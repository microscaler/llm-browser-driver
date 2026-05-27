"""Trace what find_field() returns for each search term."""
import sys
sys.path.insert(0, "/home/casibbald/Workspace/microscaler/llm-browser-driver/src")

from playwright.sync_api import sync_playwright
from llm_browser_driver import selector

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1280, "height": 720})
    page = c.new_page()
    
    # Go to Step 1
    page.goto("http://localhost:7174/shipper/post-a-job", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Fill Step 1 dropdowns
    dropdowns = [
        ("Select cargo type", "Vehicles"),
        ("Select load type", "Flatbed Truck"),
        ("Select packaging", "Pallets"),
        ("Select option", "Yes - Full Coverage"),
    ]
    for text, val in dropdowns:
        page.locator(f"text={text}", has_text=text).first.click()
        page.wait_for_timeout(400)
        page.locator("li.cursor-pointer", has_text=val).first.click()
        page.wait_for_timeout(200)
    
    # Fill some fields
    page.fill("[data-testid='input-description']", "Test desc")
    page.fill("[data-testid='input-job-title']", "Test Job")
    page.fill("[data-testid='input-weight']", "15000")
    page.fill("[data-testid='input-volume']", "50")
    page.fill("[data-testid='input-packages']", "48")
    page.fill("[data-testid='input-cargo-value']", "45000")
    page.wait_for_timeout(500)
    
    # Now trace what find_field() returns for each search term
    # These are the terms the LLM was trying to fill
    test_terms = [
        "packages",
        "cargo value",
        "insurance",
        "volume",
        "weight",
        "description",
        "job title",
        "e.g., General Cargo Transport",
        "e.g., 18000",
        "input-description",
    ]
    
    print("=== find_field() tracing ===\n")
    for term in test_terms:
        found, display = selector.find_field(page, term)
        print(f"find_field('{term}'):")
        print(f"  found={found}, display='{display}'")
        if found:
            # Also check what the actual element is
            if "input-" in str(display):
                # Try to find by testid
                testid = display if display.startswith("input-") else ""
                if testid:
                    el = page.locator(f"[data-testid='{testid}']")
                    if el.count() > 0:
                        ph = el.first.get_attribute("placeholder") or ""
                        val = el.first.input_value() or ""
                        print(f"  → testid={testid}, placeholder='{ph[:40]}', value='{val[:20]}'")
            else:
                print(f"  → placeholder='{display[:40]}'")
        print()
    
    page.close()
    c.close()
    b.close()
