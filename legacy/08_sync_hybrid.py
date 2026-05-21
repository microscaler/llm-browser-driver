#!/usr/bin/env python3
"""P0: Richer page state extraction for exploratory testing.

Captures significantly more context than just element counts:
- Visible text from all interactive elements
- ARIA labels, titles, alt text
- Form field labels (via label[for], label[data-for], aria-label)
- Button/link text with positions
- Full HTML snippet (top 2KB of body)
- Playwright accessibility tree snapshot
- Console errors and warnings
- Page dimensions and viewport info
"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from openai import OpenAI

FRONTEND_URL = "http://localhost:7174"
LLM_API_URL = "http://192.168.1.104:8000/v1"
LLM_MODEL = "qwen3"


def extract_visible_text(locator):
    """Extract visible text from a Playwright locator."""
    elements = locator.all()
    texts = []
    for el in elements:
        try:
            text = el.inner_text(timeout=1000).strip()
            if text:
                texts.append(text)
        except Exception:
            pass
    return texts


def extract_element_details(page):
    """Extract detailed information from interactive elements."""
    details = {
        "inputs": [],
        "textareas": [],
        "buttons": [],
        "links": [],
        "images": [],
        "form_fields": [],
        "disabled_elements": [],
    }

    # --- Inputs ---
    for el in page.locator("input:not([type=hidden]):not([type=submit]):not([type=button])").all():
        try:
            info = {
                "type": el.get_attribute("type") or "text",
                "name": el.get_attribute("name") or "",
                "placeholder": el.get_attribute("placeholder") or "",
                "aria_label": el.get_attribute("aria-label") or "",
                "id": el.get_attribute("id") or "",
                "disabled": el.is_disabled(),
                "readonly": el.is_readonly(),
            }
            details["inputs"].append(info)
        except Exception:
            pass

    # --- Textareas ---
    for el in page.locator("textarea").all():
        try:
            info = {
                "name": el.get_attribute("name") or "",
                "placeholder": el.get_attribute("placeholder") or "",
                "aria_label": el.get_attribute("aria-label") or "",
                "id": el.get_attribute("id") or "",
                "disabled": el.is_disabled(),
                "rows": el.get_attribute("rows") or "",
            }
            details["textareas"].append(info)
        except Exception:
            pass

    # --- Buttons ---
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
            details["buttons"].append(info)
        except Exception:
            pass

    # --- Links ---
    for el in page.locator('a[href]:not([role=button])').all():
        try:
            text = extract_visible_text(el)
            info = {
                "text": text[0] if text else "(no visible text)",
                "href": el.get_attribute("href") or "",
                "aria_label": el.get_attribute("aria-label") or "",
            }
            details["links"].append(info)
        except Exception:
            pass

    # --- Images ---
    for el in page.locator("img").all():
        try:
            info = {
                "alt": el.get_attribute("alt") or "",
                "src": el.get_attribute("src") or "",
                "aria_label": el.get_attribute("aria-label") or "",
            }
            details["images"].append(info)
        except Exception:
            pass

    # --- Form field labels ---
    # label[for="..."]
    for label in page.locator("label[for]").all():
        try:
            info = {
                "text": label.inner_text(timeout=500).strip(),
                "for": label.get_attribute("for"),
            }
            details["form_fields"].append(info)
        except Exception:
            pass

    # label[data-for="..."] (custom pattern)
    for label in page.locator("label[data-for]").all():
        try:
            info = {
                "text": label.inner_text(timeout=500).strip(),
                "data_for": label.get_attribute("data-for"),
            }
            details["form_fields"].append(info)
        except Exception:
            pass

    # Inputs/textareas with aria-labelledby pointing to another element
    for el in page.locator('input[aria-labelledby], textarea[aria-labelledby], select[aria-labelledby]').all():
        try:
            info = {
                "aria_labelledby": el.get_attribute("aria-labelledby"),
                "type": el.get_attribute("type") or "unknown",
                "name": el.get_attribute("name") or "",
            }
            details["form_fields"].append(info)
        except Exception:
            pass

    # --- Disabled elements ---
    for el in page.locator("input:disabled, textarea:disabled, button:disabled, select:disabled").all():
        try:
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            info = {
                "tag": tag,
                "type": el.get_attribute("type") or "",
                "name": el.get_attribute("name") or "",
                "text": extract_visible_text(el)[0] if extract_visible_text(el) else "",
            }
            details["disabled_elements"].append(info)
        except Exception:
            pass

    return details


def extract_html_snippet(page, max_bytes=2048):
    """Extract top portion of body HTML for DOM structure context."""
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


def extract_accessibility_tree(page):
    """Get Playwright's accessibility tree snapshot via evaluate (some versions lack page.accessibility)."""
    try:
        # Try the built-in method first
        if hasattr(page, 'accessibility') and callable(getattr(page, 'accessibility')):
            snapshot = page.accessibility.snapshot()
            return json.loads(json.dumps(snapshot, default=str))
    except Exception:
        pass
    
    # Fallback: extract ARIA-related elements via JS
    try:
        tree = page.evaluate("""() => {
            const nodes = [];
            // Walk DOM and collect accessible elements
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            let node;
            while (node = walker.nextNode()) {
                const role = node.getAttribute('role') || node.tagName.toLowerCase();
                const name = node.getAttribute('aria-label') || node.getAttribute('aria-labelledby') || node.innerText?.trim() || '';
                const expanded = node.getAttribute('aria-expanded');
                const disabled = node.getAttribute('aria-disabled');
                if (name || role !== 'span' && role !== 'div' && role !== 'p' && role !== 'a' && role !== 'button') {
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


def extract_console_during_navigation(page):
    """Capture console errors/warnings during page load.
    
    Uses the page context manager pattern so we can collect messages
    that fire during navigation. Returns a list of {type, text} dicts.
    """
    container = {"messages": []}
    
    def handle_console(msg):
        try:
            # msg.type and msg.text are string properties on ConsoleMessage
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


def build_prompt(snapshot):
    """Build a detailed prompt for the LLM with rich page context."""
    
    forms = snapshot["forms"]
    details = snapshot["details"]
    console = snapshot["console"]
    a11y = snapshot.get("accessibility_tree", {})
    
    sections = []
    
    # 1. Page metadata
    sections.append(f"PAGE: {snapshot['title']}")
    sections.append(f"URL: {snapshot['url']}")
    sections.append(f"Viewport: {json.dumps(snapshot['viewport'])}")
    
    # 2. Element counts
    sections.append(f"\n--- ELEMENT COUNTS ---")
    sections.append(f"Inputs: {forms['input_count']}, Textareas: {forms['textarea_count']}")
    sections.append(f"Buttons: {forms['button_count']}, Links: {len(details.get('links', []))}")
    sections.append(f"Images: {forms['image_count']}, Disabled: {forms['disabled_count']}")
    sections.append(f"Form fields with labels: {len(details.get('form_fields', []))}")
    
    # 3. Input details
    if details.get("inputs"):
        sections.append(f"\n--- INPUTS ---")
        for inp in details["inputs"][:20]:
            sections.append(
                f"  type={inp['type']}, name={inp['name']}, "
                f"placeholder={inp['placeholder']}, aria-label={inp['aria_label']}, "
                f"disabled={inp['disabled']}"
            )
    
    # 4. Button/link text
    if details.get("buttons"):
        sections.append(f"\n--- BUTTONS ---")
        for btn in details["buttons"][:20]:
            sections.append(f"  text='{btn['text']}', aria-label={btn['aria_label']}, disabled={btn['disabled']}")
    
    if details.get("links"):
        sections.append(f"\n--- LINKS ---")
        for link in details["links"][:20]:
            sections.append(f"  text='{link['text']}', href={link['href']}")
    
    # 5. Images (alt text)
    if details.get("images"):
        sections.append(f"\n--- IMAGES ---")
        for img in details["images"][:10]:
            sections.append(f"  alt='{img['alt']}', src={img['src'][:80] if img['src'] else ''}")
    
    # 6. Form field labels
    if details.get("form_fields"):
        sections.append(f"\n--- FORM LABELS ---")
        for lbl in details["form_fields"][:20]:
            key = list(lbl.keys())[0]
            sections.append(f"  for={lbl.get('for', lbl.get('data_for', lbl.get('aria_labelledby', 'unknown')))}, label='{lbl['text']}'")
    
    # 7. Disabled elements
    if details.get("disabled_elements"):
        sections.append(f"\n--- DISABLED ELEMENTS ---")
        for d in details["disabled_elements"][:10]:
            sections.append(f"  {d['tag']}(name={d['name']}, type={d['type']}, text='{d['text']}')")
    
    # 8. Console errors
    if console:
        sections.append(f"\n--- CONSOLE ERRORS/WARNINGS ({len(console)}) ---")
        for msg in console[:10]:
            sections.append(f"  [{msg['type']}] {msg['text']}")
    
    # 9. Accessibility tree (summarized)
    if a11y and isinstance(a11y, dict):
        children = a11y.get("children", [])
        if children:
            sections.append(f"\n--- ACCESSIBILITY TREE (top {min(len(children), 30)} nodes) ---")
            for node in children[:30]:
                name = node.get("name", "")
                role = node.get("role", "")
                if name or role:
                    sections.append(f"  role={role}, name='{name[:100]}'")
    
    return "\n".join(sections)


SYSTEM_PROMPT = """You are a QA analyst performing exploratory testing on a web application.
Analyze the page state and report any UX issues, accessibility problems, broken forms, or missing functionality.

Be specific and actionable. For each finding, include:
- SEVERITY: CRITICAL (breaks core functionality), WARNING (poor UX), or INFO (suggestion)
- WHAT: A clear description of the issue
- WHERE: Which element or section is affected
- WHY: Why it's a problem
- SUGGEST: What should be there instead

Focus on:
1. Missing interactive elements (inputs, buttons, dropdowns) where expected
2. Disabled elements that should be enabled
3. Form fields without labels (accessibility issue)
4. Empty alt text on images (accessibility issue)
5. Buttons/links with no visible text
6. Console errors that indicate broken functionality
7. Unexpected state changes or loading indicators
8. Missing ARIA labels for interactive elements
9. Incomplete form wizards (missing steps, broken navigation)
10. Data display issues (empty tables, missing pagination)
"""

USER_PROMPT_TEMPLATE = """TASK: {task_desc}

{page_summary}
"""


def analyze_with_llm(client, model, snapshot, task_desc, progress_file):
    """Call LLM for analysis with rich page context.
    
    Streams the response so we can see partial output in real-time.
    Also writes progress markers to `progress_file` for Hermes `process` tool to poll.
    """
    import time
    start = time.time()
    print(f"\n  [LLM] Starting analysis for {task_desc}...", flush=True)
    progress_file.write(f"ANALYZING: {task_desc}\n")
    progress_file.flush()
    try:
        page_summary = build_prompt(snapshot)
        user_prompt = USER_PROMPT_TEMPLATE.format(task_desc=task_desc, page_summary=page_summary)
        
        # Use streaming so we get partial output instead of waiting 30s blind
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2048,
            temperature=0.3,
            stream=True,  # <-- key: stream the response
        )
        
        full_content = ""
        full_reasoning = ""
        chunk_count = 0
        for chunk in response:
            chunk_count += 1
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                # Qwen3 streams text in `reasoning` field, not `content`
                if hasattr(delta, 'reasoning') and delta.reasoning:
                    full_reasoning += delta.reasoning
                if hasattr(delta, 'content') and delta.content:
                    full_content += delta.content
                # Write partial progress every N chunks so Hermes can poll it
                if chunk_count % 5 == 0:
                    total_chars = len(full_content) + len(full_reasoning)
                    progress_file.write(f"STREAMING: {task_desc} ({total_chars} chars, reasoning={len(full_reasoning)} chars)\n")
                    progress_file.flush()
        
        # Prefer reasoning field (Qwen3) or fall back to content
        result = full_reasoning.strip() or full_content.strip()
        
        elapsed = time.time() - start
        print(f"  [LLM] Done: {chunk_count} chunks, {len(full_content)} content chars, {len(full_reasoning)} reasoning chars, result={len(result)} chars in {elapsed:.1f}s", flush=True)
        progress_file.write(f"COMPLETED: {task_desc} ({elapsed:.1f}s, {chunk_count} chunks, reasoning={len(full_reasoning)} chars)\n")
        progress_file.flush()
        
        if not result:
            print(f"  [LLM] WARNING: No content or reasoning in stream", flush=True)
            progress_file.write(f"WARNING: {task_desc} — empty stream\n")
            progress_file.flush()
            return "[LLM returned empty response]"
        
        return result
    
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [LLM] Failed after {elapsed:.1f}s: {type(e).__name__}: {e}", flush=True)
        progress_file.write(f"FAILED: {task_desc} — {e}\n")
        progress_file.flush()
        return f"[LLM ERROR]: {type(e).__name__}: {e}"


def get_page_state(page, console_container):
    """Capture comprehensive page state synchronously."""
    title = page.title()
    url = page.url
    
    # --- Element counts ---
    inputs = page.locator("input:not([type=hidden]):not([type=submit]):not([type=button])")
    textareas = page.locator("textarea")
    buttons = page.locator("button, [role=button]")
    dropdowns = page.locator("select, [role=combobox], [role=listbox]")
    disabled = page.locator("input:disabled, textarea:disabled, button:disabled, select:disabled")
    images = page.locator("img")
    
    forms = {
        "input_count": len(inputs.all()),
        "textarea_count": len(textareas.all()),
        "button_count": len(buttons.all()),
        "dropdown_count": len(dropdowns.all()),
        "disabled_count": len(disabled.all()),
        "image_count": len(images.all()),
    }
    
    # --- Detailed element extraction ---
    details = extract_element_details(page)
    
    # --- HTML snippet ---
    html = extract_html_snippet(page, max_bytes=2048)
    
    # --- Accessibility tree ---
    a11y = extract_accessibility_tree(page)
    
    # --- Console messages (from pre-set listener) ---
    console = console_container.get("messages", []) if isinstance(console_container, dict) else []
    
    # --- Viewport info ---
    viewport = {
        "width": page.viewport_size["width"] if page.viewport_size else 0,
        "height": page.viewport_size["height"] if page.viewport_size else 0,
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


def run_test(browser_engine, browser, test):
    """Run a single exploratory test against a URL."""
    print(f"  Navigating...")
    page = browser.new_page()
    console_container = extract_console_during_navigation(page)
    
    try:
        page.goto(test["url"], wait_until="domcontentloaded", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)
        
        state = get_page_state(page, console_container)
        print(f"  Title: {state['title']}")
        print(f"  Forms: {json.dumps(state['forms'])}")
        print(f"  Form fields with labels: {len(state['details'].get('form_fields', []))}")
        print(f"  Console errors: {len(state['console'])}")
        
        return {
            "test": test["name"],
            "url": test["url"],
            "status": "success",
            "snapshot": state,
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        return {
            "test": test["name"],
            "url": test["url"],
            "status": "error",
            "error": str(e),
        }
    finally:
        page.close()


def run_tests(browser_engine, browser):
    """Run exploratory tests against a list of URLs."""
    tests = [
        {"name": "Homepage", "url": FRONTEND_URL, "task": "Analyze the homepage for UX issues, missing search/filter functionality, and overall landing page quality"},
        {"name": "Post a Job", "url": FRONTEND_URL + "/shipper/post-a-job", "task": "Analyze the post-a-job form wizard for completeness, label coverage, disabled state issues, and form field labeling"},
        {"name": "Job List", "url": FRONTEND_URL + "/shipper/my-jobs", "task": "Analyze the job list page for data display, empty states, missing data elements, and table/list accessibility"},
        {"name": "Login", "url": FRONTEND_URL + "/login", "task": "Analyze the login page for form completeness, missing fields, and accessibility"},
        {"name": "Register", "url": FRONTEND_URL + "/register", "task": "Analyze the registration form for completeness, label coverage, and form field validation UI"},
    ]
    
    results = []
    for i, test in enumerate(tests):
        print(f"\n{'='*60}")
        print(f"TEST {i+1}/{len(tests)}: {test['name']}")
        print(f"URL: {test['url']}")
        print('='*60)
        
        result = run_test(browser_engine, browser, test)
        results.append(result)
    
    return results


def main():
    print("Starting browser...")
    browser_engine = sync_playwright().start()
    browser = browser_engine.chromium.launch(headless=True)
    
    results = run_tests(browser_engine, browser)
    browser.close()
    browser_engine.stop()
    print("\nBrowser closed.")
    
    # LLM analysis with progress monitoring
    print("\n\n=== LLM ANALYSIS ===")
    progress_fp = open("progress.txt", "w")
    progress_fp.write("READY")
    progress_fp.flush()
    
    client = OpenAI(
        base_url=LLM_API_URL,
        api_key="placeholder",
        timeout=300.0,
    )
    
    completed = 0
    total = sum(1 for r in results if r["status"] == "success")
    
    for result in results:
        if result["status"] != "success":
            continue
        
        snapshot = result["snapshot"]
        print(f"\n--- {result['test']} ({completed+1}/{total}) ---")
        
        llm_text = analyze_with_llm(
            client, LLM_MODEL, snapshot, result["test"], progress_fp
        )
        result["llm_analysis"] = llm_text
        print(llm_text)
        completed += 1
    progress_fp.close()
    
    # Save results
    output_path = Path("exploratory_results_p0.json")
    output_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n\nResults saved to {output_path}")
    
    # Print summary statistics
    print("\n\n=== SUMMARY ===")
    total_inputs = 0
    total_buttons = 0
    total_labels = 0
    total_console_errors = 0
    
    for result in results:
        if result["status"] != "success":
            continue
        forms = result["snapshot"]["forms"]
        total_inputs += forms["input_count"] + forms["textarea_count"]
        total_buttons += forms["button_count"]
        total_labels += len(result["snapshot"]["details"].get("form_fields", []))
        total_console_errors += len(result["snapshot"]["console"])
    
    print(f"Pages analyzed: {sum(1 for r in results if r['status'] == 'success')}")
    print(f"Total form elements (inputs+textareas): {total_inputs}")
    print(f"Total buttons: {total_buttons}")
    print(f"Total labeled form fields: {total_labels}")
    print(f"Total console errors across all pages: {total_console_errors}")
    pages_with_errors = [r for r in results if r['status'] == 'success' and r['snapshot']['console']]
    print(f"Pages with console errors: {len(pages_with_errors)}")
    if pages_with_errors:
        for p in pages_with_errors:
            print(f"  - {p['test']}: {len(p['snapshot']['console'])} errors")


if __name__ == "__main__":
    main()
