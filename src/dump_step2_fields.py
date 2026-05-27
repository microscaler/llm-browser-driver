"""Dump all form fields on Step 2 to understand what needs filling."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1280, "height": 720})
    page = c.new_page()
    page.goto("http://localhost:7174/shipper/post-a-job", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Fill Step 1
    for text, val in [("Select cargo type", "Vehicles"), ("Select load type", "Flatbed Truck"), 
                       ("Select packaging", "Pallets"), ("Select option", "Yes - Full Coverage")]:
        page.locator(f"text={text}").first.click()
        page.wait_for_timeout(400)
        page.locator("li.cursor-pointer", has_text=val).first.click()
        page.wait_for_timeout(200)
    
    page.fill("[data-testid='input-description']", "Test description")
    page.fill("[data-testid='input-job-title']", "Test Job")
    page.fill("[data-testid='input-weight']", "15000")
    page.fill("[data-testid='input-volume']", "50")
    page.fill("[data-testid='input-packages']", "48")
    page.fill("[data-testid='input-cargo-value']", "45000")
    page.wait_for_timeout(500)
    
    # Click Next Step
    page.locator("button", has_text="Next Step").first.click()
    page.wait_for_timeout(3000)
    
    # Now dump Step 2 fields
    fields = page.evaluate("""
    () => JSON.stringify({
        inputs: [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button])')].map(el => ({
            testid: el.getAttribute('data-testid') || '',
            type: el.type,
            value: el.value,
            placeholder: el.placeholder,
        })),
        textareas: [...document.querySelectorAll('textarea')].map(el => ({
            testid: el.getAttribute('data-testid') || '',
            value: el.value,
            placeholder: el.placeholder,
        })),
        customDropdowns: [...document.querySelectorAll('[data-testid]')].filter(el => 
            el.getAttribute('data-testid')?.includes('select')).map(el => ({
            testid: el.getAttribute('data-testid') || '',
            text: el.textContent.trim(),
        })),
        buttons: [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(Boolean),
        validationBanner: document.getElementById('validation-error-banner')?.textContent?.trim() || null,
    })
    """)
    
    import json
    fields = json.loads(fields)
    
    print("=" * 70)
    print("STEP 2 FORM FIELDS")
    print("=" * 70)
    print(f"\nValidation Banner: {fields.get('validationBanner', 'None')}")
    
    print(f"\n--- Inputs ({len(fields.get('inputs', []))}) ---")
    for inp in fields.get('inputs', []):
        testid = inp['testid'] or '(none)'
        print(f"  testid={testid:25s} type={inp['type']:8s} value='{inp['value']:20s}' placeholder='{inp['placeholder']}'")
    
    print(f"\n--- Textareas ({len(fields.get('textareas', []))}) ---")
    for ta in fields.get('textareas', []):
        print(f"  testid={ta.get('testid', 'none'):25s} value='{ta['value']}' placeholder='{ta.get('placeholder', '')}'")
    
    print(f"\n--- Custom Dropdowns ({len(fields.get('customDropdowns', []))}) ---")
    for dd in fields.get('customDropdowns', []):
        print(f"  testid={dd.get('testid', 'none'):25s} text='{dd.get('text', '')}'")
    
    print(f"\n--- Buttons ({len(fields.get('buttons', []))}) ---")
    for btn in fields.get('buttons', []):
        short = btn.replace('\n', ' ')[:50]
        print(f"  '{short}'")
    
    page.close()
    c.close()
    b.close()
