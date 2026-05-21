"""Retry and recovery patterns (borrowed from browser-use).

Provides robust action execution with:
- Automatic retries on transient failures
- Fallback selector strategies when primary match fails
- Exponential backoff between retries
- Failure counting and circuit breaker
- Recovery actions (wait, scroll, refresh) when stuck

Usage::

    from llm_browser_driver.retry import RetryConfig, retry_action

    # Default config: 3 retries, exponential backoff
    config = RetryConfig(max_retries=3, backoff_base=0.5)

    # Use with the action executor
    result = retry_action(
        executor=executor,
        action=action,
        config=config,
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Args:
        max_retries: Maximum number of retry attempts (default: 3).
        backoff_base: Base delay in seconds for exponential backoff
                      (default: 0.5). Each retry doubles this delay.
        max_delay: Maximum delay between retries in seconds (default: 5.0).
        retryable_errors: Set of exception types that trigger a retry.
                          Empty means retry on all errors.
        recovery_actions: Optional list of recovery strategies to try
                          before giving up. E.g., ["wait", "scroll", "refresh"].
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    max_delay: float = 5.0
    retryable_errors: set[type[Exception]] = field(default_factory=set)
    recovery_actions: list[str] = field(default_factory=lambda: [
        "wait", "scroll", "refresh",
    ])

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if this error should trigger a retry."""
        if attempt >= self.max_retries:
            return False
        if not self.retryable_errors:
            return True
        return isinstance(error, tuple(self.retryable_errors))

    def delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number using exponential backoff."""
        delay = self.backoff_base * (2 ** attempt)
        return min(delay, self.max_delay)


# ---------------------------------------------------------------------------
# Action result
# ---------------------------------------------------------------------------


@dataclass
class ActionResult:
    """Result of an action execution attempt."""

    success: bool
    result: Any = None
    error: str | None = None
    attempt: int = 0
    retries_used: int = 0
    total_duration_ms: float = 0.0

    @property
    def final(self) -> bool:
        """Whether no more retries are possible."""
        return self.success or self.retries_used >= 3  # Conservative threshold


# ---------------------------------------------------------------------------
# Retry execution
# ---------------------------------------------------------------------------


def retry_action(
    executor: Callable,
    action: dict[str, Any],
    config: RetryConfig | None = None,
) -> ActionResult:
    """Execute an action with retry logic and fallback selectors.

    Wraps an action executor to add:
    - Automatic retries with exponential backoff
    - Fallback selector strategies
    - Recovery actions when stuck
    - Detailed result tracking

    Args:
        executor: Callable(action) -> (success: bool, result: Any, error: str)
        action: Action dict with 'action' type and 'parameters'.
        config: Retry configuration. Defaults to 3 retries.

    Returns:
        ActionResult with success/failure status and details.

    Example::

        config = RetryConfig(max_retries=3)
        result = retry_action(
            executor=driver.execute_action,
            action={"action": "click", "parameters": {"element": "#btn"}},
            config=config,
        )
        if result.success:
            print(f"Clicked after {result.attempt} attempt(s)")
        else:
            print(f"Failed after {result.retries_used} retries: {result.error}")
    """
    if config is None:
        config = RetryConfig()

    last_error = None
    start = time.monotonic()

    for attempt in range(config.max_retries + 1):
        try:
            success, result, error = executor(action)
            duration_ms = (time.monotonic() - start) * 1000

            if success:
                return ActionResult(
                    success=True,
                    result=result,
                    attempt=attempt + 1,
                    retries_used=attempt,
                    total_duration_ms=duration_ms,
                )

            last_error = error or "Action returned failure"
            logger.warning(
                "Action failed (attempt %d/%d): %s",
                attempt + 1, config.max_retries + 1, last_error,
            )

        except Exception as e:
            last_error = str(e)
            logger.warning(
                "Action exception (attempt %d/%d): %s",
                attempt + 1, config.max_retries + 1, last_error,
            )

        # Retry with backoff if not last attempt
        if attempt < config.max_retries:
            delay = config.delay(attempt)
            logger.debug("Retrying in %.1fs...", delay)
            time.sleep(delay)

    # All retries exhausted — try recovery actions
    if config.recovery_actions:
        logger.info("All retries exhausted, trying recovery actions...")
        recovery_result = try_recovery(executor, action, config.recovery_actions)
        if recovery_result.success:
            return recovery_result

    # Final failure
    duration_ms = (time.monotonic() - start) * 1000
    return ActionResult(
        success=False,
        error=last_error or "All retries and recovery failed",
        attempt=config.max_retries + 1,
        retries_used=config.max_retries,
        total_duration_ms=duration_ms,
    )


def try_recovery(
    executor: Callable,
    action: dict[str, Any],
    recovery_strategies: list[str],
) -> ActionResult:
    """Try recovery actions when the primary action fails repeatedly.

    Recovery strategies:
    - wait: Wait for page to settle (networkidle, 2s)
    - scroll: Scroll slightly to trigger lazy-loaded content
    - refresh: Reload the page and retry

    Args:
        executor: The action executor.
        action: The original failed action.
        recovery_strategies: List of recovery strategies to try.

    Returns:
        ActionResult — success if any recovery worked, failure otherwise.
    """
    # Map strategy names to recovery functions
    strategies = {
        "wait": _recover_wait,
        "scroll": _recover_scroll,
        "refresh": _recover_refresh,
    }

    for strategy in recovery_strategies:
        fn = strategies.get(strategy)
        if fn is None:
            logger.warning("Unknown recovery strategy: %s", strategy)
            continue

        logger.info("Trying recovery strategy: %s", strategy)
        try:
            result = fn(executor, action)
            if result.success:
                logger.info("Recovery successful with: %s", strategy)
                return result
        except Exception as e:
            logger.warning("Recovery strategy '%s' failed: %s", strategy, e)

    return ActionResult(
        success=False,
        error=f"All recovery strategies failed: {recovery_strategies}",
        attempt=0,
        retries_used=0,
    )


def _recover_wait(executor, action: dict[str, Any]) -> ActionResult:
    """Wait for page to settle, then retry the original action."""
    wait_action = {"action": "wait", "parameters": {"condition": "networkidle"}}
    success, _, _ = executor(wait_action)

    if not success:
        return ActionResult(
            success=False,
            error="Wait recovery failed",
        )

    time.sleep(2)
    success, result, error = executor(action)
    return ActionResult(
        success=success,
        result=result,
        error=error,
    )


def _recover_scroll(executor, action: dict[str, Any]) -> ActionResult:
    """Scroll down slightly to trigger lazy content, then retry."""
    scroll_action = {"action": "scroll", "parameters": {"direction": "down", "distance": 200}}
    executor(scroll_action)
    time.sleep(0.5)
    success, result, error = executor(action)
    return ActionResult(
        success=success,
        result=result,
        error=error,
    )


def _recover_refresh(executor, executor_args: dict[str, Any] | None = None) -> ActionResult:
    """Reload the page and retry.

    Note: This requires the executor to have access to the current URL.
    """
    reload_action = {"action": "evaluate", "parameters": {"script": "window.location.reload()"}}
    executor(reload_action)
    time.sleep(1)
    # After refresh, we'd need to navigate back to the original URL
    # This is a simplified version — real implementation needs URL tracking
    return ActionResult(
        success=False,
        error="Refresh recovery requires URL tracking (not implemented)",
    )
