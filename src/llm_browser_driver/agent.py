"""Core interaction loop — the loop driver.

This is the central module that ties together state extraction, LLM decision
making, action execution, and reporting. It provides the public
`BrowserDriver` class that users import.

The interaction loop:
1. Capture page state
2. LLM decides next action
3. Execute action on page
4. Record result
5. Repeat until done or max iterations

Extracted from `09_interactive_exploration.py`
(see lines 354–427 for system prompt, 780–859 for loop, 904–980 for main).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, Browser as PlaywrightBrowser, BrowserContext

from llm_browser_driver.config import AppConfig, load_config
from llm_browser_driver.state import get_page_state, build_page_summary, build_action_history_summary
from llm_browser_driver.llm_client import LLMClient, parse_action_from_response
from llm_browser_driver.actions import execute_action


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

INTERACTIVE_SYSTEM_PROMPT = """You are an exploratory QA agent testing a web application.
You can interact with the page by taking actions. Your goal is to thoroughly test the page for bugs.

**Your capabilities:**
- Click buttons and links
- Fill input fields and textareas
- Select options from native <select> dropdowns
- Select options from custom dropdown menus (SolidJS/React/HTML5)
- Scroll the page
- Navigate to URLs
- Wait for elements to appear
- Evaluate JavaScript
- Go back/forward in browser history

**Your workflow:**
1. Analyze the current page state - identify ALL visible inputs, dropdowns, and buttons
2. Fill in all form fields (inputs, textareas, dropdowns) with realistic test values
3. **CRITICAL: After filling all fields, look for and click navigation buttons** like "Next Step", "Submit", "Continue", "Save", or similar
4. Observe the result and state changes (URL change? new page? error messages?)
5. Repeat until you've tested key functionality or reached max iterations

**Action types and parameters:**
- `click`: Click an element. Parameters: `{{"action": "click", "element": "button text or link href"}}`
  - For buttons: use the button text exactly as shown
  - For links: use the href or link text
- `fill`: Fill an input field. Parameters: `{{"action": "fill", "field": "input name or placeholder", "value": "text to enter"}}`
  - Use the field name, placeholder text, or data-testid from the page state
  - For textareas: use placeholder text or data-testid (e.g., "input-description")
- `select`: Select an option from a native <select> dropdown. Parameters: `{{"action": "select", "field": "select name", "option": "option text"}}`
- `select_custom`: Select an option from a custom dropdown (SolidJS/React/HTML5). Custom dropdowns use <button> triggers with <i class="fa-chevron-down"> icons instead of <select> elements. Parameters: `{{"action": "select_custom", "field": "dropdown trigger text or testid", "option": "option text"}}`
  - Use this when you see `--- CUSTOM DROPDOWNS ---` in the page state
  - The "field" should be the trigger text (e.g., "Select Country") or data-testid (e.g., "select-pickup-country")
  - The "option" should be the exact option text from the `--- DROPDOWN MENU ITEMS ---` section
- `scroll`: Scroll the page. Parameters: `{{"action": "scroll", "direction": "down" or "up", "distance": "partial" or "full"}}`
- `navigate`: Navigate to a URL. Parameters: `{{"action": "navigate", "url": "full URL"}}`
- `go_back`: Go back in browser history. Parameters: `{{"action": "go_back"}}`
- `wait`: Wait for a condition. Parameters: `{{"action": "wait", "condition": "networkidle" or "load" or "timeout:5000"}}`
- `evaluate`: Run JavaScript. Parameters: `{{"action": "evaluate", "script": "javascript expression"}}`

**Focus areas for testing:**
1. Navigation: Can you move between pages? Are links working? Do "Next", "Back", "Submit" buttons work?
2. Forms: Do inputs accept text? Are there validation errors? Do buttons become enabled after filling?
3. Interactive elements: Do dropdowns work? Do clickable elements trigger state changes?
4. Error states: What happens with invalid input? Empty states? Loading states?
5. Accessibility: Missing labels, disabled elements, keyboard navigation hints
6. Content: Is data displaying correctly? Are there broken images or links?

