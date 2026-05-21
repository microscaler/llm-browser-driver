#!/usr/bin/env python3
"""P1: Interactive Exploration — LLM decides actions, agent executes them.

Playground loop:
1. LLM sees page state + action history + goal
2. LLM decides next action (click, fill, scroll, evaluate, wait, navigate)
3. Agent executes the action on the page
4. Agent captures new state + detects changes
5. Loop repeats until goal achieved or max iterations reached

This discovers bugs that static inspection can't:
- Broken click handlers
- Form validation errors
- Broken navigation
- Unexpected state changes
- Missing modal/dialog handling
"""

import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from openai import OpenAI

FRONTEND_URL = "http://localhost:7174"
LLM_API_URL = "http://192.168.1.104:8000/v1"
LLM_MODEL = "qwen3"

# Max iterations per test to prevent infinite loops
MAX_ITERATIONS = 15
MAX_TOKENS = 2048
TEMPERATURE = 0.3


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
        "selects": [],
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
                "value": el.get_attribute("value") or "",
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
                "value": el.inner_text(timeout=500).strip(),
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
                "target": el.get_attribute("target") or "",
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

    # --- Selects ---
    for el in page.locator("select").all():
        try:
            options = []
            for opt in el.locator("option").all():
                opt_info = {
                    "text": opt.inner_text(timeout=500).strip(),
                    "value": opt.get_attribute("value") or "",
                    "selected": opt.is_checked(),
                }
                options.append(opt_info)
            info = {
                "name": el.get_attribute("name") or "",
                "id": el.get_attribute("id") or "",
                "disabled": el.is_disabled(),
                "options": options[:10],  # Limit to avoid huge payloads
            }
            details["selects"].append(info)
        except Exception:
            pass

    # --- Form field labels ---
    for label in page.locator("label[for]").all():
        try:
            info = {
                "text": label.inner_text(timeout=500).strip(),
                "for": label.get_attribute("for"),
            }
            details["form_fields"].append(info)
        except Exception:
            pass

    for label in page.locator("label[data-for]").all():
        try:
            info = {
                "text": label.inner_text(timeout=500).strip(),
                "data_for": label.get_attribute("data-for"),
            }
            details["form_fields"].append(info)
        except Exception:
            pass

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
    """Get Playwright's accessibility tree snapshot via evaluate."""
    try:
        if hasattr(page, 'accessibility') and callable(getattr(page, 'accessibility')):
            snapshot = page.accessibility.snapshot()
            return json.loads(json.dumps(snapshot, default=str))
    except Exception:
        pass
    
    try:
        tree = page.evaluate("""() => {
            const nodes = [];
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
    """Capture console errors/warnings during page load."""
    container = {"messages": []}
    
    def handle_console(msg):
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


def build_page_summary(snapshot):
    """Build a detailed text summary for the LLM."""
    forms = snapshot["forms"]
    details = snapshot["details"]
    console = snapshot["console"]
    
    sections = []
    sections.append(f"PAGE: {snapshot['title']}")
    sections.append(f"URL: {snapshot['url']}")
    sections.append(f"Viewport: {json.dumps(snapshot['viewport'])}")
    sections.append(f"\n--- ELEMENT COUNTS ---")
    sections.append(f"Inputs: {forms['input_count']}, Textareas: {forms['textarea_count']}")
    sections.append(f"Buttons: {forms['button_count']}, Links: {len(details.get('links', []))}")
    sections.append(f"Images: {forms['image_count']}, Disabled: {forms['disabled_count']}")
    sections.append(f"Form fields with labels: {len(details.get('form_fields', []))}")
    sections.append(f"Selects: {len(details.get('selects', []))}")
    
    if details.get("inputs"):
        sections.append(f"\n--- INPUTS ---")
        for inp in details["inputs"][:20]:
            sections.append(
                f"  type={inp['type']}, name={inp['name']}, "
                f"placeholder={inp['placeholder']}, aria-label={inp['aria_label']}, "
                f"disabled={inp['disabled']}, value={inp['value']}"
            )
    
    if details.get("buttons"):
        sections.append(f"\n--- BUTTONS ---")
        for btn in details["buttons"][:20]:
            sections.append(f"  text='{btn['text']}', aria-label={btn['aria_label']}, disabled={btn['disabled']}")
    
    if details.get("links"):
        sections.append(f"\n--- LINKS ---")
        for link in details["links"][:20]:
            sections.append(f"  text='{link['text']}', href={link['href']}")
    
    if details.get("selects"):
        sections.append(f"\n--- SELECTS ---")
        for sel in details["selects"][:10]:
            sections.append(f"  name={sel['name']}, disabled={sel['disabled']}")
            for opt in sel.get('options', [])[:5]:
                sections.append(f"    option: {opt['text']} (value={opt['value']}, selected={opt['selected']})")
    
    if details.get("form_fields"):
        sections.append(f"\n--- FORM LABELS ---")
        for lbl in details["form_fields"][:20]:
            key = list(lbl.keys())[0]
            sections.append(f"  for={lbl.get('for', lbl.get('data_for', lbl.get('aria_labelledby', 'unknown')))}, label='{lbl['text']}'")
    
    if console:
        sections.append(f"\n--- CONSOLE ERRORS/WARNINGS ({len(console)}) ---")
        for msg in console[:10]:
            sections.append(f"  [{msg['type']}] {msg['text']}")
    
    # Accessibility tree summary
    a11y = snapshot.get("accessibility_tree", {})
    if a11y and isinstance(a11y, dict):
        children = a11y.get("children", [])
        if children:
            sections.append(f"\n--- ACCESSIBILITY TREE ({len(children)} nodes) ---")
            for node in children[:20]:
                name = node.get("name", "")
                role = node.get("role", "")
                if name or role:
                    sections.append(f"  role={role}, name='{name[:80]}'")
    
    return "\n".join(sections)


def build_action_history_summary(action_history):
    """Build a summary of actions taken so far."""
    if not action_history:
        return "No actions taken yet."
    
    lines = []
    lines.append("ACTION HISTORY:")
    for i, action in enumerate(action_history[-10:], 1):  # Last 10 actions
        lines.append(f"  {i}. {action['action']} → {action['result'][:100]}")
    
    if len(action_history) > 10:
        lines.append(f"  ... ({len(action_history) - 10} more actions omitted)")
    
    return "\n".join(lines)


INTERACTIVE_SYSTEM_PROMPT = """You are an exploratory QA agent testing a web application.
You can interact with the page by taking actions. Your goal is to thoroughly test the page for bugs.

**Your capabilities:**
- Click buttons and links
- Fill input fields and textareas
- Select options from dropdowns
- Scroll the page
- Navigate to URLs
- Wait for elements to appear
- Evaluate JavaScript
- Go back/forward in browser history

**Your workflow:**
1. Analyze the current page state
2. Decide the most useful next action to discover bugs
3. Execute the action
4. Observe the result and state changes
5. Repeat until you've tested key functionality or reached max iterations

**Action types and parameters:**
- `click`: Click an element. Parameters: `{{"action": "click", "element": "button text or link href"}}`
  - For buttons: use the button text
  - For links: use the href or link text
- `fill`: Fill an input field. Parameters: `{{"action": "fill", "field": "input name or placeholder", "value": "text to enter"}}`
- `select`: Select an option from a dropdown. Parameters: `{{"action": "select", "field": "select name", "option": "option text"}}`
- `scroll`: Scroll the page. Parameters: `{{"action": "scroll", "direction": "down" or "up", "distance": "partial" or "full"}}`
- `navigate`: Navigate to a URL. Parameters: `{{"action": "navigate", "url": "full URL"}}`
- `go_back`: Go back in browser history. Parameters: `{{"action": "go_back"}}`
- `wait`: Wait for a condition. Parameters: `{{"action": "wait", "condition": "networkidle" or "load" or "timeout:5000"}}`
- `evaluate`: Run JavaScript. Parameters: `{{"action": "evaluate", "script": "javascript expression"}}`

**Focus areas for testing:**
1. Navigation: Can you move between pages? Are links working?
2. Forms: Do inputs accept text? Are there validation errors? Do buttons work?
3. Interactive elements: Do dropdowns work? Do clickable elements trigger state changes?
4. Error states: What happens with invalid input? Empty states? Loading states?
5. Accessibility: Missing labels, disabled elements, keyboard navigation hints
6. Content: Is data displaying correctly? Are there broken images or links?

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


def decide_action(page, snapshot, action_history, goal, progress_file):
    """Have the LLM decide the next action to take."""
    import time
    start = time.time()
    
    progress_file.write(f"DECIDING action in step {len(action_history) + 1}...")
    progress_file.flush()
    
    page_summary = build_page_summary(snapshot)
    history_summary = build_action_history_summary(action_history)
    
    prompt = f"""TASK: {goal}

{history_summary}

CURRENT PAGE STATE:
{page_summary}

Based on the goal, action history, and current page state, decide the next action to take.
"""
    
    try:
        # NOTE: Must use stream=False because Qwen3 on vLLM puts streaming output
        # entirely in the reasoning field. Non-streaming correctly returns the JSON
        # answer in the content field.
        print(f"  [LLM] Making API call to {LLM_API_URL}/v1/models/{LLM_MODEL}...", flush=True)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": INTERACTIVE_SYSTEM_PROMPT.format(max_iter=MAX_ITERATIONS)},
                {"role": "user", "content": prompt},
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=False,  # Non-streaming required for Qwen3 to return JSON in content
        )
        print(f"  [LLM] API call complete", flush=True)
        
        elapsed = time.time() - start
        print(f"  [LLM] Response received in {elapsed:.1f}s", flush=True)
        
        # The JSON answer is in content (non-streaming mode)
        choice = response.choices[0]
        result = (choice.message.content or "").strip()
        print(f"  [LLM RAW] Content length: {len(result)}", flush=True)
        print(f"  [LLM RAW] Last 300 chars: {result[-300:]}", flush=True)
        
        # Parse action from the JSON response
        action = parse_action_from_response(result)
        print(f"  [LLM PARSED] Action: {action}", flush=True)
        return action
    except Exception as e:
        elapsed = time.time() - start
        import traceback
        error_str = f"{type(e).__name__}: {str(e)}"
        print(f"  [LLM] Failed after {elapsed:.1f}s: {error_str}", flush=True)
        print(f"  [LLM] Full traceback:", flush=True)
        traceback.print_exc()
        progress_file.write(f"FAILED: LLM decision failed — {error_str}\n")
        progress_file.flush()
        return {"action": "done", "summary": f"LLM error after {len(action_history)} steps: {error_str}"}
        return {"action": "done", "summary": f"LLM error after {len(action_history)} steps: {e}"}


