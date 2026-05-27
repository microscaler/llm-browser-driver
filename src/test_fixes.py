"""Test the find_field() and page summary fixes."""
import sys
sys.path.insert(0, "/home/casibbald/Workspace/microscaler/llm-browser-driver/src")

from playwright.sync_api import sync_playwright
from llm_browser_driver import selector, actions, state

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1280, "height": 720})
    page = c.new_page()
    
    # Go to Step 2
    page.goto("http://localhost:7174/shipper/post-a-job", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Fill Step 1
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
    
    page.fill("[data-testid='input-description']", "Test description")
    page.fill("[data-testid='input-job-title']", "Test Job")
    page.fill("[data-testid='input-weight']", "15000")
    page.fill("[data-testid='input-volume']", "50")
    page.fill("[data-testid='input-packages']", "48")
    page.fill("[data-testid='input-cargo-value']", "45000")
    page.wait_for_timeout(500)
    page.locator("button", has_text="Next Step").first.click()
    page.wait_for_timeout(3000)
    
    print("=== find_field() on Step 2 buttons ===")
    tests = [
        ("Country", "should match the CountrySelect button"),
        ("State / Province", "should match the ProvinceAutocomplete button"),
    ]
    for term, desc in tests:
        found, display = selector.find_field(page, term)
        status = "OK" if found else "FAIL"
        print(f"  [{status}] find_field('{term}'): display='{display}' — {desc}")
    
    print("\n=== Page summary includes button testids? ===")
    s = state.get_page_state(page)
    summary = state.build_page_summary(s)
    has_testids = "test_id=" in summary
    status = "OK" if has_testids else "FAIL"
    print(f"  [{status}] Button testids in summary: {has_testids}")
    
    # Print buttons section
    btn_section = summary[summary.find("--- BUTTONS ---"):summary.find("--- LINKS ---")]
    lines = btn_section.split("\n")
    print(f"\n  Buttons ({len(lines)} lines):")
    for line in lines:
        print(f"    {line[:80]}")
    
    page.close()
    c.close()
    b.close()
    print("\nDone!")
