"""Test if the generic word fix resolves the find_field() false positive."""
import sys
sys.path.insert(0, "/home/casibbald/Workspace/microscaler/llm-browser-driver/src")

from playwright.sync_api import sync_playwright
from llm_browser_driver import selector

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1280, "height": 720})
    page = c.new_page()
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
    
    page.fill("[data-testid='input-description']", "Test desc")
    page.fill("[data-testid='input-job-title']", "Test Job")
    page.fill("[data-testid='input-weight']", "15000")
    page.fill("[data-testid='input-volume']", "50")
    page.fill("[data-testid='input-packages']", "48")
    page.fill("[data-testid='input-cargo-value']", "45000")
    page.wait_for_timeout(500)
    
    print("=== Testing 'e.g., 18000' matching ===\n")
    
    # This was the problematic search — should match weight, not job title
    found, display = selector.find_field(page, "e.g., 18000")
    print(f"find_field('e.g., 18000'):")
    print(f"  found={found}, display='{display}'")
    if found and '18000' in str(display):
        print("  ✅ CORRECT — matched weight field")
    elif found and 'Job' in str(display) or 'General Cargo' in str(display):
        print("  ❌ WRONG — matched job title")
    
    # Also test a few other problematic searches
    tests = [
        "packages",
        "cargo value",
        "insurance",
        "volume",
        "weight",
        "e.g., General Cargo Transport",
    ]
    print("\n=== Other searches ===")
    for term in tests:
        found, display = selector.find_field(page, term)
        print(f"  find_field('{term}'): found={found}, display='{display[:40]}'")
    
    page.close()
    c.close()
    b.close()
    print("\nDone!")
