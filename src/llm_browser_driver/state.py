"""Page state extraction for LLM Browser Driver.

Extracts comprehensive page state that the LLM uses to understand the current
page and decide the next action. Captures:

- Form inputs (type, name, placeholder, value, disabled, readonly)
- Textareas (name, placeholder, value, disabled)
- Buttons (text, aria-label, disabled)
- Links (text, href, aria-label, target)
- Selects with options (name, options, selected)
- Form field labels (for/data-for → text mapping)
- Images (alt, src, aria-label)
- Disabled elements (tag, type, name, text)
- Accessibility tree (role, name, expanded, disabled per node)
- Console errors/warnings (type, text)
- HTML snippet (top 2KB of body)
- Viewport dimensions

This is extracted from `09_interactive_exploration.py` (lines 36–351, 861–901)
and adapted into a reusable module.
"""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Page


def extract_visible_text(locator: Any) -> list[str]:
    """Extract visible text from a Playwright locator.

    Args:
        locator: A Playwright locator object.

    Returns:
        List of visible text strings, stripped and filtered.
    """
    texts = []
    try:
        for el in locator.all():
            try:
                text = el.inner_text(timeout=1000).strip()
                if text:
                    texts.append(text)
            except Exception:
                pass
    except Exception:
        pass
    return texts


def extract_inputs(page: Page) -> list[dict[str, Any]]:
    """Extract input field details.

    Args:
        page: Playwright Page object.

    Returns:
        List of input field dicts with type, name, placeholder, aria-label,
        id, disabled, readonly, value.
    """
    inputs = []
    for el in page.locator(
        "input:not([type=hidden]):not([type=submit]):not([type=button])"
    ).all():
        try:
            info = {
                "type": el.get_attribute("type") or "text",
                "name": el.get_attribute("name") or "",
                "placeholder": el.get_attribute("placeholder") or "",
                "aria_label": el.get_attribute("aria-label") or "",
                "id": el.get_attribute("id") or "",
                "disabled": el.is_disabled(),
                "readonly": el.get_attribute("readonly") is not None,
                "value": el.get_attribute("value") or "",
            }
            inputs.append(info)
        except Exception:
            pass
    return inputs


def extract_textareas(page: Page) -> list[dict[str, Any]]:
    """Extract textarea details.

    Args:
        page: Playwright Page object.

    Returns:
        List of textarea dicts with name, placeholder, aria-label, id,
        disabled, rows, value.
    """
    textareas = []
    for el in page.locator("textarea").all():
        try:
            info = {
                "name": el.get_attribute("name") or "",
                "placeholder": el.get_attribute("placeholder") or "",
                "aria_label": el.get_attribute("aria-label") or "",
                "id": el.get_attribute("id") or "",
                "disabled": el.is_disabled(),
                "rows": el.get_attribute("rows") or "",
                "value": el.inner_text(timeout=500).strip(),
            }
            textareas.append(info)
        except Exception:
            pass
    return textareas


def extract_buttons(page: Page) -> list[dict[str, Any]]:
    """Extract button details.

    Args:
        page: Playwright Page object.

    Returns:
        List of button dicts with text, aria-label, type, disabled, role.
    """
    buttons = []
    for el in page.locator("button, [role=button]").all():
        try:
            text = extract_visible_text(el)
            info = {
                "text": text[0] if text else "(no visible text)",
                "aria_label": el.get_attribute("aria-label") or "",
                "type": el.get_attribute("type") or "",
                "disabled": el.is_disabled(),
                "role": el.get_attribute("role") or "",
            }
            buttons.append(info)
        except Exception:
            pass
    return buttons


def extract_links(page: Page) -> list[dict[str, Any]]:
    """Extract link details.

    Args:
        page: Playwright Page object.

    Returns:
        List of link dicts with text, href, aria-label, target.
    """
    links = []
    for el in page.locator('a[href]:not([role=button])').all():
        try:
            text = extract_visible_text(el)
            info = {
                "text": text[0] if text else "(no visible text)",
                "href": el.get_attribute("href") or "",
                "aria_label": el.get_attribute("aria-label") or "",
                "target": el.get_attribute("target") or "",
            }
            links.append(info)
        except Exception:
            pass
    return links


