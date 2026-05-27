"""Complete scripted journey — fills ALL wizard steps programmatically."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hauliage" / "microservices" / "consignments" / "impl" / "tests"))

from playwright.sync_api import sync_playwright
from hauliage_driver_config import PICKUP_COUNTRY_OPTIONS, PICKUP_STATE_OPTIONS
import json
from datetime import datetime
from collections import defaultdict

def select_dropdown(page, trigger_text, option_text):
    """Open custom dropdown and select option by text."""
    btn = page.locator(f"text={trigger_text}", has_text=trigger_text).first
    if btn.count() == 0:
        return False, f"No button found for: {trigger_text}"
    btn.click()
    page.wait_for_timeout(500)
    option = page.locator("li.cursor-pointer", has_text=option_text).first
    if option.count() == 0:
        available = [o.inner_text() for o in page.locator("li.cursor-pointer").all()[:20]]
        return False, f"Option '{option_text}' not found. Available: {', '.join(available)}"
    option.click()
    page.wait_for_timeout(200)
    return True, f"Selected option '{option_text}'"


def fill_field(page, field_text, value, testid=None):
    """Fill input/textarea by testid or label text."""
    if testid:
        loc = page.locator(f"[data-testid='{testid}']")
        if loc.count() > 0:
            loc.first.fill(value, timeout=5000)
            return True, f"Filled '{testid}'"
    # Search by visible text (label/placeholder)
    all_inputs = page.locator("input:not([type=hidden]):not([type=submit]):not([type=button]), textarea")
    for inp in all_inputs.all()[:50]:
        try:
            tid = inp.get_attribute("data-testid") or ""
            ph = inp.get_attribute("placeholder") or ""
            if field_text.lower() in ph.lower() or tid == field_text:
                inp.fill(value, timeout=5000)
                return True, f"Filled '{tid or ph}'"
        except Exception:
            continue
    return False, f"Could not find field: {field_text}"


def next_step(page, max_wait=3000):
    """Click Next Step and wait for transition."""
    btn = page.locator("button", has_text="Next Step").first
    if btn.count() == 0:
        return False, "No Next Step button found"
    btn.click()
    page.wait_for_timeout(max_wait)
    return True, "Next Step clicked"


def check_step(page):
    """Get current step text from the page."""
    for selector in ["h2", "h3", "[class*='step-title']", "[class*='step-header']"]:
        try:
            header = page.locator(selector).first
            if header.count() > 0:
                text = header.inner_text()
                if "Step" in text or "Delivery" in text or "Pickup" in text:
                    return text.strip()
        except Exception:
            continue
    return "Unknown step"


def run_journey():
    results = defaultdict(dict)
    start_time = datetime.now()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        
        try:
            # Navigate to post-a-job
            page.goto("http://localhost:7174/shipper/post-a-job", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            print(f"[INIT] Page loaded: {page.url}")
            print(f"[INIT] Current step: {check_step(page)}")
            
            # ===== STEP 1: Shipment Details =====
            print("\n" + "="*60)
            print("STEP 1: Shipment Details")
            print("="*60)
            
            # Dropdowns (order: cargo, load, packaging, insurance)
            dropdowns = [
                ("Select cargo type", "Vehicles"),
                ("Select load type", "Flatbed Truck"),
                ("Select packaging", "Pallets"),
                ("Select option", "Yes - Full Coverage"),
            ]
            for trigger, option in dropdowns:
                ok, msg = select_dropdown(page, trigger, option)
                results["step1"][f"{trigger}"] = {"option": option, "ok": ok, "msg": msg}
                print(f"  [{trigger}] {option} → {'✓' if ok else '✗'} {msg}")
            
            # Fill text fields
            fields = [
                ("input-description", "Test description for shipment"),
                ("input-job-title", "Test Job Title"),
                ("input-weight", "15000"),
                ("input-volume", "50"),
                ("input-packages", "48"),
                ("input-cargo-value", "45000"),
            ]
            for testid, value in fields:
                ok, msg = fill_field(page, testid, value, testid=testid)
                results["step1"][testid] = {"ok": ok, "msg": msg}
                print(f"  [{testid}] {value[:30]} → {'✓' if ok else '✗'}")
            
            # Click Next Step
            print("\n  [Next Step] Clicking...")
            ok, msg = next_step(page)
            results["step1"]["next_step"] = {"ok": ok, "msg": msg}
            print(f"  → {'✓' if ok else '✗'} {msg}")
            
            # Verify transition
            step = check_step(page)
            print(f"\n  [VERIFY] Current step: {step}")
            results["step1"]["next_step_success"] = "Step 2" in step
            print(f"  [VERIFY] Transitioned to Step 2: {results['step1']['next_step_success']}")
            
            if not results["step1"]["next_step_success"]:
                print("\n  ✗✗✗ FAILED: Step 1 → Step 2 transition failed")
                print(f"  Got step: {step}")
                # Take screenshot for debugging
                page.screenshot(path="/tmp/step1_fail.png")
                browser.close()
                return results
            
            # ===== STEP 2: Pickup Location =====
            print("\n" + "="*60)
            print("STEP 2: Pickup Location")
            print("="*60)
            
            # Country dropdown (API returns provinces)
            print("  2a. Selecting country...")
            first_country = PICKUP_COUNTRY_OPTIONS[0]["name"] if isinstance(PICKUP_COUNTRY_OPTIONS[0], dict) else PICKUP_COUNTRY_OPTIONS[0]
            ok, msg = select_dropdown(page, "Select country", first_country)
            results["step2"]["country"] = {"option": first_country, "ok": ok, "msg": msg}
            print(f"  [country] {first_country} → {'✓' if ok else '✗'} {msg}")
            
            # Wait for API to populate states
            page.wait_for_timeout(2000)
            
            # State dropdown
            print("  2b. Selecting state...")
            state_btn = page.locator("[data-testid='select-pickup-state']").first
            if state_btn.count() > 0:
                state_btn.click()
                page.wait_for_timeout(500)
                state_options = page.locator("li.cursor-pointer").all()
                if state_options:
                    state_name = state_options[0].inner_text().strip()
                    state_options[0].click()
                    page.wait_for_timeout(500)
                    results["step2"]["state"] = {"option": state_name, "ok": True}
                    print(f"  [state] {state_name} → ✓")
                else:
                    results["step2"]["state"] = {"ok": False, "msg": "No state options found"}
                    print(f"  [state] ✗ No options found")
            else:
                results["step2"]["state"] = {"ok": False, "msg": "No state button found"}
                print(f"  [state] ✗ No state button")
            
            # City dropdown
            print("  2c. Selecting city...")
            city_btn = page.locator("[data-testid='select-pickup-city']").first
            if city_btn.count() > 0:
                city_btn.click()
                page.wait_for_timeout(500)
                city_options = page.locator("li.cursor-pointer").all()
                if city_options:
                    city_name = city_options[0].inner_text().strip()
                    city_options[0].click()
                    page.wait_for_timeout(500)
                    results["step2"]["city"] = {"option": city_name, "ok": True}
                    print(f"  [city] {city_name} → ✓")
                else:
                    results["step2"]["city"] = {"ok": False, "msg": "No city options"}
                    print(f"  [city] ✗ No options")
            else:
                results["step2"]["city"] = {"ok": False, "msg": "No city button"}
                print(f"  [city] ✗ No button")
            
            # Wait for address to be enabled
            page.wait_for_timeout(1000)
            
            # Fill address, date, times
            print("  2d. Filling address, date, times...")
            addr_fields = [
                ("input-pickup-address", "123 Test Street"),
                ("input-pickup-date", "2026-06-15"),
                ("input-pickup-time-start", "09:00"),
                ("input-pickup-time-end", "17:00"),
            ]
            for testid, value in addr_fields:
                ok, msg = fill_field(page, testid, value, testid=testid)
                results["step2"][testid] = {"ok": ok, "msg": msg}
                print(f"  [{testid}] {value[:30]} → {'✓' if ok else '✗'}")
            
            # Click Next Step
            print("\n  [Next Step] Clicking...")
            ok, msg = next_step(page)
            results["step2"]["next_step"] = {"ok": ok, "msg": msg}
            print(f"  → {'✓' if ok else '✗'} {msg}")
            
            # Verify transition
            step = check_step(page)
            print(f"\n  [VERIFY] Current step: {step}")
            results["step2"]["next_step_success"] = "Step 3" in step or "Delivery" in step
            print(f"  [VERIFY] Transitioned to Step 3: {results['step2']['next_step_success']}")
            
            if not results["step2"]["next_step_success"]:
                print("\n  ✗✗✗ FAILED: Step 2 → Step 3 transition failed")
                page.screenshot(path="/tmp/step2_fail.png")
                browser.close()
                return results
            
            # ===== STEP 3: Delivery Location =====
            print("\n" + "="*60)
            print("STEP 3: Delivery Location")
            print("="*60)
            
            # Country dropdown
            print("  3a. Selecting country...")
            ok, msg = select_dropdown(page, "Select country", first_country)
            results["step3"]["country"] = {"option": first_country, "ok": ok, "msg": msg}
            print(f"  [country] {first_country} → {'✓' if ok else '✗'} {msg}")
            
            page.wait_for_timeout(2000)
            
            # State dropdown
            print("  3b. Selecting state...")
            state_btn = page.locator("[data-testid='select-delivery-state']").first
            if state_btn.count() > 0:
                state_btn.click()
                page.wait_for_timeout(500)
                state_options = page.locator("li.cursor-pointer").all()
                if state_options:
                    state_name = state_options[0].inner_text().strip()
                    state_options[0].click()
                    page.wait_for_timeout(500)
                    results["step3"]["state"] = {"option": state_name, "ok": True}
                    print(f"  [state] {state_name} → ✓")
            else:
                results["step3"]["state"] = {"ok": False, "msg": "No state button"}
                print(f"  [state] ✗ No button")
            
            # City dropdown
            print("  3c. Selecting city...")
            city_btn = page.locator("[data-testid='select-delivery-city']").first
            if city_btn.count() > 0:
                city_btn.click()
                page.wait_for_timeout(500)
                city_options = page.locator("li.cursor-pointer").all()
                if city_options:
                    city_name = city_options[0].inner_text().strip()
                    city_options[0].click()
                    page.wait_for_timeout(500)
                    results["step3"]["city"] = {"option": city_name, "ok": True}
                    print(f"  [city] {city_name} → ✓")
            else:
                results["step3"]["city"] = {"ok": False, "msg": "No city button"}
                print(f"  [city] ✗ No button")
            
            page.wait_for_timeout(1000)
            
            # Fill remaining fields
            print("  3d. Filling address, date, times...")
            for testid, value in addr_fields:
                ok, msg = fill_field(page, testid, value, testid=testid)
                results["step3"][testid] = {"ok": ok, "msg": msg}
                print(f"  [{testid}] {value[:30]} → {'✓' if ok else '✗'}")
            
            # Click Next Step
            print("\n  [Next Step] Clicking...")
            ok, msg = next_step(page)
            results["step3"]["next_step"] = {"ok": ok, "msg": msg}
            print(f"  → {'✓' if ok else '✗'} {msg}")
            
            step = check_step(page)
            results["step3"]["next_step_success"] = "Step 4" in step or "Cargo" in step
            print(f"\n  [VERIFY] Current step: {step}")
            print(f"  [VERIFY] Transitioned to Step 4: {results['step3']['next_step_success']}")
            
            # Final summary
            elapsed = (datetime.now() - start_time).total_seconds()
            print("\n" + "="*60)
            print("FINAL RESULTS")
            print("="*60)
            
            for step_name in ["step1", "step2", "step3"]:
                print(f"\n  {step_name.upper().replace('_', ' ')}:")
                all_ok = True
                for key, val in results[step_name].items():
                    ok = val.get('ok', False)
                    icon = '✓' if ok else '✗'
                    if not ok:
                        all_ok = False
                    print(f"    {icon} {key}: {val.get('msg', val.get('option', ''))[:50]}")
                print(f"  Step {step_name} ALL OK: {all_ok}")
            
            print(f"\n  Total time: {elapsed:.1f}s")
            
            # Save results
            output_path = "/tmp/scripted_journey_complete.json"
            with open(output_path, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\n  Results saved to {output_path}")
            
        except Exception as e:
            import traceback
            print(f"\n✗✗✗ EXCEPTION: {e}")
            traceback.print_exc()
            page.screenshot(path="/tmp/journey_crash.png")
        finally:
            browser.close()
    
    return results


if __name__ == "__main__":
    results = run_journey()
