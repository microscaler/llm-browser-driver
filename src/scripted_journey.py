"""Scripted journey tester for Hauliage post-a-job wizard.

Uses llm-browser-driver's low-level APIs to deterministically drive
through each step of the wizard, reporting which steps succeed and
which fail. This bypasses the LLM's tendency to fill fields but not
click navigation buttons.

Usage:
    PYTHONPATH=src:../../hauliage/microservices/consignments/impl/tests python3 src/scripted_journey.py
"""

import json
import sys
import time
from pathlib import Path

# Add hauliage config path
_hauliage_config_paths = [
    Path(__file__).resolve().parent.parent.parent
    / "hauliage" / "microservices" / "consignments" / "impl" / "tests",
    Path("/home/casibbald/Workspace/microscaler/hauliage/microservices/consignments/impl/tests"),
]
for p in _hauliage_config_paths:
    if p.exists():
        sys.path.insert(0, str(p))
        break

from playwright.sync_api import sync_playwright
from llm_browser_driver.config import load_config
from llm_browser_driver.state import get_page_state, build_page_summary, detect_current_step
from llm_browser_driver.selector import find_custom_dropdown_trigger, click_custom_dropdown_option
from llm_browser_driver.actions import execute_fill
from hauliage_driver_config import PICKUP_COUNTRY_OPTIONS

FRONTEND_URL = "http://localhost:7174/shipper/post-a-job"
LLM_URL = "http://192.168.1.104:8000/v1"


def find_field(page, field_name):
    """Find a field by name/placeholder/testid and return the element."""
    elements = page.locator(
        "input:not([type=hidden]):not([type=submit]):not([type=button]), textarea"
    ).all()
    for el in elements:
        try:
            el_name = el.get_attribute("name") or ""
            el_placeholder = el.get_attribute("placeholder") or ""
            el_id = el.get_attribute("id") or ""
            el_aria = el.get_attribute("aria-label") or ""
            el_testid = el.get_attribute("data-testid") or ""
            el_textarea_testid = el.get_attribute("data-testid") or ""
            
            field_lower = field_name.lower()
            if (
                field_lower in el_name.lower()
                or field_lower in el_placeholder.lower()
                or field_lower in el_id.lower()
                or field_lower in el_aria.lower()
                or field_lower in el_testid.lower()
            ):
                return el
        except Exception:
            pass
    return None


def find_and_click_button(page, button_text):
    """Find and click a button by exact text."""
    buttons = page.locator("button").all()
    for btn in buttons:
        try:
            text = btn.inner_text().strip()
            if text == button_text:
                btn.click()
                return True
        except Exception:
            pass
    return False


def select_dropdown(page, trigger_text, option_text):
    """Open a custom dropdown and select an option."""
    found, message = find_custom_dropdown_trigger(page, trigger_text)
    if not found:
        return False, message
    
    # trigger is a Playwright element (locatable)
    page.locator(f"text='{trigger_text}'").first.click()
    page.wait_for_timeout(1000)
    
    success = click_custom_dropdown_option(page, option_text)
    page.wait_for_timeout(500)
    return success, f"Selected option '{option_text}'"


def fill_field(page, field_name, value):
    """Fill a field by name/placeholder/testid."""
    el = find_field(page, field_name)
    if not el:
        return False, f"Could not find field: {field_name}"
    
    try:
        el_type = el.get_attribute("type") or "text"
        if el_type == "textarea":
            el.fill(value)
        else:
            el.fill(value)
        return True, f"Filled field '{field_name}'"
    except Exception as e:
        return False, f"Failed to fill field: {str(e)}"


def get_page_info(page):
    """Get current page info."""
    state = get_page_state(page)
    step = detect_current_step(page)
    url = page.url
    buttons = [b["text"] for b in state.get("details", {}).get("buttons", [])]
    return {
        "url": url,
        "step": step,
        "buttons": buttons,
        "inputs": len(state.get("details", {}).get("inputs", [])),
        "dropdowns": len(state.get("custom_dropdowns", [])),
    }