def extract_selects(page: Page) -> list[dict[str, Any]]:
    """Extract select dropdown details with options.

    Args:
        page: Playwright Page object.

    Returns:
        List of select dicts with name, id, disabled, and options array.
    """
    selects = []
    for el in page.locator("select").all():
        try:
            options = []
            for opt in el.locator("option").all():
                try:
                    opt_info = {
                        "text": opt.inner_text(timeout=500).strip(),
                        "value": opt.get_attribute("value") or "",
                        "selected": opt.is_checked(),
                    }
                    options.append(opt_info)
                except Exception:
                    pass
            info = {
                "name": el.get_attribute("name") or "",
                "id": el.get_attribute("id") or "",
                "disabled": el.is_disabled(),
                "options": options[:10],  # Limit to avoid huge payloads
            }
            selects.append(info)
        except Exception:
            pass
    return selects


def extract_form_fields(page: Page) -> list[dict[str, Any]]:
    """Extract form field labels.

    Handles three label patterns:
    - label[for="id"] → text (standard)
    - label[data-for="id"] → text (React-style)
    - input/textarea/select with aria-labelledby → text

    Args:
        page: Playwright Page object.

    Returns:
        List of label dicts with for/data_for/aria_labelledby → text mapping.
    """
    fields = []

    # Standard label[for="id"]
    for label in page.locator("label[for]").all():
        try:
            info = {
                "text": label.inner_text(timeout=500).strip(),
                "for": label.get_attribute("for"),
            }
            fields.append(info)
        except Exception:
            pass

    # React-style label[data-for="id"]
    for label in page.locator("label[data-for]").all():
        try:
            info = {
                "text": label.inner_text(timeout=500).strip(),
                "data_for": label.get_attribute("data-for"),
            }
            fields.append(info)
        except Exception:
            pass

    # aria-labelledby references
    for el in page.locator(
        'input[aria-labelledby], textarea[aria-labelledby], select[aria-labelledby]'
    ).all():
        try:
            info = {
                "aria_labelledby": el.get_attribute("aria-labelledby"),
                "type": el.get_attribute("type") or "unknown",
                "name": el.get_attribute("name") or "",
            }
            fields.append(info)
        except Exception:
            pass

    return fields


def extract_disabled_elements(page: Page) -> list[dict[str, Any]]:
    """Extract disabled interactive elements.

    Args:
        page: Playwright Page object.

    Returns:
        List of disabled element dicts with tag, type, name, text.
    """
    disabled = []
    for el in page.locator(
        "input:disabled, textarea:disabled, button:disabled, select:disabled"
    ).all():
        try:
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            info = {
                "tag": tag,
                "type": el.get_attribute("type") or "",
                "name": el.get_attribute("name") or "",
                "text": extract_visible_text(el)[0] if extract_visible_text(el) else "",
            }
            disabled.append(info)
        except Exception:
            pass
    return disabled


def extract_html_snippet(page: Page, max_bytes: int = 2048) -> str:
    """Extract top portion of body HTML for DOM structure context.

    Args:
        page: Playwright Page object.
        max_bytes: Maximum bytes to extract (default 2048).

    Returns:
        String of body HTML, limited to max_bytes.
    """
    try:
        html = page.evaluate(f"""() => {{
            const body = document.querySelector('body');
            if (!body) return '';
            const html = body.innerHTML;
            let bytes = 0;
            let result = '';
            for (const ch of html) {{
                const len = new TextEncoder().encode(ch).length;
                if (bytes + len > {max_bytes}) break;
                result += ch;
                bytes += len;
            }}
            return result;
        }}""")
        return html if html else ""
    except Exception:
        return ""