def parse_action_from_response(response_text):
    """Parse the action JSON from LLM response text.
    
    Qwen3 outputs reasoning text (thinking) followed by the actual JSON answer.
    The JSON answer is always at the END of the response.
    
    Strategy: scan from the end to find the last { that opens a valid JSON object.
    """
    # Strategy 1: Find the last JSON object starting from the end
    # Work backwards through the text, when we find a '{', try to parse forward
    for i in range(len(response_text) - 1, -1, -1):
        if response_text[i] == '{':
            candidate = response_text[i:]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and 'action' in parsed:
                    return parsed
            except (json.JSONDecodeError, ValueError):
                continue
    
    # Strategy 2: Extract "action": "..." from anywhere in text
    action_value_match = re.search(r'"action"\s*[:\s]+["\']([^"\']+)["\']', response_text)
    if action_value_match:
        action_value = action_value_match.group(1)
        known_actions = ['click', 'fill', 'select', 'scroll', 'navigate', 'go_back', 'wait', 'evaluate', 'done', 'error']
        if action_value in known_actions:
            return {'action': action_value}
    
    # Strategy 3: Return done with summary
    if response_text.strip():
        return {'action': 'done', 'summary': f"Completed analysis: {response_text[:200]}"}
    else:
        return {'action': 'done', 'summary': 'Empty response'}


