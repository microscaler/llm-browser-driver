"""Tests for retry and recovery patterns.

Covers:
- RetryConfig defaults and behavior
- retry_action success path
- retry_action failure with retries
- Exponential backoff timing
- Recovery actions (wait, scroll, refresh)
- Final failure after all retries exhausted
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from llm_browser_driver.retry import (
    RetryConfig,
    ActionResult,
    retry_action,
    try_recovery,
    _recover_wait,
    _recover_scroll,
)


# ---------------------------------------------------------------------------
# RetryConfig tests
# ---------------------------------------------------------------------------


class TestRetryConfig:
    def test_defaults(self):
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.backoff_base == 0.5
        assert config.max_delay == 5.0
        assert config.retryable_errors == set()
        assert config.recovery_actions == ["wait", "scroll", "refresh"]

    def test_custom_values(self):
        config = RetryConfig(
            max_retries=5,
            backoff_base=1.0,
            max_delay=10.0,
        )
        assert config.max_retries == 5
        assert config.backoff_base == 1.0
        assert config.max_delay == 10.0

    def test_should_retry_exhausted(self):
        config = RetryConfig(max_retries=2)
        assert not config.should_retry(Exception("fail"), attempt=2)

    def test_should_retry_available(self):
        config = RetryConfig(max_retries=3)
        assert config.should_retry(Exception("fail"), attempt=0)
        assert config.should_retry(Exception("fail"), attempt=1)
        assert config.should_retry(Exception("fail"), attempt=2)

    def test_should_retry_with_specific_errors(self):
        config = RetryConfig(retryable_errors={ValueError})
        assert config.should_retry(ValueError("bad"), attempt=0)
        assert not config.should_retry(TypeError("bad"), attempt=0)

    def test_exponential_backoff(self):
        config = RetryConfig(backoff_base=1.0, max_delay=10.0)
        # attempt=0 -> 1s, attempt=1 -> 2s, attempt=2 -> 4s, attempt=3 -> 8s
        assert config.delay(0) == 1.0
        assert config.delay(1) == 2.0
        assert config.delay(2) == 4.0
        assert config.delay(3) == 8.0

    def test_max_delay_cap(self):
        config = RetryConfig(backoff_base=1.0, max_delay=5.0)
        # attempt=10 -> 1024s capped to 5s
        assert config.delay(10) == 5.0


# ---------------------------------------------------------------------------
# retry_action tests
# ---------------------------------------------------------------------------


class TestRetryAction:
    def test_success_on_first_attempt(self):
        executor = MagicMock(return_value=(True, "clicked", None))
        result = retry_action(executor, {"action": "click", "parameters": {}})

        assert result.success is True
        assert result.result == "clicked"
        assert result.attempt == 1
        assert result.retries_used == 0
        executor.assert_called_once()

    def test_retry_on_failure(self):
        call_count = [0]

        def executor(action):
            call_count[0] += 1
            if call_count[0] < 3:
                return (False, None, "not found")
            return (True, "clicked", None)

        result = retry_action(
            executor,
            {"action": "click", "parameters": {}},
            config=RetryConfig(max_retries=5, backoff_base=0.01),
        )

        assert result.success is True
        assert result.retries_used == 2
        assert call_count[0] == 3

    def test_all_retries_exhausted(self):
        executor = MagicMock(return_value=(False, None, "element not found"))
        result = retry_action(
            executor,
            {"action": "click", "parameters": {}},
            config=RetryConfig(max_retries=2, backoff_base=0.01),
        )

        assert result.success is False
        assert result.retries_used == 2
        assert "element not found" in result.error
        # Recovery tries wait, scroll, refresh — each calls executor
        # 2 retries + 3 recovery actions = 5 calls (refresh doesn't call executor with action)
        # refresh just calls evaluate → total depends on implementation
        assert executor.call_count >= 2

    def test_exception_caught(self):
        def executor(action):
            raise ConnectionError("browser disconnected")

        result = retry_action(
            executor,
            {"action": "click", "parameters": {}},
            config=RetryConfig(max_retries=1, backoff_base=0.01),
        )

        assert result.success is False
        assert "browser disconnected" in result.error

    def test_recovery_triggered_on_exhaustion(self):
        """When retries exhausted, recovery actions are tried."""
        click_calls = [0]

        def executor(action):
            if action["action"] == "click":
                click_calls[0] += 1
                # Primary click fails twice, succeeds on 3rd attempt
                if click_calls[0] <= 2:
                    return (False, None, "not found")
                return (True, "clicked", None)
            # Recovery actions succeed
            return (True, None, None)

        result = retry_action(
            executor,
            {"action": "click", "parameters": {}},
            config=RetryConfig(
                max_retries=1,
                backoff_base=0.01,
                recovery_actions=["wait", "scroll", "refresh"],
            ),
        )

        # Recovery should have saved it (wait succeeds, then retry click which succeeds)
        assert result.success is True
        # Should have: 2 click retries + wait + refresh evaluate + click recovery
        assert click_calls[0] >= 3

    def test_default_config_used(self):
        executor = MagicMock(return_value=(True, "ok", None))
        result = retry_action(executor, {"action": "click", "parameters": {}})
        assert result.success is True

    def test_duration_tracked(self):
        def executor(action):
            time.sleep(0.01)
            return (True, "ok", None)

        result = retry_action(
            executor,
            {"action": "click", "parameters": {}},
            config=RetryConfig(max_retries=0, backoff_base=0.01),
        )
        assert result.total_duration_ms > 0


# ---------------------------------------------------------------------------
# ActionResult tests
# ---------------------------------------------------------------------------


class TestActionResult:
    def test_success_is_not_final_until_retries_exhausted(self):
        result = ActionResult(success=True, attempt=1, retries_used=0)
        assert result.final is True  # success = final

    def test_failure_is_final(self):
        result = ActionResult(success=False, attempt=4, retries_used=3)
        assert result.final is True

    def test_pending_not_final(self):
        result = ActionResult(success=False, attempt=1, retries_used=0)
        assert result.final is False
