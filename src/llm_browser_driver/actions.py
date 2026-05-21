"""Action executor for LLM Browser Driver.

Executes actions returned by the LLM on the current page. Handles:
- click: Element clicking with fallback strategies (id → text → href)
- fill: Field filling with multi-strategy matching
- select: Dropdown option selection
- navigate: URL navigation
- scroll: Page scrolling
- wait: Condition waiting
- evaluate: JavaScript evaluation with console.log auto-rewriting
- go_back: Browser history navigation
- done: Termination

Extracted from `09_interactive_exploration.py` execute_action() (lines 529–777).
"""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Page

from llm_browser_driver import selector


def execute_click(page: Page, action: dict[str, str]) -> str:
    """Execute a click action with multi-strategy element finding.

    Strategy order (highest to lowest confidence):
    1. Element id match
    2. Button text match
    3. Link href/text match
    4. Fallback: report failure

    Args:
        page: Playwright Page object.
        action: Action dict with "element" key.

    Returns:
        Result message string.
    """
    element = action.get("element", "")
    found = False

    # Strategy 1: Try exact id match first (most reliable)
    result = selector.click_by_id(page, element)
    if result[0]:
        found = True

    # Strategy 2: Try button text
    if not found:
        result = selector.click_by_button_text(page, element)
        if result[0]:
            found = True

    # Strategy 3: Try links
    if not found:
        result = selector.click_by_link(page, element)
        if result[0]:
            found = True

    if not found:
        return f"Could not find element matching: {element[:100]}"

    return result[1]


def execute_fill(page: Page, action: dict[str, str]) -> str:
    """Execute a fill action with multi-strategy field finding.

    Checks: name → placeholder → id → aria-label → label[for] text.
    First match fills the field.

    Args:
        page: Playwright Page object.
        action: Action dict with "field" and "value" keys.

    Returns:
        Result message string.
    """
    field = action.get("field", "")
    value = action.get("value", "")

    found, display = selector.find_field(page, field)
    if not found:
        return f"Could not find field matching: {field[:100]}"

    # Fill the matched field
    for inp in page.locator(
        "input:not([type=hidden]):not([type=submit]):not([type=button]), textarea"
    ).all()[:70]:
        try:
            inp_name = inp.get_attribute("name") or ""
            inp_placeholder = inp.get_attribute("placeholder") or ""
            inp_id = inp.get_attribute("id") or ""
            inp_aria_label = inp.get_attribute("aria-label") or ""

            # Get label text
            inp_label = ""
            inp_id_attr = inp.get_attribute("id")
            if inp_id_attr:
                label_el = page.locator(f"label[for='{inp_id_attr}']")
                if label_el.count() > 0:
                    inp_label = label_el.first.inner_text(timeout=500).strip()

            field_lower = field.lower()
            if (
                field_lower in inp_name.lower()
                or field_lower in inp_placeholder.lower()
                or field_lower in inp_id.lower()
                or field_lower in inp_aria_label.lower()
                or field_lower in inp_label.lower()
            ):
                inp.fill(value, timeout=5000)
                return f"Filled input '{display}' with '{value[:50]}'"
        except Exception:
            continue

    return f"Could not fill field matching: {field[:100]}"


def execute_select(page: Page, action: dict[str, str]) -> str:
    """Execute a select action for dropdown options.

    Args:
        page: Playwright Page object.
        action: Action dict with "field" and "option" keys.

    Returns:
        Result message string.
    """
    field = action.get("field", "")
    option = action.get("option", "")

    found, select_name = selector.find_select_field(page, field)
    if not found:
        return f"Could not find select field matching: {field[:100]}"

    return selector.click_select_option(page, select_name, option)[1]