def execute_action(page, action, action_history):
    """Execute an action on the page and return the result."""
    action_type = action.get("action", "unknown")
    result = ""
    
    try:
        if action_type == "click":
            element = action.get("element", "")
            found = False
            
            # Strategy 1: Try exact id match first (most reliable)
            try:
                id_locator = page.locator(f"#{element.strip().lower().replace(' ', '-')}")
                if id_locator.count() > 0:
                    id_locator.click(timeout=5000)
                    text = id_locator.inner_text(timeout=1000).strip()
                    result = f"Clicked by id='{element.strip().lower().replace(' ', '-')}': {text[:100]}"
                    found = True
            except Exception:
                pass
            
            # Strategy 2: Try button text
            if not found:
                buttons = page.locator(f"button, [role=button]")
                for btn in buttons.all()[:50]:
                    try:
                        text = btn.inner_text(timeout=500).strip().lower()
                        if element.lower() in text or text in element.lower():
                            btn.click(timeout=5000)
                            result = f"Clicked button: {btn.inner_text(timeout=1000)[:100]}"
                            found = True
                            break
                    except Exception:
                        continue
            
            # Strategy 3: Try links
            if not found:
                links = page.locator('a[href]')
                for link in links.all()[:50]:
                    try:
                        href = link.get_attribute("href") or ""
                        text = link.inner_text(timeout=500).strip().lower()
                        if element.lower() in text or element.lower() in href.lower() or text in element.lower():
                            link.click(timeout=5000)
                            result = f"Clicked link: {text[:100]}"
                            found = True
                            break
                    except Exception:
                        continue
            
            if not found:
                result = f"Could not find element matching: {element[:100]}"
        
        elif action_type == "fill":
            field = action.get("field", "")
            value = action.get("value", "")
            found = False
            
            inputs = page.locator("input:not([type=hidden]):not([type=submit]):not([type=button])")
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
                    
                    # Check against ALL identifiers: name, placeholder, id, aria-label, label text
                    field_lower = field.lower()
                    if (field_lower in inp_name.lower() or 
                        field_lower in inp_placeholder.lower() or 
                        field_lower in inp_id.lower() or
                        field_lower in inp_aria_label.lower() or
                        field_lower in inp_label.lower()):
                        inp.fill(value, timeout=5000)
                        # Use the matched identifier for the result
                        display = inp_label or inp_aria_label or inp_id or inp_name or inp_placeholder
                        result = f"Filled input '{display}' with '{value[:50]}'"
                        found = True
                        break
                except Exception:
                    continue
            
            if not found:
                # Try textareas
                textareas = page.locator("textarea")
                for ta in textareas.all()[:20]:
                    try:
                        ta_name = ta.get_attribute("name") or ""
                        ta_placeholder = ta.get_attribute("placeholder") or ""
                        ta_id = ta.get_attribute("id") or ""
                        ta_aria_label = ta.get_attribute("aria-label") or ""
                        
                        # Get label text
                        ta_label = ""
                        ta_id_attr = ta.get_attribute("id")
                        if ta_id_attr:
                            label_el = page.locator(f"label[for='{ta_id_attr}']")
                            if label_el.count() > 0:
                                ta_label = label_el.first.inner_text(timeout=500).strip()
                        
                        field_lower = field.lower()
                        if (field_lower in ta_name.lower() or 
                            field_lower in ta_placeholder.lower() or
                            field_lower in ta_id.lower() or
                            field_lower in ta_aria_label.lower() or
                            field_lower in ta_label.lower()):
                            ta.fill(value, timeout=5000)
                            display = ta_label or ta_aria_label or ta_id or ta_name or ta_placeholder
                            result = f"Filled textarea '{display}' with '{value[:50]}'"
                            found = True
                            break
                    except Exception:
                        continue
            
            if not found:
                result = f"Could not find field matching: {field[:100]}"
        
        elif action_type == "select":
            field = action.get("field", "")
            option = action.get("option", "")
            found = False
            
            selects = page.locator("select")
            for sel in selects.all()[:20]:
                try:
                    sel_name = sel.get_attribute("name") or ""
                    if field.lower() in sel_name.lower():
                        options = sel.locator("option")
                        for opt in options.all()[:50]:
                            try:
                                opt_text = opt.inner_text(timeout=500).strip()
                                if option.lower() in opt_text.lower():
                                    opt.click(timeout=5000)
                                    result = f"Selected option '{opt_text}' in select '{sel_name}'"
                                    found = True
                                    break
                            except Exception:
                                continue
                        break
                except Exception:
                    continue
            
            if not found:
                result = f"Could not find select field matching: {field[:100]}"
        
        elif action_type == "scroll":
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
            
            result = f"Scrolled {direction} ({distance})"
        
        elif action_type == "navigate":
            url = action.get("url", "")
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)
            result = f"Navigated to {url}"
        
        elif action_type == "go_back":
            page.go_back(wait_until="domcontentloaded", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)
            result = "Went back"
        
        elif action_type == "wait":
            condition = action.get("condition", "networkidle")
            if condition.startswith("timeout:"):
                timeout_ms = int(condition.split(":")[1])
                page.wait_for_timeout(timeout_ms)
                result = f"Waited {timeout_ms}ms"
            else:
                page.wait_for_load_state(condition, timeout=10000)
                result = f"Waited for {condition}"
        
        elif action_type == "evaluate":
            script = action.get("script", "")
            
            # Transform console.log calls into return values
            # Playwright's evaluate() only returns what the script explicitly returns
            # When LLM uses console.log(), we need to capture the argument
            if "console.log(" in script:
                import re
                
                # Strategy: collect all console.log arguments into an array and return it
                # This handles any pattern - callbacks, standalone, nested
                logs = list(re.finditer(r'console\.log\((.+?)\)(?=\s*[;,)]|$)', script, re.DOTALL))
                if logs:
                    # Build a results array by collecting each console.log argument
                    # Then return the array at the end
                    results = []
                    new_script = []
                    last_end = 0
                    for log_match in logs:
                        new_script.append(script[last_end:log_match.start()])
                        # Extract the argument and replace console.log with pushing to results
                        arg = log_match.group(1)
                        new_script.append(f"results.push({arg});")
                        last_end = log_match.end()
                    new_script.append(script[last_end:])
                    # Append the return statement at the end
                    script = "".join(new_script) + "\nresults;"
            
            # Wrap script in a function to handle 'return' statements
            # Playwright's evaluate() requires scripts to be functions
            if script.strip().startswith("{"):
                # Script starts with { - wrap to return the object
                wrapped_script = f"(function() {{ return {script[1:-1].strip()} }})()"
            elif "return " in script:
                # Has return statement - wrap in IIFE
                wrapped_script = f"(function() {{ {script} }})()"
            else:
                wrapped_script = script
            value = page.evaluate(wrapped_script)
            result = f"Evaluation result: {str(value)[:200]}"
        
        elif action_type == "done":
            summary = action.get("summary", "Test complete")
            result = summary
        
        else:
            result = f"Unknown action type: {action_type}"
    
    except Exception as e:
        result = f"Action '{action_type}' failed: {str(e)[:200]}"
    
    action_history.append({
        "action": action_type,
        "parameters": {k: v for k, v in action.items() if k != "action"},
        "result": result,
    })
    
    return result


