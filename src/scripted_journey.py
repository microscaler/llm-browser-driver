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
from hauliage_driver_config import HauliageDriverConfig

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
    trigger = find_custom_dropdown_trigger(page, trigger_text)
    if not trigger:
        return False, f"Could not find dropdown trigger: {trigger_text}"
    
    trigger.click()
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
            
            print("\n[7/9] Step 1: Filling weight/dimensions...")
            success1, msg1 = fill_field(page, "18000", "15000")
            print(f"     Weight: {msg1} → {'✓' if success1 else '✗'}")
            success2, msg2 = fill_field(page, "67.2", "12")
            print(f"     Length: {msg2} → {'✓' if success2 else '✗'}")
            results.append({"step": "dimensions", "status": "ok" if success1 and success2 else "fail", 
                           "details": f"{msg1}, {msg2}"})
            
            # Check if Next Step is enabled
            print("\n[8/9] Checking if Next Step is enabled...")
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
                    print("\n[11/9] Step 2: Trying to select pickup country...")
                    countries = HauliageDriverConfig.PICKUP_COUNTRIES
                    if countries:
                        first_country = countries[0]["name"]
                        print(f"     First available country: {first_country}")
                        page.wait_for_timeout(500)
                        success, msg = select_dropdown(page, "Select country", first_country)
                        print(f"     {msg} → {'✓' if success else '✗'}")
                        results.append({"step": "pickup_country", "status": "ok" if success else "fail", "details": msg})
                        
                        if success:
                            # Check for state/province dropdown
                            page.wait_for_timeout(1000)
                            info = get_page_info(page)
                            print(f"\n     After country selection:")
                            print(f"     Step: {info['step']}")
                            print(f"     Buttons: {info['buttons']}")
                            results.append({"step": "after_country_select", "details": info})
                    else:
                        print("     No countries configured in hauliage_driver_config")
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
                details = r.get("details", "")[:80]
                print(f"    {i:2d}. [{status_icon}] {stage:20s} {details}")
            
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