**CRITICAL: Multi-step wizard patterns**
- When you see "Step X" in the page state or title, you're on a multi-step form
- Fill ALL visible fields on the current step (check INPUTS, TEXTAREAS, CUSTOM DROPDOWNS sections)
- After filling all fields, **IMMEDIATELY click the "Next Step" or similar navigation button**
- Do NOT stop and call "done" until you've advanced to the next step or hit a real blocker
- Track your progress: Step 1 → Step 2 → Step 3 etc. by checking the page state each iteration

**Important rules:**
- Be methodical: test one area at a time
- Try both expected and unexpected inputs (empty, very long text, special characters)
- Look for state changes after each action (new elements, URL changes, errors)
- If you encounter an error, document it and try alternatives
- If a page is a 404, note it and move on
- You can take up to {max_iter} actions total
- If you've tested the main functionality, stop and summarize

**Output format:**
Return ONLY a JSON object with your next action:
{{"action": "click", "element": "button text"}}

If you want to stop, return:
{{"action": "done", "summary": "Brief summary of what you tested and found"}}

Do NOT include any explanation or reasoning outside the JSON.
"""


# ---------------------------------------------------------------------------
# Data classes for results
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """Result of a single exploration test."""

    test_name: str
    url: str
    status: str  # "success" or "error"
    initial_url: str = ""
    final_url: str = ""
    iterations: int = 0
    action_history: list[dict[str, Any]] = field(default_factory=list)
    console_errors: list[dict[str, str]] = field(default_factory=list)
    error: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    time_taken: float = 0.0
    # Screenshot metadata (populated when screenshot capture is enabled)
    _screenshot_dir: str | None = None
    _screenshots_taken: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "test": self.test_name,
            "url": self.url,
            "status": self.status,
            "initial_url": self.initial_url,
            "final_url": self.final_url,
            "iterations": self.iterations,
            "action_history": self.action_history,
            "console_errors": self.console_errors,
            "error": self.error,
            "findings": self.findings,
            "time_taken": self.time_taken,
        }

    def __repr__(self) -> str:
        return f"TestResult(test_name={self.test_name!r}, status={self.status!r})"



# ---------------------------------------------------------------------------
# BrowserDriver — public API
# ---------------------------------------------------------------------------


class BrowserDriver:
    """Autonomous web testing driver powered by an LLM.

    The driver maintains a Playwright browser session and uses an LLM to
    decide exploratory actions. It provides a simple, config-driven API
    for both exploratory and spec-driven testing.

    Args:
        config: Application configuration. If None, loads defaults
                (environment variables → config file → hardcoded defaults).
        config_kwargs: Passed to `load_config()` to override defaults.

    Example:
        >>> driver = BrowserDriver(
        ...     config_kwargs={
        ...         "url": "http://localhost:3000",
        ...         "llm": {"api_url": "http://vllm:8000/v1", "model": "qwen3"},
        ...     }
        ... )
        >>> result = driver.explore(goal="Test the login form", max_iterations=30)
        >>> for finding in result.findings:
        ...     print(finding["description"])

    Attributes:
        config: Resolved application configuration.
        llm: LLM client instance.
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        **config_kwargs: Any,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            self.config = load_config(**config_kwargs)
        self.llm = LLMClient(self.config)
        self._browser_instance: PlaywrightBrowser | None = None
        self._playwright_instance: Any = None

    # ------------------------------------------------------------------
    # Screenshot capture
    # ------------------------------------------------------------------

    def _take_screenshot(
        self,
        page: Any,
        step: int,
        screenshot_dir: Path,
        tag: str = "",
    ) -> str | None:
        """Capture a screenshot and save it to the screenshot directory.

        Args:
            page: Playwright Page object.
            step: Current step number for naming.
            screenshot_dir: Directory to save screenshots.
            tag: Optional tag suffix (e.g., 'failure').

        Returns:
            Relative file path (e.g., 'screenshots/step-1.png') or None.
        """
        try:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            if tag:
                name = f"step-{step}-{tag}.png"
            else:
                name = f"step-{step}.png"
            path = screenshot_dir / name
            page.screenshot(path=str(path), full_page=True, timeout=5000)
            return f"screenshots/{name}"
        except Exception:
            return None


    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def __enter__(self) -> "BrowserDriver":
        """Start the browser when entering the context manager."""
        self._playwright_instance = sync_playwright().start()
        self._browser_instance = self._playwright_instance.chromium.launch(
            headless=self.config.browser.headless,
        )
        return self

    def __exit__(self, *args: Any) -> None:
        """Close the browser when exiting the context manager."""
        self.close()

    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._browser_instance:
            self._browser_instance.close()
            self._browser_instance = None
        if self._playwright_instance:
            self._playwright_instance.stop()
            self._playwright_instance = None

    # ------------------------------------------------------------------
    # Core method: explore
    # ------------------------------------------------------------------

    def explore(
        self,
        url: str | None = None,
        goal: str = "",
        max_iterations: int | None = None,
        auth_file: str | Path | None = None,
        screenshot_dir: str | Path | None = None,
        screenshot_interval: int | None = None,
        screenshot_on_failure: bool = True,
    ) -> TestResult:
        """Run an interactive exploration test.

        The driver navigates to the URL, captures page state, and uses
        the LLM to decide exploratory actions until the goal is achieved
        or max iterations are reached.

        Args:
            url: Page URL to explore. Defaults to config.url.
            goal: Natural-language description of what to test.
            max_iterations: Maximum LLM decisions before stopping.
                Defaults to config.agent.max_iterations.
            auth_file: Path to Playwright storage-shipper JSON for
                authenticated sessions.
            screenshot_dir: Directory to save screenshots. If provided,
                screenshots are saved as step-{N}.png.
            screenshot_interval: Take a screenshot every N iterations.
                Only used when screenshot_dir is provided.
            screenshot_on_failure: Take a screenshot when an error occurs.
                Only used when screenshot_dir is provided.

        Returns:
            TestResult with action history, console errors, and findings.
            If screenshots were captured, each action record includes
            a "screenshot" key with the relative path to the PNG.

        Example:
            >>> result = driver.explore(
            ...     url="http://localhost:3000",
            ...     goal="Test the user registration flow end-to-end",
            ...     max_iterations=30,
            ... )
        """
        url = url or self.config.url
        if not url:
            raise ValueError("URL is required — pass it to explore() or set config.url")

        max_iterations = max_iterations or self.config.agent.max_iterations

        system_prompt = INTERACTIVE_SYSTEM_PROMPT.format(
            max_iter=max_iterations
        )

        # Start browser if not already running
        should_close_browser = self._browser_instance is None
        if should_close_browser:
            self._playwright_instance = sync_playwright().start()
            self._browser_instance = self._playwright_instance.chromium.launch(
                headless=self.config.browser.headless,
            )

        # Create context (with auth if provided)
        context: BrowserContext | None = None
        if auth_file:
            context = self._browser_instance.new_context(
                storage_state=str(auth_file),
            )
        else:
            context = self._browser_instance.new_context(
                viewport={
                    "width": self.config.browser.viewport_width,
                    "height": self.config.browser.viewport_height,
                },
            )

        page = context.new_page()
        start_time = time.time()

        # Setup screenshot capture
        screenshot_dir_path: Path | None = None
        if screenshot_dir:
            screenshot_dir_path = Path(screenshot_dir)
            # Use run-{timestamp} subfolder if screenshot_dir is a base directory
            if screenshot_dir_path.is_dir() and not screenshot_dir_path.name.startswith("run-"):
                from datetime import datetime
                ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
                screenshot_dir_path = screenshot_dir_path / f"run-{ts}"
            screenshot_dir_path.mkdir(parents=True, exist_ok=True)

        try:
            # Navigate to the page
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)

            # Initial page screenshot
            screenshot_path = None
            if screenshot_dir_path is not None:
                screenshot_path = self._take_screenshot(page, 0, screenshot_dir_path)

            initial_url = page.url
            action_history: list[dict[str, Any]] = []
            findings: list[dict[str, Any]] = []
            screenshots_taken = 0

            # Main exploration loop
            iteration = 0
            while iteration < max_iterations:
                iteration += 1

                # Capture current state
                snapshot = get_page_state(page)

                # Build prompts
                page_summary = build_page_summary(snapshot)
                history_summary = build_action_history_summary(action_history)

                # Heuristic: detect if all form fields are filled and suggest clicking "Next Step"
                # This addresses the case where the LLM fills all fields but doesn't know to navigate
                fill_actions = [r for r in action_history if r.get('action') == 'fill']
                fill_count = len(fill_actions)
                
                # Check if any navigation button exists and is enabled
                nav_buttons = [
                    btn for btn in snapshot.get('details', {}).get('buttons', [])
                    if btn.get('text', '') in ('Next Step', 'Next', 'Continue', 'Submit', 'Save', 'Review', 'Confirm')
                    and not btn.get('disabled', False)
                ]
                
                # Check if navigation has already been attempted
                nav_attempted = any(
                    r.get('action') == 'click' and 'Next' in str(r.get('result', ''))
                    for r in action_history
                )
                
                # Check if any dropdown was selected
                dropdown_actions = [r for r in action_history if r.get('action') in ('select_custom', 'select')]
                dropdown_count = len(dropdown_actions)
                
                # Conservative heuristic: only suggest navigation when SIGNIFICANT form interaction occurred
                # Require both fills AND dropdowns to ensure substantial progress
                form_interacted = fill_count >= 3 and dropdown_count >= 1
                # Only suggest, never auto-click (LLM may not follow, but auto-clicking breaks validation)
                navigation_hint = ""
                auto_click_nav = False
                if form_interacted and nav_buttons and not nav_attempted:
                    btn_text = ", ".join(b["text"] for b in nav_buttons)
                    navigation_hint = (
                        f"\n**NAVIGATION SUGGESTION**: You have performed {fill_count} fills and {dropdown_count} dropdown selections. "
                        f"Nav buttons available: {btn_text}. If all form fields are filled, click one to proceed.\n"
                    )
                    print(
                        f"[ITER {iteration}] NAV HINT (suggestion only): "
                        f"fills={fill_count}, dropdowns={dropdown_count}, nav={btn_text}",
                        flush=True,
                    )
                elif form_interacted and nav_attempted and not nav_buttons:
                    # LLM tried to click Next but it failed (validation error), suggest checking errors
                    navigation_hint = (
                        "\n**NOTE**: You attempted to navigate but the Next Step button is now disabled. "
                        "This likely means validation failed — check for red error messages on the page and fill any missing fields.\n"
                    )
                    print(
                        f"[ITER {iteration}] NAV FAILED: Next Step disabled, suggesting validation check",
                        flush=True,
                    )

                user_prompt = f"""TASK: {goal}

{history_summary}

CURRENT PAGE STATE:
{page_summary}
{navigation_hint}

Based on the goal, action history, and current page state, decide the next action to take.
"""

                # DEBUG: Print page summary to understand what LLM sees
                if iteration <= 5:
                    print(f"\n[ITER {iteration}] PAGE SUMMARY SNAPSHOT:", flush=True)
                    # Print just the forms section
                    form_lines = [l for l in page_summary.split('\n') if any(k in l for k in ['INPUTS', 'TEXTAREAS', 'BUTTONS', 'SELECTS', 'CUSTOM', 'FORM FIELDS'])]
                    for line in form_lines[:30]:
                        print(f"  {line}", flush=True)

                llm_response = self.llm.chat(system_prompt, user_prompt)
                action = parse_action_from_response(llm_response)
                
                # HARD CODED FALLBACK: If heuristic says to auto-click nav but LLM
                # didn't do it anyway (common with qwen3), force click the nav button
                if auto_click_nav and action.get('action') != 'click':
                    # LLM ignored the navigation hint - force it
                    nav_btn_text = nav_buttons[0]['text']
                    action = {"action": "click", "element": nav_btn_text}
                    action['auto_forced'] = True  # flag for logging

                # Execute action
                result_msg, is_done = execute_action(page, action)

                # Take screenshot at intervals
                current_screenshot: str | None = None
                if screenshot_dir_path is not None:
                    screenshot_interval_int = screenshot_interval or 0
                    if screenshot_interval_int > 0 and iteration % screenshot_interval_int == 0:
                        current_screenshot = self._take_screenshot(
                            page, iteration, screenshot_dir_path
                        )
                        if current_screenshot:
                            screenshots_taken += 1

                # Record result
                action_record = {
                    "step": iteration,
                    "action": action.get("action", "unknown"),
                    "parameters": {k: v for k, v in action.items() if k != "action"},
                    "result": result_msg[:500],
                    "url": page.url,
                }
                if current_screenshot:
                    action_record["screenshot"] = current_screenshot
                action_history.append(action_record)

                # Check if done
                if is_done or action.get("action") == "done":
                    summary = action.get("summary", "")
                    if summary:
                        findings.append({
                            "type": "summary",
                            "description": summary,
                        })
                    break

            # Build findings from action history
            for record in action_history:
                result = record.get("result", "")
                # Detect error patterns in results
                if "Could not find" in result or "failed" in result.lower():
                    findings.append({
                        "type": "issue",
                        "severity": "low",
                        "action": record["action"],
                        "description": result[:200],
                    })

            elapsed = time.time() - start_time

            return TestResult(
                test_name=goal,
                url=url,
                status="success",
                initial_url=initial_url,
                final_url=page.url,
                iterations=iteration,
                action_history=action_history,
                console_errors=snapshot.get("console", []),
                findings=findings,
                time_taken=elapsed,
                _screenshot_dir=str(screenshot_dir_path) if screenshot_dir_path else None,
                _screenshots_taken=screenshots_taken,
            )

        except Exception as e:
            elapsed = time.time() - start_time

            # Capture error screenshot
            screenshot_path = None
            if screenshot_dir_path is not None and screenshot_on_failure:
                screenshot_path = self._take_screenshot(
                    page, 0, screenshot_dir_path, tag="failure"
                )
                screenshots_taken += 1 if screenshot_path else 0

            return TestResult(
                test_name=goal,
                url=url,
                status="error",
                initial_url=initial_url if 'initial_url' in dir() else "",
                final_url=page.url if page else "",
                iterations=iteration,
                action_history=action_history,
                error=str(e),
                time_taken=elapsed,
                _screenshot_dir=str(screenshot_dir_path) if screenshot_dir_path else None,
                _screenshots_taken=screenshots_taken,
            )

        finally:
            page.close()
            context.close()
            # Only close browser if we created it inside explore()
            if should_close_browser:
                self.close()

    # ------------------------------------------------------------------
    # Convenience: run multiple explorations
    # ------------------------------------------------------------------

    def explore_batch(
        self,
        tests: list[dict[str, Any]],
        max_iterations: int | None = None,
    ) -> list[TestResult]:
        """Run multiple explorations sequentially.

        Each test is a dict with keys: url (str), goal (str),
        and optionally auth_file (str|Path).

        Args:
            tests: List of test dicts.
            max_iterations: Shared max iterations for all tests.

        Returns:
            List of TestResults.

        Example:
            >>> results = driver.explore_batch([
            ...     {"url": "http://localhost:3000", "goal": "test login"},
            ...     {"url": "http://localhost:3000/jobs", "goal": "test job listing"},
            ... ])
        """
        results = []
        for test in tests:
            result = self.explore(
                url=test["url"],
                goal=test["goal"],
                max_iterations=max_iterations,
                auth_file=test.get("auth_file"),
            )
            results.append(result)
        return results