def run_interactive_test(browser, test, progress_file):
    """Run an interactive exploration test with LLM decision loop."""
    print(f"\n{'='*60}")
    print(f"INTERACTIVE TEST: {test['name']}")
    print(f"URL: {test['url']}")
    print(f"Goal: {test['task']}")
    print('='*60)
    
    page = browser.new_page()
    console_container = extract_console_during_navigation(page)
    
    try:
        # Navigate to the page
        print(f"  Navigating...")
        page.goto(test["url"], wait_until="domcontentloaded", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)
        
        initial_url = page.url
        action_history = []
        test_results = []
        iteration = 0
        
        # Main exploration loop
        while iteration < MAX_ITERATIONS:
            iteration += 1
            print(f"\n  Step {iteration}/{MAX_ITERATIONS}:")
            
            # Capture current state
            state = get_page_state(page, console_container)
            
            # LLM decides next action
            action = decide_action(
                page, state, action_history, test["task"], progress_file
            )
            
            print(f"  Action: {action}")
            
            # Execute action
            action_result = execute_action(page, action, action_history)
            
            # Record result
            test_results.append({
                "iteration": iteration,
                "action": action,
                "result": action_result,
                "url": page.url,
            })
            
            print(f"  Result: {action_result[:100]}")
            
            # Check if done
            if action.get("action") == "done":
                print(f"  Test complete after {iteration} steps")
                break
        
        return {
            "test": test["name"],
            "url": test["url"],
            "status": "success",
            "initial_url": initial_url,
            "final_url": page.url,
            "iterations": iteration,
            "action_history": action_history,
            "console_errors": console_container.get("messages", []) if isinstance(console_container, dict) else [],
        }
    
    except Exception as e:
        print(f"  ERROR: {e}")
        return {
            "test": test["name"],
            "url": test["url"],
            "status": "error",
            "error": str(e),
            "iterations": iteration,
            "action_history": action_history,
        }
    
    finally:
        page.close()


