"""Test execute_fill() already-filled check."""
import sys
sys.path.insert(0, "/home/casibbald/Workspace/microscaler/llm-browser-driver/src")

from playwright.sync_api import sync_playwright
from llm_browser_driver import actions

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1280, "height": 720})
    page = c.new_page()
    page.goto("http://localhost:7174/shipper/post-a-job", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Fill some fields first
    page.fill("[data-testid='input-job-title']", "Test Job")
    page.fill("[data-testid='input-weight']", "15000")
    page.fill("[data-testid='input-description']", "Test desc")
    page.wait_for_timeout(500)
    
    print("=== execute_fill() already-filled check ===\n")
    
    # Try to fill job title with same value (should say "Already filled")
    r1 = actions.execute_fill(page, {"field": "job title", "value": "Test Job"})
    print(f"1. fill 'job title'='Test Job': {r1}")
    
    # Try with different value (should succeed)
    r2 = actions.execute_fill(page, {"field": "job title", "value": "New Job"})
    print(f"2. fill 'job title'='New Job': {r2}")
    
    # Try with same value again (should say "Already filled")
    r3 = actions.execute_fill(page, {"field": "job title", "value": "New Job"})
    print(f"3. fill 'job title'='New Job': {r3}")
    
    # Try with slightly different value (should succeed)
    r4 = actions.execute_fill(page, {"field": "job title", "value": "New Job "})
    print(f"4. fill 'job title'='New Job ': {r4}")
    
    # Try with empty value (should succeed - different from "New Job")
    r5 = actions.execute_fill(page, {"field": "job title", "value": ""})
    print(f"5. fill 'job title'='': {r5}")
    
    page.close()
    c.close()
    b.close()