def extract_accessibility_tree(page: Page) -> dict[str, Any]:
    """Get Playwright's accessibility tree snapshot.

    Tries the native accessibility.snapshot() first, falls back to
    a custom TreeWalker implementation if unavailable.

    Args:
        page: Playwright Page object.

    Returns:
        Dict with accessibility tree children (role, name, expanded, disabled).
    """
    # Try Playwright's native accessibility API first
    try:
        if hasattr(page, 'accessibility') and callable(getattr(page, 'accessibility')):
            snapshot = page.accessibility.snapshot()
            return json.loads(json.dumps(snapshot, default=str))
    except Exception:
        pass

    # Fallback: custom TreeWalker
    try:
        tree = page.evaluate("""() => {
            const nodes = [];
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_ELEMENT,
                null,
                false
            );
            let node;
            while (node = walker.nextNode()) {
                const role = node.getAttribute('role') || node.tagName.toLowerCase();
                const name = node.getAttribute('aria-label')
                    || node.getAttribute('aria-labelledby')
                    || node.innerText?.trim() || '';
                const expanded = node.getAttribute('aria-expanded');
                const disabled = node.getAttribute('aria-disabled');
                if (name || (role !== 'span' && role !== 'div'
                    && role !== 'p' && role !== 'a' && role !== 'button')) {
                    nodes.push({
                        role: role,
                        name: name.substring(0, 200),
                        expanded: expanded,
                        disabled: disabled,
                        tag: node.tagName.toLowerCase()
                    });
                }
            }
            return nodes;
        }""")
        return {"method": "fallback", "children": tree or []}
    except Exception as e:
        return {"error": str(e)}


def extract_console_messages(page: Page) -> list[dict[str, str]]:
    """Capture console errors and warnings during page load.

    Sets up a console event listener that captures error and warning
    messages until explicitly removed.

    Args:
        page: Playwright Page object.

    Returns:
        List of console message dicts with type and text.
    """
    container: dict[str, list] = {"messages": []}

    def handle_console(msg: Any) -> None:
        try:
            msg_type = str(msg.type)
            msg_text = str(msg.text)
            if msg_type in ("error", "warning"):
                container["messages"].append({
                    "type": msg_type,
                    "text": msg_text,
                })
        except Exception:
            pass

    page.on("console", handle_console)
    return container["messages"]


def build_page_summary(snapshot: dict[str, Any]) -> str:
    """Build a detailed text summary for the LLM from a page state snapshot.

    Converts the structured snapshot dict into a human-readable text summary
    that the LLM can parse to understand the current page.

    Args:
        snapshot: Page state dict from get_page_state().

    Returns:
        Formatted text summary.
    """
    forms = snapshot.get("forms", {})
    details = snapshot.get("details", {})
    console = snapshot.get("console", [])

    sections = []
    sections.append(f"PAGE: {snapshot['title']}")
    sections.append(f"URL: {snapshot['url']}")
    sections.append(f"Viewport: {json.dumps(snapshot.get('viewport', {}))}")
    sections.append(f"\n--- ELEMENT COUNTS ---")
    sections.append(
        f"Inputs: {forms.get('input_count', 0)}, "
        f"Textareas: {forms.get('textarea_count', 0)}"
    )
    sections.append(
        f"Buttons: {forms.get('button_count', 0)}, "
        f"Links: {len(details.get('links', []))}"
    )
    sections.append(
        f"Images: {forms.get('image_count', 0)}, "
        f"Disabled: {forms.get('disabled_count', 0)}"
    )
    sections.append(
        f"Form fields with labels: {len(details.get('form_fields', []))}"
    )
    sections.append(f"Selects: {len(details.get('selects', []))}")

    # Inputs detail
    if details.get("inputs"):
        sections.append(f"\n--- INPUTS ---")
        for inp in details["inputs"][:20]:
            sections.append(
                f"  type={inp['type']}, name={inp['name']}, "
                f"placeholder={inp['placeholder']}, aria-label={inp['aria_label']}, "
                f"disabled={inp['disabled']}, value={inp['value']}"
            )

    # Buttons detail
    if details.get("buttons"):
        sections.append(f"\n--- BUTTONS ---")
        for btn in details["buttons"][:20]:
            sections.append(
                f"  text='{btn['text']}', "
                f"aria-label={btn['aria_label']}, "
                f"disabled={btn['disabled']}"
            )

    # Links detail
    if details.get("links"):
        sections.append(f"\n--- LINKS ---")
        for link in details["links"][:20]:
            sections.append(f"  text='{link['text']}', href={link['href']}")

    # Selects detail
    if details.get("selects"):
        sections.append(f"\n--- SELECTS ---")
        for sel in details["selects"][:10]:
            sections.append(
                f"  name={sel['name']}, disabled={sel['disabled']}"
            )
            for opt in sel.get("options", [])[:5]:
                sections.append(
                    f"    option: {opt['text']} "
                    f"(value={opt['value']}, selected={opt['selected']})"
                )

    # Form field labels
    if details.get("form_fields"):
        sections.append(f"\n--- FORM LABELS ---")
        for lbl in details["form_fields"][:20]:
            key = list(lbl.keys())[0]
            for_key = lbl.get(
                "for",
                lbl.get("data_for", lbl.get("aria_labelledby", "unknown"))
            )
            sections.append(
                f"  for={for_key}, label='{lbl.get('text', '')}'"
            )

    # Console errors
    if console:
        sections.append(
            f"\n--- CONSOLE ERRORS/WARNINGS ({len(console)}) ---"
        )
        for msg in console[:10]:
            sections.append(f"  [{msg['type']}] {msg['text']}")

    # Accessibility tree summary
    a11y = snapshot.get("accessibility_tree", {})
    if a11y and isinstance(a11y, dict):
        children = a11y.get("children", [])
        if children:
            sections.append(
                f"\n--- ACCESSIBILITY TREE ({len(children)} nodes) ---"
            )
            for node in children[:20]:
                name = node.get("name", "")
                role = node.get("role", "")
                if name or role:
                    sections.append(f"  role={role}, name='{name[:80]}'")

    return "\n".join(sections)