def get_page_state(page, console_container):
    """Capture comprehensive page state."""
    title = page.title()
    url = page.url
    
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
    
    details = extract_element_details(page)
    html = extract_html_snippet(page, max_bytes=2048)
    a11y = extract_accessibility_tree(page)
    console = console_container.get("messages", []) if isinstance(console_container, dict) else []
    
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


def main():
    print("Starting interactive exploration...")
    browser_engine = sync_playwright().start()
    browser = browser_engine.chromium.launch(headless=True)
    
    # Define interactive exploration tests
    # Focus on pages that actually exist and have forms/interactions
    tests = [
        {
            "name": "Homepage Navigation",
            "url": FRONTEND_URL,
            "task": "Test homepage navigation: click various links, scroll the page, and verify links work. Look for broken links, missing navigation elements, and content issues.",
        },
        {
            "name": "Post a Job Form",
            "url": FRONTEND_URL + "/shipper/post-a-job",
            "task": "Test the post-a-job form: fill in fields, submit, and observe validation. Try valid and invalid inputs. Look for missing labels, broken validation, and submission issues.",
        },
        {
            "name": "Login Page",
            "url": FRONTEND_URL + "/signin",
            "task": "Test the login page: fill in email/password fields, submit the form. Look for validation errors, missing fields, broken submission, and UX issues.",
        },
        {
            "name": "Register Page",
            "url": FRONTEND_URL + "/signup",
            "task": "Test the registration page: fill in fields, submit. Look for validation errors, missing fields, broken submission, and UX issues.",
        },
    ]
    
    results = []
    
    for i, test in enumerate(tests):
        print(f"\n{'='*60}")
        print(f"TEST {i+1}/{len(tests)}: {test['name']}")
        print('='*60)
        
        # Create a new progress file per test
        progress_file = open("progress_interactive.txt", "w")
        progress_file.write("STARTED")
        progress_file.flush()
        
        result = run_interactive_test(browser, test, progress_file)
        results.append(result)
        progress_file.close()
    
    browser.close()
    browser_engine.stop()
    print("\nBrowser closed.")
    
    # Save results
    output_path = Path("exploratory_results_p1.json")
    output_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n\nResults saved to {output_path}")
    
    # Print summary
    print("\n\n=== SUMMARY ===")
    for result in results:
        print(f"\n{result['test']}:")
        print(f"  Status: {result['status']}")
        if result['status'] == 'success':
            print(f"  Iterations: {result['iterations']}")
            print(f"  URL change: {result['initial_url']} → {result['final_url']}")
            print(f"  Actions taken: {len(result['action_history'])}")
            if result.get('action_history'):
                print(f"  Last 3 actions:")
                for action in result['action_history'][-3:]:
                    print(f"    - {action['action']}: {action['result'][:100]}")


if __name__ == "__main__":
    client = OpenAI(
        base_url=LLM_API_URL,
        api_key="placeholder",
        timeout=300.0,
    )
    main()
