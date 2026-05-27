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


def _get_field_label(page: Page, field_el) -> str:
    """Get the display label for a form field by checking label[for], label[data-for],
    or the nearest <label> sibling/ancestor (SolidJS pattern).

    Args:
        page: Playwright Page object.
        field_el: Playwright element handle.

    Returns:
        Label text string, or empty string.
    """
    # Try label[for="id"]
    inp_id_attr = field_el.get_attribute("id") or ""
    if inp_id_attr:
        label_el = page.locator(f"label[for='{inp_id_attr}']")
        if label_el.count() > 0:
            return label_el.first.inner_text(timeout=500).strip()
        label_el = page.locator(f"label[data-for='{inp_id_attr}']")
        if label_el.count() > 0:
            return label_el.first.inner_text(timeout=500).strip()

    # Try label[data-for] where data-for matches field data-testid
    testid = field_el.get_attribute("data-testid") or ""
    if testid:
        label_el = page.locator(f"label[data-for='{testid}']")
        if label_el.count() > 0:
            return label_el.first.inner_text(timeout=500).strip()

    # SolidJS pattern: label is the preceding sibling or parent <label> wrapping the field
    try:
        # Check if field is wrapped in a <label>
        parent_label = field_el.evaluate_handle("el => { let p = el.parentElement; while(p) { if(p.tagName === 'LABEL') return p; p = p.parentElement; } return null; }")
        if parent_label:
            return parent_label.inner_text(timeout=500).strip()

        # Check preceding label sibling
        prev_label = field_el.evaluate_handle("el => { let p = el.previousElementSibling; while(p) { if(p.tagName === 'LABEL') return p; p = p.previousElementSibling; } return null; }")
        if prev_label:
            return prev_label.inner_text(timeout=500).strip()
    except Exception:
        pass

    return ""


def find_field(page: Page, field_text: str) -> tuple[bool, str]:
    """Try to find an input or textarea field by multiple criteria.

    Checks in priority order:
    1. data-testid match (highest confidence — matches 'input-description' for 'description')
    2. name → placeholder → id → aria-label → label[for] text → label[data-for] text
    3. Nearby label detection (SolidJS pattern where label has no for/data-for)

    Args:
        page: Playwright Page object.
        field_text: The field text from the LLM (e.g., "email", "First Name", "Description").

    Returns:
        (success, display_name_or_empty) tuple. The display name is the first
        matching identifier found (label > aria-label > id > name > placeholder).
    """
    # Strategy 1: Match by data-testid (most reliable for SolidJS forms)
    # Convert field_text to testid-friendly form: "Description" → "input-description"
    # or "pickup country" → "pickup-country"
    testid_keywords = field_text.lower().split()
    testid_patterns = []
    for kw in testid_keywords:
        if kw not in ("select", "required", "*"):
            testid_patterns.append(kw)
        else:
            testid_patterns.append("")
    testid_patterns.append(f"{testid_keywords[0] if testid_keywords else ''}")  # first word
    testid_patterns.append(f"{testid_keywords[-1] if testid_keywords else ''}")  # last word

    for pattern in [
        f"input[data-testid*='{field_text.lower().replace(' ', '-')}']",
        f"textarea[data-testid*='{field_text.lower().replace(' ', '-')}']",
        f"input[data-testid*='{field_text.lower().replace(' ', '')}']",
        f"textarea[data-testid*='{field_text.lower().replace(' ', '')}']",
        # Try with common prefixes
        f"input[data-testid='input-{field_text.lower().replace(' ', '-')}']",
        f"textarea[data-testid='input-{field_text.lower().replace(' ', '-')}']",
    ]:
        try:
            locator = page.locator(pattern)
            if locator.count() > 0:
                text = locator.first.inner_text(timeout=500).strip()
                label = _get_field_label(page, locator.first)
                display = label or text or field_text
                return True, display
        except Exception:
            continue

    # Strategy 2: Try label[for] text match first (React-style)
    try:
        labels = page.locator("label[data-for]")
        for lbl in labels.all()[:50]:
            try:
                lbl_text = lbl.inner_text(timeout=500).strip().lower()
                if field_text.lower() in lbl_text or lbl_text in field_text.lower():
                    for_val = lbl.get_attribute("data-for") or ""
                    if for_val:
                        inp = page.locator(f"#{for_val}")
                        if inp.count() > 0:
                            return True, lbl.inner_text(timeout=500).strip()
            except Exception:
                continue
    except Exception:
        pass

    # Strategy 3: Try inputs first (name → placeholder → id → aria-label → label)
    inputs = page.locator(
        "input:not([type=hidden]):not([type=submit]):not([type=button])"
    )

    for inp in inputs.all()[:50]:
        try:
            inp_name = inp.get_attribute("name") or ""
            inp_placeholder = inp.get_attribute("placeholder") or ""
            inp_id = inp.get_attribute("id") or ""
            inp_aria_label = inp.get_attribute("aria-label") or ""
            inp_testid = inp.get_attribute("data-testid") or ""

            # Get label text
            inp_label = _get_field_label(page, inp)

            field_lower = field_text.lower()
            if (
                field_lower in inp_name.lower()
                or field_lower in inp_placeholder.lower()
                or field_lower in inp_id.lower()
                or field_lower in inp_aria_label.lower()
                or field_lower in inp_label.lower()
            ):
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

    # Strategy 4: Try textareas (name → placeholder → id → aria-label → label → testid)
    textareas = page.locator("textarea")
    for ta in textareas.all()[:20]:
        try:
            ta_name = ta.get_attribute("name") or ""
            ta_placeholder = ta.get_attribute("placeholder") or ""
            ta_id = ta.get_attribute("id") or ""
            ta_aria_label = ta.get_attribute("aria-label") or ""
            ta_testid = ta.get_attribute("data-testid") or ""

            ta_label = _get_field_label(page, ta)

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
    return False, f"Could not find select field matching: {select_name}"