def run_journey():
    """Run the scripted post-a-job wizard journey."""
    print("=" * 70)
    print("Hauliage Post-a-Job Wizard — Scripted Journey Test")
    print("=" * 70)
    print(f"Frontend: {FRONTEND_URL}")
    print(f"LLM: {LLM_URL}")
    print()
    
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        c = b.new_context(viewport={"width": 1280, "height": 720})
        page = c.new_page()
        
        results = []
        current_step = 1
        
        try:
            # Navigate to the page
            print("[1/9] Navigating to post-a-job page...")
            page.goto(FRONTEND_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            info = get_page_info(page)
            print(f"     Current step: {info['step']}")
            print(f"     Buttons: {info['buttons']}")
            results.append({"step": "navigate", "status": "success", "details": info})
            
            # Step 1: Cargo specs
            print("\n[2/9] Step 1: Selecting cargo type...")
            success, msg = select_dropdown(page, "Select cargo type", "Vehicles")
            print(f"     {msg} → {'✓' if success else '✗'}")
            results.append({"step": "cargo_type", "status": "ok" if success else "fail", "details": msg})
            
            print("\n[3/9] Step 1: Selecting load type...")
            # Note: "Full Truck Load" doesn't exist, use "Flatbed Truck"
            page.wait_for_timeout(500)
            success, msg = select_dropdown(page, "Select load type", "Flatbed Truck")
            print(f"     {msg} → {'✓' if success else '✗'}")
            results.append({"step": "load_type", "status": "ok" if success else "fail", "details": msg})
            
            print("\n[4/9] Step 1: Selecting packaging...")
            page.wait_for_timeout(500)
            success, msg = select_dropdown(page, "Select packaging", "Pallets")
            print(f"     {msg} → {'✓' if success else '✗'}")
            results.append({"step": "packaging", "status": "ok" if success else "fail", "details": msg})
            
            print("\n[5/9] Step 1: Filling description...")
            success, msg = fill_field(page, "input-description", "Transporting vehicles on a flatbed truck. Standard handling.")
            print(f"     {msg} → {'✓' if success else '✗'}")
            results.append({"step": "description", "status": "ok" if success else "fail", "details": msg})
            
            print("\n[6/9] Step 1: Filling job title...")
            success, msg = fill_field(page, "General Cargo Transport", "Vehicle Transport - Flatbed")
            print(f"     {msg} → {'✓' if success else '✗'}")
            results.append({"step": "job_title", "status": "ok" if success else "fail", "details": msg})
            
            print("\n[7/9] Step 1: Filling weight...")
            success1, msg1 = fill_field(page, "18000", "15000")
            print(f"     Weight: {msg1} → {'✓' if success1 else '✗'}")
            
            print("\n[8/9] Step 1: Filling volume...")
            success2, msg2 = fill_field(page, "67.2", "50")
            print(f"     Volume: {msg2} → {'✓' if success2 else '✗'}")
            
            print("\n[9/9] Step 1: Filling number of packages...")
            success3, msg3 = fill_field(page, "input-packages", "48")
            print(f"     Packages: {msg3} → {'✓' if success3 else '✗'}")
            
            print("\n[10/9] Step 1: Filling cargo value...")
            success4, msg4 = fill_field(page, "input-cargo-value", "45000")
            print(f"     Cargo Value: {msg4} → {'✓' if success4 else '✗'}")
            
            print("\n[11/9] Step 1: Selecting insurance...")
            page.wait_for_timeout(500)
            success5, msg5 = select_dropdown(page, "Select option", "Yes - Full Coverage")
            print(f"     Insurance: {msg5} → {'✓' if success5 else '✗'}")
            
            all_step1_pass = all([success1, success2, success3, success4, success5])
            results.append({"step": "step1_completion", "status": "ok" if all_step1_pass else "fail", 
                           "details": f"Weight:{msg1[:40]} Volume:{msg2[:40]} Pkg:{msg3[:40]} Val:{msg4[:40]} Ins:{msg5[:40]}"})
            
            # Check if Next Step is enabled
            print("\n[12/11] Checking form state before clicking Next Step...")
            page.wait_for_timeout(1000)
            
            # Dump all form field values from SolidJS
            form_state = page.evaluate("""
            () => {
                const fields = {};
                // Check all inputs/textareas by data-testid
                document.querySelectorAll('[data-testid]').forEach(el => {
                    fields[el.getAttribute('data-testid')] = {
                        type: el.type || el.tagName.toLowerCase(),
                        value: el.value || '',
                    };
                });
                // Check select dropdowns (custom SolidJS ones)
                document.querySelectorAll('[data-testid*="dropdown"]').forEach(el => {
                    fields[el.getAttribute('data-testid')] = el.innerHTML;
                });
                // Check if validation error banner exists
                const banner = document.getElementById('validation-error-banner');
                fields['validationBanner'] = banner ? banner.textContent : null;
                return fields;
            }
            """)
            print(f"     Form state: {json.dumps(form_state, indent=4, default=str)[:500]}")
            page.wait_for_timeout(1000)
            info = get_page_info(page)
            next_step_enabled = "Next Step" in info["buttons"]
            print(f"     Next Step button present: {next_step_enabled}")
            print(f"     All buttons: {info['buttons']}")
            
            if next_step_enabled:
                print("\n[9/9] Step 1 → Step 2: Clicking Next Step...")
                success = find_and_click_button(page, "Next Step")
                page.wait_for_timeout(3000)
                print(f"     {'✓' if success else '✗'} Clicked Next Step")
                results.append({"step": "next_to_step2", "status": "ok" if success else "fail"})
                
                # Check where we ended up
                info = get_page_info(page)
                print(f"\n     NEW STEP: {info['step']}")
                print(f"     NEW URL: {info['url']}")
                print(f"     New buttons: {info['buttons']}")
                results.append({"step": "after_next_step", "details": info})
                
                if info["step"] and "Step 2" in info["step"]:
                    print("\n     ✓✓✓ SUCCESS! Reached Step 2: Pickup Location")
                    
                    # Try to interact with Step 2
                    print("\n[10/9] Step 2: Exploring pickup location...")
                    info = get_page_info(page)
                    print(f"     Inputs: {info['inputs']}")
                    print(f"     Dropdowns: {info['dropdowns']}")
                    print(f"     Buttons: {info['buttons']}")
                    results.append({"step": "step2_exploration", "details": info})
                    
                    # Try to select pickup country
                    print("\n[12/11] Step 2: Selecting pickup country...")
                    countries = PICKUP_COUNTRY_OPTIONS
                    if countries:
                        first_country = countries[0]
                        print(f"     First available country: {first_country}")
                        page.wait_for_timeout(500)
                        success, msg = select_dropdown(page, "Select country", first_country)
                        print(f"     Country: {msg} → {'✓' if success else '✗'}")
                        results.append({"step": "pickup_country", "status": "ok" if success else "fail", "details": msg})
                        
                        if success:
                            # After country selection, state dropdown should appear
                            page.wait_for_timeout(1500)
                            
                            # Dump state dropdown options
                            state_options = page.evaluate("""
                            () => {
                                const stateBtn = [...document.querySelectorAll('[data-testid]')].find(el => 
                                    el.getAttribute('data-testid')?.includes('select-pickup-state'));
                                if (!stateBtn) return { visible: false, text: 'State button not found' };
                                // Open the dropdown to see options
                                return { 
                                    visible: true, 
                                    text: stateBtn.textContent.trim(),
                                    testid: stateBtn.getAttribute('data-testid'),
                                };
                            }
                            """)
                            print(f"     State dropdown: {state_options.get('text', 'N/A')}")
                            
                            # Check if state dropdown is enabled (not "Select a country first")
                            if "Select a country first" in state_options.get("text", ""):
                                print("     State dropdown still says 'Select a country first' — waiting for API...")
                                page.wait_for_timeout(3000)
                                state_options = page.evaluate("""
                                () => {
                                    const stateBtn = [...document.querySelectorAll('[data-testid]')].find(el => 
                                        el.getAttribute('data-testid')?.includes('select-pickup-state'));
                                    if (!stateBtn) return { text: 'Not found' };
                                    return stateBtn.textContent.trim();
                                }
                                """)
                                print(f"     After wait: {state_options}")
                            
                            # Select state if available (try a common one like "California" or first option)
                            page.wait_for_timeout(500)
                            state_success = False
                            state_msg = ""
                            for test_state in ["California", "New York", "Texas", "London"]:
                                page.wait_for_timeout(300)
                                state_success, state_msg = select_dropdown(page, "Select a country first", test_state)
                                if state_success:
                                    print(f"     State '{test_state}': {state_msg} → ✓")
                                    results.append({"step": "pickup_state", "status": "ok", "details": state_msg})
                                    break
                                else:
                                    # Try first available option by selecting from "Select a country first"
                                    # This might be a state option already shown
                                    pass
                            
                            if not state_success:
                                # Try to just click the state button and see what options exist
                                print("     State dropdown not found with common names — trying first available option")
                                state_btns = page.locator("[data-testid*='select-pickup-state']")
                                if state_btns.count() > 0:
                                    state_btn = state_btns.first
                                    current_text = state_btn.inner_text()
                                    print(f"     State button text: '{current_text}'")
                                    state_btn.click()
                                    page.wait_for_timeout(800)
                                    # Try to find any li option in the dropdown
                                    options = page.locator("li.cursor-pointer").all()
                                    if options:
                                        first_state = options[0].inner_text().strip()
                                        print(f"     First state option: '{first_state}'")
                                        page.locator("li.cursor-pointer").first.click()
                                        page.wait_for_timeout(500)
                                        state_success = True
                                        state_msg = f"Selected state: {first_state}"
                                        results.append({"step": "pickup_state", "status": "ok", "details": state_msg})
                                    else:
                                        print("     No state options found — state dropdown may need country API response")
                                        results.append({"step": "pickup_state", "status": "fail", "details": "No state options available"})
                                else:
                                    print("     No state button found")
                                    results.append({"step": "pickup_state", "status": "info", "details": "No state dropdown visible"})
                            
                            # Try to select city if state was selected
                            if state_success:
                                page.wait_for_timeout(1000)
                                city_btns = page.locator("[data-testid*='select-pickup-city']")
                                if city_btns.count() > 0:
                                    city_btn_text = city_btns.first.inner_text()
                                    print(f"     City button text: '{city_btn_text}'")
                                    city_btns.first.click()
                                    page.wait_for_timeout(800)
                                    city_options = page.locator("li.cursor-pointer").all()
                                    if city_options:
                                        first_city = city_options[0].inner_text().strip()
                                        print(f"     First city option: '{first_city}'")
                                        page.locator("li.cursor-pointer").first.click()
                                        page.wait_for_timeout(500)
                                        city_msg = f"Selected city: {first_city}"
                                        print(f"     {city_msg} → ✓")
                                        results.append({"step": "pickup_city", "status": "ok", "details": city_msg})
                                    else:
                                        print("     No city options found")
                                        results.append({"step": "pickup_city", "status": "info", "details": "No city dropdown options"})
                                else:
                                    print("     No city button found")
                                    results.append({"step": "pickup_city", "status": "info", "details": "No city dropdown visible"})
                            else:
                                results.append({"step": "pickup_city", "status": "info", "details": "Skipped — state not selected"})
                            
                            # Fill pickup address
                            print("\n     Filling pickup address...")
                            addr_success, addr_msg = fill_field(page, "input-pickup-address", "123 Test Street")
                            print(f"     {addr_msg} → {'✓' if addr_success else '✗'}")
                            results.append({"step": "pickup_address", "status": "ok" if addr_success else "fail", "details": addr_msg})
                            
                            # Fill pickup date (future date)
                            print("\n     Filling pickup date...")
                            date_success, date_msg = fill_field(page, "input-pickup-date", "2026-06-15")
                            print(f"     {date_msg} → {'✓' if date_success else '✗'}")
                            results.append({"step": "pickup_date", "status": "ok" if date_success else "fail", "details": date_msg})
                            
                            # Fill pickup time
                            print("\n     Filling pickup times...")
                            t1_success, t1_msg = fill_field(page, "input-pickup-time-start", "09:00")
                            print(f"     Start: {t1_msg} → {'✓' if t1_success else '✗'}")
                            t2_success, t2_msg = fill_field(page, "input-pickup-time-end", "17:00")
                            print(f"     End: {t2_msg} → {'✓' if t2_success else '✗'}")
                            results.append({"step": "pickup_times", "status": "ok" if t1_success and t2_success else "fail",
                                           "details": f"{t1_msg}, {t2_msg}"})
                            
                            # Try to advance to Step 3
                            print("\n[18/11] Step 2 → Step 3: Clicking Next Step...")
                            page.wait_for_timeout(1000)
                            nav_success = find_and_click_button(page, "Next Step")
                            page.wait_for_timeout(3000)
                            print(f"     {'✓' if nav_success else '✗'} Clicked Next Step")
                            results.append({"step": "next_to_step3", "status": "ok" if nav_success else "fail"})
                            
                            info = get_page_info(page)
                            print(f"     NEW STEP: {info['step']}")
                            print(f"     NEW URL: {info['url']}")
                            results.append({"step": "after_step3", "details": info})
                            
                            if info["step"] and "Step 3" in info["step"]:
                                print("\n     ✓✓✓ SUCCESS! Reached Step 3: Delivery Location")
                            elif "validation-error-banner" in info.get("buttons", "") or "error" in str(info).lower():
                                # Check for validation errors
                                banner_text = page.evaluate("document.getElementById('validation-error-banner')?.textContent || ''")
                                if banner_text:
                                    print(f"     Validation error: {banner_text[:200]}")
                                    results.append({"step": "validation_error", "status": "fail", "details": banner_text[:200]})
                                else:
                                    print(f"     Failed to advance — Step: {info['step']}")
                            else:
                                print(f"     Failed to advance to Step 3 — Step: {info['step']}")
                                results.append({"step": "failed_to_advance", "status": "fail", "details": f"Still on: {info['step']}"})
                        else:
                            print(f"     Country selection failed: {msg}")
                            results.append({"step": "pickup_country", "status": "fail", "details": msg})
                    else:
                        print("     No countries configured")
                        results.append({"step": "no_countries", "status": "info"})
                else:
                    print(f"\n     ✗✗✗ FAILED! Still on step: {info['step']}")
                    results.append({"step": "failed_to_advance", "status": "fail", "details": f"Still on: {info['step']}"})
            else:
                print("\n     ✗✗✗ Next Step button NOT enabled!")
                print("     Possible validation errors blocking navigation.")
                results.append({"step": "next_step_disabled", "status": "fail", "details": "Next Step not enabled"})
                
        except Exception as e:
            print(f"\n✗✗✗ EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            results.append({"step": "exception", "status": "error", "details": str(e)})
        
        finally:
            # Save results
            results_path = Path("/tmp/scripted_journey_results.json")
            results_path.write_text(json.dumps(results, indent=2, default=str))
            print(f"\n{'='*70}")
            print("JOURNEY RESULTS")
            print("=" * 70)
            
            success_count = sum(1 for r in results if r.get("status") == "ok")
            fail_count = sum(1 for r in results if r.get("status") == "fail")
            info_count = sum(1 for r in results if r.get("status") in ("info", None))
            
            print(f"\n  Total stages: {len(results)}")
            print(f"  ✓ Success: {success_count}")
            print(f"  ✗ Failed: {fail_count}")
            print(f"  ℹ Info: {info_count}")
            
            print(f"\n  Stage-by-stage:")
            for i, r in enumerate(results, 1):
                status_icon = "✓" if r.get("status") == "ok" else ("✗" if r.get("status") == "fail" else "ℹ")
                stage = r.get("step", "unknown")
                details = r.get("details", "")
                if isinstance(details, dict):
                    details_str = json.dumps(details, default=str)[:80]
                else:
                    details_str = str(details)[:80]
                print(f"    {i:2d}. [{status_icon}] {stage:20s} {details_str}")
            
            # Check if we reached Step 2
            reached_step2 = any(
                "Step 2" in str(r.get("details", "")) or r.get("step") == "after_next_step"
                for r in results
            )
            print(f"\n  Reached Step 2: {'✓ YES' if reached_step2 else '✗ NO'}")
            print(f"\n  Results saved to: {results_path}")
            
            page.close()
            c.close()
            b.close()
    
    return results


if __name__ == "__main__":
    run_journey()