def build_action_history_summary(action_history: list[dict[str, Any]]) -> str:
    """Build a text summary of actions taken so far for the LLM prompt.

    Only includes the last 10 actions to keep prompts concise.

    Args:
        action_history: List of action records from the exploration loop.

    Returns:
        Text summary with numbered actions.
    """
    if not action_history:
        return "No actions taken yet."

    lines = []
    lines.append("ACTION HISTORY:")
    for i, action in enumerate(action_history[-10:], 1):
        lines.append(f"  {i}. {action['action']} → {action['result'][:100]}")

    if len(action_history) > 10:
        lines.append(f"  ... ({len(action_history) - 10} more actions omitted)")

    return "\n".join(lines)


def get_page_state(page: Page) -> dict[str, Any]:
    """Capture comprehensive page state.

    This is the main entry point for page state extraction. It orchestrates
    all individual extractors and returns a single structured dict.

    Args:
        page: Playwright Page object.

    Returns:
        Page state dict with title, url, viewport, forms, details, html_snippet,
        accessibility_tree, and console messages.
    """
    title = page.title()
    url = page.url

    inputs = page.locator("input:not([type=hidden]):not([type=submit]):not([type=button])")
    textareas = page.locator("textarea")
    buttons = page.locator("button, [role=button]")
    dropdowns = page.locator("select, [role=combobox], [role=listbox]")
    disabled = page.locator(
        "input:disabled, textarea:disabled, button:disabled, select:disabled"
    )
    images = page.locator("img")

    forms = {
        "input_count": len(inputs.all()),
        "textarea_count": len(textareas.all()),
        "button_count": len(buttons.all()),
        "dropdown_count": len(dropdowns.all()),
        "disabled_count": len(disabled.all()),
        "image_count": len(images.all()),
    }

    details = {
        "inputs": extract_inputs(page),
        "textareas": extract_textareas(page),
        "buttons": extract_buttons(page),
        "links": extract_links(page),
        "images": extract_visible_text(page.locator("img")),
        "selects": extract_selects(page),
        "form_fields": extract_form_fields(page),
        "disabled_elements": extract_disabled_elements(page),
    }

    html = extract_html_snippet(page)

    a11y = extract_accessibility_tree(page)
    console = extract_console_messages(page)

    viewport = {
        "width": page.viewport_size.get("width", 0) if page.viewport_size else 0,
        "height": page.viewport_size.get("height", 0) if page.viewport_size else 0,
    }

    return {
        "title": title,
        "url": url,
        "viewport": viewport,
        "forms": forms,
        "details": details,
        "html_snippet": html[:500] if html else "",
        "accessibility_tree": a11y,
        "console": console,
    }
