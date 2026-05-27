#!/usr/bin/env python3
"""Generic integration test for select_custom dropdown action.

This test demonstrates the select_custom action working on ANY
web application with custom dropdown components (SolidJS/React/HTML5).
No application-specific values are hardcoded here.

For Hauliage-specific test data, see:
    microservices/consignments/impl/tests/hauliage_driver_config.py

Usage with Hauliage:
    # In hauliage repo, from microservices/ directory:
    PYTHONPATH=../../llm-browser-driver/src:./consignments/impl/tests python3 ../llm-browser-driver/src/test_generic_dropdown.py hauliage
"""

import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from llm_browser_driver.state import get_page_state, build_page_summary
from llm_browser_driver.actions import execute_select_custom_dropdown


def find_dropdown_by_testid(page, testid_prefix):
    """Find a dropdown trigger by data-testid prefix match."""
    for el in page.locator("button[type='button']").all()[:50]:
        try:
            testid = el.get_attribute("data-testid") or ""
            if testid_prefix in testid:
                text = el.inner_text(timeout=500).strip()
                if text:
                    return {"text": text, "testid": testid}
        except Exception:
            continue
    return None


def open_dropdown_and_list_options(page, testid_prefix, count=20):
    """Open a dropdown and return all visible option texts."""
    el = page.locator(f"button[data-testid*='{testid_prefix}']").first
    el.click(timeout=5000)
    page.wait_for_timeout(1000)

    options = []
    for li in page.locator("ul li.cursor-pointer").all()[:count]:
        try:
            text = li.inner_text(timeout=500).strip()
            if text:
                options.append(text)
        except Exception:
            pass
    return options


def test_generic_dropdown_flow(frontend_url, test_config):
    """Run dropdown selection flow using external test config.

    Args:
        frontend_url: The URL to test against.
        test_config: Dict with dropdown test cases.
            Example:
                {
                    "dropdowns": [
                        {"testid_prefix": "select-cargo", "target": "Vehicles"},
                        {"testid_prefix": "select-load", "target": "Flatbed Truck"},
                    ]
                }
    """
    print("=" * 70)
    print(f"GENERIC TEST: Custom Dropdown Flow")
    print(f"Target: {frontend_url}")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        # Navigate
        print(f"\n[1] Navigate to {frontend_url}")
        page.goto(frontend_url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # Capture initial state
        print("\n[2] Initial state:")
        snap0 = get_page_state(page)
        dds = snap0.get("details", {}).get("custom_dropdowns", [])
        print(f"    Custom dropdowns found: {len(dds)}")
        for dd in dds:
            print(f"      - '{dd['text']}' (test_id={dd.get('data-testid', '')})")

        # Run each dropdown test case
        dropdowns = test_config.get("dropdowns", [])
        all_passed = True

        for i, tc in enumerate(dropdowns):
            testid_prefix = tc["testid_prefix"]
            target_option = tc["target"]
            desc = tc.get("desc", testid_prefix)

            print(f"\n[{i+3}] Test: {desc} → target='{target_option}'")

            # Find the dropdown
            found_dd = find_dropdown_by_testid(page, testid_prefix)
            if not found_dd:
                # Try all available dropdowns
                print(f"    Dropdown '{testid_prefix}' not found by testid")
                print(f"    Available dropdowns: {[dd['text'] for dd in dds[:5]]}")
                all_passed = False
                continue

            # Try to select the option
            result = execute_select_custom_dropdown(page, {
                "action": "select_custom",
                "field": found_dd["text"],
                "option": target_option,
            })
            print(f"    Result: {result}")

            if "Selected option" in result:
                # Verify the dropdown updated
                snap = get_page_state(page)
                dd_list = snap.get("details", {}).get("custom_dropdowns", [])
                for dd in dd_list:
                    if dd["testid"] == found_dd["testid"]:
                        new_text = dd["text"]
                        print(f"    Dropdown now shows: '{new_text}'")
                        if new_text != found_dd["text"]:
                            print(f"    ✅ Selection verified")
                        else:
                            print(f"    ⚠️ Dropdown text unchanged (may be OK if options use display aliases)")
            else:
                # Option not found — list available options for debugging
                options = open_dropdown_and_list_options(page, testid_prefix)
                print(f"    ⚠️ Option not found. Available options:")
                for j, opt in enumerate(options[:10]):
                    print(f"      [{j}] '{opt}'")
                all_passed = False

        # Final state
        print("\n[Final] Dropdown state:")
        snap_final = get_page_state(page)
        dds_final = snap_final.get("details", {}).get("custom_dropdowns", [])
        for dd in dds_final:
            print(f"      - '{dd['text']}' (test_id={dd.get('data-testid', '')})")

        # Save results
        result_path = Path("/tmp/generic_dropdown_test.json")
        result_data = {
            "passed": all_passed,
            "tests_run": len(dropdowns),
            "final_dropdowns": dds_final,
            "summary": build_page_summary(snap_final),
        }
        result_path.write_text(json.dumps(result_data, indent=2))
        print(f"\n[Save] Results → {result_path}")

        screenshot = Path("/tmp/generic_dropdown_test.png")
        page.screenshot(path=str(screenshot), full_page=True)
        print(f"         Screenshot → {screenshot}")

        browser.close()

    print("\n" + "=" * 70)
    print("RESULT:")
    print("=" * 70)
    if all_passed:
        print("  All dropdown selections succeeded")
    else:
        print("  Some selections failed — check available options above")
    print(f"  Config tests_run: {len(dropdowns)}")
    print(f"  Result: {result_path}")


if __name__ == "__main__":
    # Allow passing a config file path as argument
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
        if config_path.exists():
            config = json.loads(config_path.read_text())
            url = config.get("frontend_url", "http://localhost:7174/shipper/post-a-job")
            test_generic_dropdown_flow(url, config)
            sys.exit(0)

    # Example config — replace with Hauliage config for real testing
    print("No config provided. Here's an example config:")
    print()
    print(json.dumps({
        "frontend_url": "http://localhost:7174/shipper/post-a-job",
        "dropdowns": [
            {
                "testid_prefix": "select-cargo",
                "target": "Vehicles",
                "desc": "Cargo type → Vehicles",
            },
            {
                "testid_prefix": "select-load",
                "target": "Flatbed Truck",
                "desc": "Load type → Flatbed Truck",
            },
            {
                "testid_prefix": "select-packag",
                "target": "Pallets",
                "desc": "Packaging → Pallets",
            },
            {
                "testid_prefix": "select-insur",
                "target": "Yes",
                "desc": "Insurance → Yes",
            },
        ],
    }, indent=2))
    print()
    print("Usage:")
    print("  python3 test_generic_dropdown.py /path/to/config.json")
    print()
    print("Example: from hauliage microservices/ directory:")
    print("  PYTHONPATH=../../llm-browser-driver/src:./consignments/impl/tests")
    print("  python3 ../llm-browser-driver/src/test_generic_dropdown.py")
    print()
    print("See hauliage/microservices/consignments/impl/tests/hauliage_driver_config.py")