def find_custom_dropdown_trigger(page: Page, field_text: str) -> tuple[bool, str]:
    """Find a custom dropdown trigger button by matching its displayed text.

    Custom dropdowns use <button type='button'> with chevron styling instead of
    native <select> elements. The button's visible text is the currently selected
    value or placeholder (e.g., "Select Country", "Select State / Province").

    Selection strategy:
    1. data-testid match (highest priority)
    2. Button text contains field_text
    3. Button text is field_text

    Args:
        page: Playwright Page object.
        field_text: The field text from the LLM (e.g., "Select Country", "pickup country").

    Returns:
        (success, display_text) tuple.
    """
    # Strategy 1: Match by data-testid (most reliable)
    # Look for patterns like select-pickup-country, pickup-country, etc.
    testid_patterns = [
        f"[data-testid*='{field_text.lower().replace(' ', '-')}']",
        f"[data-testid*='{field_text.lower().replace(' ', '')}']",
    ]
    for pattern in testid_patterns:
        try:
            locator = page.locator(f"button[type='button']{pattern}")
            if locator.count() > 0:
                text = locator.first.inner_text(timeout=500).strip()
                return True, text
        except Exception:
            continue

    # Strategy 2: Search all custom dropdown triggers by text
    for el in page.locator("button[type='button']").all()[:50]:
        try:
            text = el.inner_text(timeout=500).strip()
            classes = el.get_attribute("class") or ""
            # Must be a dropdown trigger: either has fa-chevron-down on button class,
            # or has a child <i> with fa-chevron-down (SelectDropdown component pattern
            # renders the chevron as <span><i class="fas fa-chevron-down"></i></span>
            # inside the button, not on the button's own class attribute)
            has_chevron = (
                "fa-chevron-down" in classes
                # SelectDropdown renders <i class="fa-solid fa-chevron-down ..."> inside button
                or el.locator("i.fa.fa-chevron-down").count() > 0
                or el.locator("i.fa-solid.fa-chevron-down").count() > 0
                # Also handle FontAwesome 5+ syntax: i class="fas fa-chevron-down"
                or el.locator("i.fas.fa-chevron-down").count() > 0
            )
            if not has_chevron:
                continue
            # Case-insensitive text match
            if field_text.lower() in text.lower() or text.lower() in field_text.lower():
                return True, text
        except Exception:
            continue

    return False, ""


def click_custom_dropdown_option(page: Page, option_text: str) -> tuple[bool, str]:
    """Click a visible option in an open custom dropdown menu.

    Custom dropdowns render options as <ul><li class="cursor-pointer"> when open.
    This finds and clicks the matching option by text.

    Args:
        page: Playwright Page object.
        option_text: The text of the option to select.

    Returns:
        (success, result_message) tuple.
    """
    for el in page.locator("ul li.cursor-pointer").all()[:100]:
        try:
            text = el.inner_text(timeout=500).strip()
            if option_text.lower() in text.lower() or text.lower() in option_text.lower():
                el.click(timeout=5000)
                return True, f"Selected option '{text}'"
        except Exception:
            continue
    return False, f"Option '{option_text}' not found in open dropdown menu"


def click_select_option(
    page: Page, select_name: str, option_text: str
) -> tuple[bool, str]:
    """Find a select by name and select the matching option.

    Uses Playwright's select_option() API rather than clicking
    <option> elements (which aren't clickable in browsers).

    Args:
        page: Playwright Page object.
        select_name: The select element name attribute.
        option_text: The option text to select.

    Returns:
        (success, result_message) tuple.
    """
    selects = page.locator("select")
    for sel in selects.all()[:20]:
        try:
            sel_name = sel.get_attribute("name") or ""
            if select_name.lower() == sel_name.lower():
                # Find the matching option by text
                matching_option = None
                for opt in sel.locator("option").all()[:50]:
                    opt_text = opt.inner_text(timeout=500).strip()
                    if option_text.lower() in opt_text.lower():
                        matching_option = opt
                        break

                if matching_option is not None:
                    opt_text = matching_option.inner_text(timeout=500).strip()
                    # Use select_option() on the SELECT locator, passing the option label
                    sel.select_option(label=opt_text, timeout=5000)
                    return (
                        True,
                        f"Selected option '{opt_text}' in select '{sel_name}'",
                    )
                return False, f"Option '{option_text}' not found in select '{sel_name}'"
        except Exception:
            continue
    return False, f"Could not find select field matching: {select_name}"
