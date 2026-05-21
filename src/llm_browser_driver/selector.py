"""Action-to-element matching (fuzzy lookup).

The selector module implements the anti-fragile selection strategy that is
LLM Browser Driver's core differentiator. Every action is matched by
semantically stable identifiers — never by CSS class or XPath.

Selection strategy:
- Click: element id → button text → link href → fuzzy text
- Fill: input name → placeholder → id → aria-label → label[for] text
- Select: select name → option text

This means UI refactors (class name swaps, component restructuring) don't
break tests as long as the page remains accessible.

Extracted from `09_interactive_exploration.py` execute_action() (lines 529–777).
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page


# ---------------------------------------------------------------------------
# Click selectors — these also perform the click (atomic find+click)
# ---------------------------------------------------------------------------


def click_by_id(page: Page, element_text: str) -> tuple[bool, str]:
    """Try to click by element id attribute.

    Highest-confidence click strategy. The element id is semantically stable
    across UI refactors.

    Args:
        page: Playwright Page object.
        element_text: The element text from the LLM (used as id).

    Returns:
        (success, result_message) tuple.
    """
    try:
        id_locator = page.locator(
            f"#{element_text.strip().lower().replace(' ', '-')}"
        )
        if id_locator.count() > 0:
            id_locator.click(timeout=5000)
            text = id_locator.inner_text(timeout=1000).strip()
            return (
                True,
                f"Clicked by id='{element_text.strip().lower().replace(' ', '-')}': "
                f"{text[:100]}",
            )
    except Exception:
        pass
    return False, ""


def click_by_button_text(page: Page, element_text: str) -> tuple[bool, str]:
    """Try to click by button text match.

    Args:
        page: Playwright Page object.
        element_text: The element text from the LLM.

    Returns:
        (success, result_message) tuple.
    """
    buttons = page.locator("button, [role=button]")
    for btn in buttons.all()[:50]:
        try:
            text = btn.inner_text(timeout=500).strip().lower()
            if element_text.lower() in text or text in element_text.lower():
                btn.click(timeout=5000)
                return (
                    True,
                    f"Clicked button: {btn.inner_text(timeout=1000)[:100]}",
                )
        except Exception:
            continue
    return False, ""


def click_by_link(page: Page, element_text: str) -> tuple[bool, str]:
    """Try to click by link text or href match.

    Args:
        page: Playwright Page object.
        element_text: The element text from the LLM.

    Returns:
        (success, result_message) tuple.
    """
    links = page.locator('a[href]')
    for link in links.all()[:50]:
        try:
            href = link.get_attribute("href") or ""
            text = link.inner_text(timeout=500).strip().lower()
            if (
                element_text.lower() in text
                or element_text.lower() in href.lower()
                or text in element_text.lower()
            ):
                link.click(timeout=5000)
                return True, f"Clicked link: {text[:100]}"
        except Exception:
            continue
    return False, ""


# ---------------------------------------------------------------------------
# Field finders — return (success, display_name_or_empty)
# The actual fill/select ops are in actions.py so selector stays focused
# on "how to find" not "how to modify"
# ---------------------------------------------------------------------------


def find_field(page: Page, field_text: str) -> tuple[bool, str]:
    """Try to find an input or textarea field by multiple criteria.

    Checks: name → placeholder → id → aria-label → label[for] text.
    First match wins. This is the fill field matching strategy.

    Args:
        page: Playwright Page object.
        field_text: The field text from the LLM (e.g., "email", "First Name").

    Returns:
        (success, display_name_or_empty) tuple. The display name is the first
        matching identifier found (label > aria-label > id > name > placeholder).
    """
    # Try inputs first
    inputs = page.locator(
        "input:not([type=hidden]):not([type=submit]):not([type=button])"
    )

    for inp in inputs.all()[:50]:
        try:
            inp_name = inp.get_attribute("name") or ""
            inp_placeholder = inp.get_attribute("placeholder") or ""
            inp_id = inp.get_attribute("id") or ""
            inp_aria_label = inp.get_attribute("aria-label") or ""

            # Get label text by finding associated <label> element
            inp_label = ""
            inp_id_attr = inp.get_attribute("id")
            if inp_id_attr:
                label_el = page.locator(f"label[for='{inp_id_attr}']")
                if label_el.count() > 0:
                    inp_label = label_el.first.inner_text(timeout=500).strip()

            field_lower = field_text.lower()
            if (
                field_lower in inp_name.lower()
                or field_lower in inp_placeholder.lower()
                or field_lower in inp_id.lower()
                or field_lower in inp_aria_label.lower()
                or field_lower in inp_label.lower()
            ):
                # Use the matched identifier for the result
                display = (
                    inp_label
                    or inp_aria_label
                    or inp_id
                    or inp_name
                    or inp_placeholder
                )
                return True, display

        except Exception:
            continue

    # Try textareas
    textareas = page.locator("textarea")
    for ta in textareas.all()[:20]:
        try:
            ta_name = ta.get_attribute("name") or ""
            ta_placeholder = ta.get_attribute("placeholder") or ""
            ta_id = ta.get_attribute("id") or ""
            ta_aria_label = ta.get_attribute("aria-label") or ""

            ta_label = ""
            ta_id_attr = ta.get_attribute("id")
            if ta_id_attr:
                label_el = page.locator(f"label[for='{ta_id_attr}']")
                if label_el.count() > 0:
                    ta_label = label_el.first.inner_text(timeout=500).strip()

            field_lower = field_text.lower()
            if (
                field_lower in ta_name.lower()
                or field_lower in ta_placeholder.lower()
                or field_lower in ta_id.lower()
                or field_lower in ta_aria_label.lower()
                or field_lower in ta_label.lower()
            ):
                display = (
                    ta_label
                    or ta_aria_label
                    or ta_id
                    or ta_name
                    or ta_placeholder
                )
                return True, display

        except Exception:
            continue

    return False, ""


def find_select_field(page: Page, field_text: str) -> tuple[bool, str]:
    """Try to find a select element by field name.

    Args:
        page: Playwright Page object.
        field_text: The field text from the LLM.

    Returns:
        (success, select_name_or_empty) tuple.
    """
    selects = page.locator("select")
    for sel in selects.all()[:20]:
        try:
            sel_name = sel.get_attribute("name") or ""
            if field_text.lower() in sel_name.lower():
                return True, sel_name
        except Exception:
            continue
    return False, ""


def click_select_option(
    page: Page, select_name: str, option_text: str
) -> tuple[bool, str]:
    """Find a select by name and click the matching option.

    Args:
        page: Playwright Page object.
        select_name: The select element name attribute.
        option_text: The option text to click.

    Returns:
        (success, result_message) tuple.
    """
    selects = page.locator("select")
    for sel in selects.all()[:20]:
        try:
            sel_name = sel.get_attribute("name") or ""
            if select_name.lower() == sel_name.lower():
                options = sel.locator("option")
                for opt in options.all()[:50]:
                    try:
                        opt_text = opt.inner_text(timeout=500).strip()
                        if option_text.lower() in opt_text.lower():
                            opt.click(timeout=5000)
                            return (
                                True,
                                f"Selected option '{opt_text}' in select '{sel_name}'",
                            )
                    except Exception:
                        continue
                return True, f"Option '{option_text}' not found in select '{sel_name}'"
        except Exception:
            continue
    return False, f"Could not find select field matching: {select_name}"