def execute_navigate(page: Page, action: dict[str, str]) -> str:
    """Navigate to a URL.

    Args:
        page: Playwright Page object.
        action: Action dict with "url" key.

    Returns:
        Result message string.
    """
    url = action.get("url", "")
    page.goto(url, wait_until="domcontentloaded", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    return f"Navigated to {url}"


def execute_scroll(page: Page, action: dict[str, str]) -> str:
    """Scroll the page.

    Args:
        page: Playwright Page object.
        action: Action dict with "direction" and "distance" keys.

    Returns:
        Result message string.
    """
    direction = action.get("direction", "down")
    distance = action.get("distance", "partial")

    if distance == "full":
        if direction == "down":
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        else:
            page.evaluate("window.scrollTo(0, 0)")
    else:
        if direction == "down":
            page.evaluate("window.scrollBy(0, 500)")
        else:
            page.evaluate("window.scrollBy(0, -500)")

    return f"Scrolled {direction} ({distance})"


def execute_wait(page: Page, action: dict[str, str]) -> str:
    """Wait for a condition.

    Supported conditions: networkidle, load, timeout:N (milliseconds).

    Args:
        page: Playwright Page object.
        action: Action dict with "condition" key.

    Returns:
        Result message string.
    """
    condition = action.get("condition", "networkidle")
    if condition.startswith("timeout:"):
        timeout_ms = int(condition.split(":")[1])
        page.wait_for_timeout(timeout_ms)
        return f"Waited {timeout_ms}ms"
    else:
        page.wait_for_load_state(condition, timeout=10000)
        return f"Waited for {condition}"


def execute_evaluate(page: Page, action: dict[str, str]) -> str:
    """Execute JavaScript on the page.

    Auto-rewrites console.log calls to return their arguments as an array.
    Handles scripts that start with { or contain return statements.

    Args:
        page: Playwright Page object.
        action: Action dict with "script" key.

    Returns:
        Result message string with evaluation result.
    """
    script = action.get("script", "")

    # Transform console.log calls into return values
    # Playwright's evaluate() only returns what the script explicitly returns
    if "console.log(" in script:
        logs = list(re.finditer(r'console\.log\((.+?)\)(?=\s*[;,)]|$)', script, re.DOTALL))
        if logs:
            # Build a results array by collecting each console.log argument
            # Then return the array at the end
            results = []
            new_script = []
            last_end = 0
            for log_match in logs:
                new_script.append(script[last_end:log_match.start()])
                arg = log_match.group(1)
                new_script.append(f"results.push({arg});")
                last_end = log_match.end()
            new_script.append(script[last_end:])
            script = "".join(new_script) + "\nresults;"

    # Wrap script to handle 'return' statements and object literals
    if script.strip().startswith("{"):
        wrapped_script = f"(function() {{ return {script[1:-1].strip()} }})()"
    elif "return " in script:
        wrapped_script = f"(function() {{ {script} }})()"
    else:
        wrapped_script = script

    try:
        value = page.evaluate(wrapped_script)
        return f"Evaluation result: {str(value)[:200]}"
    except Exception as e:
        return f"evaluate() failed: {str(e)[:200]}"


def execute_go_back(page: Page, action: dict[str, str]) -> str:
    """Go back in browser history.

    Args:
        page: Playwright Page object.
        action: Action dict (no parameters needed).

    Returns:
        Result message string.
    """
    page.go_back(wait_until="domcontentloaded", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    return "Went back"


# ---------------------------------------------------------------------------
# Public action dispatcher
# ---------------------------------------------------------------------------

# Action handler registry
ACTION_HANDLERS = {
    "click": execute_click,
    "fill": execute_fill,
    "select": execute_select,
    "navigate": execute_navigate,
    "scroll": execute_scroll,
    "wait": execute_wait,
    "evaluate": execute_evaluate,
    "go_back": execute_go_back,
}


def execute_action(page: Page, action: dict[str, Any]) -> tuple[str, bool]:
    """Execute an action on the page.

    Dispatches to the appropriate handler based on the "action" key.
    Returns a result message and whether the action was a termination signal.

    Args:
        page: Playwright Page object.
        action: Action dict with at least an "action" key.

    Returns:
        (result_message, is_done) tuple.
    """
    action_type = action.get("action", "unknown")

    # Termination signal
    if action_type == "done":
        summary = action.get("summary", "Test complete")
        return summary, True

    if action_type == "error":
        return f"Error reported: {action.get('message', 'Unknown error')}", True

    handler = ACTION_HANDLERS.get(action_type)
    if handler is None:
        return f"Unknown action type: {action_type}", False

    try:
        result = handler(page, action)
        return result, False
    except Exception as e:
        return f"Action '{action_type}' failed: {str(e)[:200]}", False
