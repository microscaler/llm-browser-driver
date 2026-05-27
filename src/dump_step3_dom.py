"""Comprehensive dump of Step 3 (Delivery Location) DOM structure."""
from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1280, "height": 720})
    page = c.new_page()
    page.goto("http://localhost:7174/shipper/post-a-job", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Fill Step 1 quickly
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
    page.locator("button", has_text="Next Step").first.click()
    page.wait_for_timeout(3000)
    
    # Fill Step 2
    page.locator("[data-testid='select-pickup-country']").first.click()
    page.wait_for_timeout(800)
    page.locator("li.cursor-pointer").first.click()
    page.wait_for_timeout(2000)
    
    page.locator("[data-testid='select-pickup-state']").first.click()
    page.wait_for_timeout(500)
    if page.locator("li.cursor-pointer").count() > 0:
        page.locator("li.cursor-pointer").first.click()
        page.wait_for_timeout(500)
    
    page.locator("[data-testid='select-pickup-city']").first.click()
    page.wait_for_timeout(500)
    if page.locator("li.cursor-pointer").count() > 0:
        page.locator("li.cursor-pointer").first.click()
        page.wait_for_timeout(500)
    
    page.fill("[data-testid='input-pickup-address']", "123 Test St")
    page.fill("[data-testid='input-pickup-date']", "2026-06-15")
    page.fill("[data-testid='input-pickup-time-start']", "09:00")
    page.fill("[data-testid='input-pickup-time-end']", "17:00")
    page.wait_for_timeout(500)
    page.locator("button", has_text="Next Step").first.click()
    page.wait_for_timeout(3000)
    
    # Now we're on Step 3 — dump everything
    dump = page.evaluate("""
    () => JSON.stringify({
        // Step header
        stepHeader: (() => {
            const els = document.querySelectorAll('h1, h2, h3, [class*="step-title"]');
            for (const el of els) {
                if (el.textContent.includes('Step 3') || el.textContent.includes('Delivery')) {
                    return el.textContent.trim();
                }
            }
            return 'NOT FOUND';
        })(),
        
        // All form elements
        inputs: [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button])')].map(el => ({
            type: el.type,
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            'data-testid': el.getAttribute('data-testid') || '',
            'aria-label': el.getAttribute('aria-label') || '',
            'aria-labelledby': el.getAttribute('aria-labelledby') || '',
            label: el.labels?.[0]?.textContent?.trim() || '',
            disabled: el.disabled,
            required: el.required,
            value: el.value,
        })),
        
        textareas: [...document.querySelectorAll('textarea')].map(el => ({
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            'data-testid': el.getAttribute('data-testid') || '',
            'aria-label': el.getAttribute('aria-label') || '',
            label: el.labels?.[0]?.textContent?.trim() || '',
            value: el.value,
        })),
        
        selects: [...document.querySelectorAll('select:not([hidden])')].map(el => ({
            name: el.name || '',
            id: el.id || '',
            'data-testid': el.getAttribute('data-testid') || '',
            'aria-label': el.getAttribute('aria-label') || '',
            label: el.labels?.[0]?.textContent?.trim() || '',
            options: [...el.options].map(o => o.text).slice(0, 3),
        })),
        
        // Custom dropdowns (SolidJS SelectDropdown pattern)
        customDropdowns: [...document.querySelectorAll('[data-testid]')].filter(el => 
            el.getAttribute('data-testid')?.includes('select') && 
            el.tagName === 'BUTTON'
        ).map(el => ({
            testid: el.getAttribute('data-testid') || '',
            text: el.textContent.trim(),
            'aria-expanded': el.getAttribute('aria-expanded') || '',
            'aria-haspopup': el.getAttribute('aria-haspopup') || '',
            disabled: el.disabled || el.classList.contains('opacity-50'),
            className: el.className,
        })),
        
        // All buttons
        buttons: [...document.querySelectorAll('button:not([type=hidden])')].map(el => ({
            text: el.textContent.trim().replace(/\s+/g, ' ').substring(0, 80),
            'data-testid': el.getAttribute('data-testid') || '',
            id: el.id || '',
            type: el.type || '',
            disabled: el.disabled,
        })),
        
        // Labels in the page
        labels: [...document.querySelectorAll('label')].map(el => ({
            text: el.textContent?.trim() || '',
            'for': el.getAttribute('for') || '',
            htmlFor: el.htmlFor || '',
        })).filter(l => l.text && l.text.length > 2 && l.text.length < 100),
        
        // Validation banner
        validationBanner: document.getElementById('validation-error-banner')?.textContent?.trim() || null,
        validationInline: document.querySelectorAll('[class*="error-message"], [class*="field-error"], .text-red-500').length,
        
        // Sidebar indicators
        sidebarIndicators: [...document.querySelectorAll('[data-testid*="step"], [class*="step-nav"], [class*="nav-step"]')].map(el => ({
            testid: el.getAttribute('data-testid') || '',
            text: el.textContent?.trim() || '',
            className: el.className,
        })),
        
        // All data-testid values (for cross-referencing)
        allTestDataIds: [...document.querySelectorAll('[data-testid]')].map(el => el.getAttribute('data-testid')).filter(Boolean),
    }, null, 2)
    """)
    
    data = json.loads(dump)
    
    # Print in a structured way
    print("=" * 80)
    print("STEP 3 (Delivery Location) — COMPLETE DOM DUMP")
    print("=" * 80)
    print(f"\nStep Header: {data['stepHeader']}")
    print(f"Validation Banner: {data['validationBanner']}")
    print(f"Inline error elements: {data['validationInline']}")
    
    print(f"\n--- INPUTS ({len(data['inputs'])}) ---")
    for i, inp in enumerate(data['inputs']):
        testid = inp['data-testid'] or inp['id'] or inp.get('name', '') or '(none)'
        aria = inp['aria-label'] or inp['aria-labelledby'] or ''
        label = inp.get('label', '')
        placeholder = inp['placeholder'] or ''
        disabled = ' [DISABLED]' if inp['disabled'] else ''
        required = ' *' if inp['required'] else ''
        print(f"  [{i:2d}] testid={testid:30s} type={inp['type']:6s} placeholder='{placeholder[:30]}' label='{label[:30]}' aria='{aria[:30]}'{disabled}{required}")
    
    print(f"\n--- TEXTAREAS ({len(data['textareas'])}) ---")
    for i, ta in enumerate(data['textareas']):
        testid = ta['data-testid'] or ta['id'] or ta.get('name', '') or '(none)'
        label = ta.get('label', '')
        placeholder = ta['placeholder'] or ''
        print(f"  [{i:2d}] testid={testid:30s} placeholder='{placeholder[:30]}' label='{label[:30]}'")
    
    print(f"\n--- SELECTS ({len(data['selects'])}) ---")
    for sel in data['selects']:
        testid = sel['data-testid'] or sel['id'] or sel.get('name', '') or '(none)'
        print(f"  testid={testid:30s} placeholder='{sel.get('label', '')[:30]}'")
    
    print(f"\n--- CUSTOM DROPDOWNS (SolidJS) ({len(data['customDropdowns'])}) ---")
    for dd in data['customDropdowns']:
        disabled = ' [DISABLED]' if dd['disabled'] else ''
        aria = dd.get('aria-expanded', '') or dd.get('aria-haspopup', '')
        print(f"  testid={dd['testid']:30s} text='{dd['text'][:40]}' aria='{aria}'{disabled}")
    
    print(f"\n--- BUTTONS ({len(data['buttons'])}) ---")
    for btn in data['buttons']:
        disabled = ' [DISABLED]' if btn['disabled'] else ''
        testid = btn.get('data-testid', '') or btn.get('id', '')
        if btn['text']:
            print(f"  text='{btn['text'][:60]}' testid='{testid}'{disabled}")
    
    print(f"\n--- LABELS ({len(data['labels'])}) ---")
    for lbl in data['labels'][:20]:  # First 20
        for_attr = lbl.get('for', '') or lbl.get('htmlFor', '')
        print(f"  text='{lbl['text'][:50]}' for='{for_attr}'")
    
    print(f"\n--- ALL data-testid VALUES ---")
    for tid in data['allTestDataIds']:
        print(f"  {tid}")
    
    print(f"\n--- SIDEBAR NAV INDICATORS ---")
    for ind in data['sidebarIndicators'][:15]:
        print(f"  testid={ind.get('testid', 'none'):20s} class={ind['className'][:60]:60s} text='{ind['text'][:40]}'")
    
    # Save full JSON for inspection
    with open('/tmp/step3_full_dump.json', 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\nFull JSON saved to /tmp/step3_full_dump.json")
    
    page.close()
    c.close()
    b.close()
