#!/usr/bin/env python3
"""Drive the Post-a-Job wizard end-to-end using the llm-browser-driver.

Runs the LLM browser driver against Hauliage's Step 1 (cargo specs)
and Step 2 (pickup location) dropdowns to verify the custom dropdown
support works in a real exploration scenario.
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

from llm_browser_driver import BrowserDriver

FRONTEND_URL = "http://localhost:7174/shipper/post-a-job"
LLM_URL = "http://192.168.1.104:8000/v1"


def main():
    print("=" * 70)
    print("LLM Browser Driver: Post-a-Job Wizard Journey")
    print("=" * 70)
    print(f"Target: {FRONTEND_URL}")
    print(f"LLM: {LLM_URL}")
    print(f"Max iterations: 80")
    print()

    config_kwargs = {
        "url": FRONTEND_URL,
        "llm": {
            "api_url": LLM_URL,
            "model": "qwen3",
        },
        "agent": {"max_iterations": 80},
        "browser": {"headless": True},
    }

    driver = BrowserDriver(**config_kwargs)

    goal = (
        "Complete the Post-a-Job wizard from start to finish.\n"
        "Step 1 requires: selecting cargo type, load type, packaging, "
        "filling weight/dimensions fields, and providing a description. "
        "Step 2 requires: pickup address, country, state, city, and date/time.\n"
        "Use 'select_custom' action for dropdowns (they use custom buttons "
        "with chevron icons, not native <select> elements).\n"
        "Fill all required fields and click Next Step to advance between steps.\n"
        "Report any validation errors or blocks you encounter."
    )

    print("[1] Starting exploration...")
    start = time.time()

    result = driver.explore(
        url=FRONTEND_URL,
        goal=goal,
        max_iterations=80,
    )

    elapsed = time.time() - start

    print(f"\n[2] Exploration complete: {result.iterations} iterations, {elapsed:.0f}s")
    print(f"    Status: {result.status}")
    print(f"    Initial URL: {result.initial_url}")
    print(f"    Final URL: {result.final_url}")
    print(f"    Console errors: {len(result.console_errors)}")
    print(f"    Findings: {len(result.findings)}")

    # Show action history
    print(f"\n[3] Action history ({len(result.action_history)} actions):")
    for record in result.action_history:
        action = record.get("action", "?")
        params = record.get("parameters", {})
        result_text = record.get("result", "")[:100]
        print(f"  [{action:15s}] params={json.dumps(params, default=str)[:70]} → {result_text}")

    # Show console errors
    if result.console_errors:
        print(f"\n[4] Console errors ({len(result.console_errors)}):")
        for err in result.console_errors[:10]:
            print(f"  - {err.get('level', '?')}: {err.get('message', err.get('text', ''))[:120]}")

    # Show findings
    if result.findings:
        print(f"\n[5] Findings ({len(result.findings)}):")
        for f in result.findings:
            desc = f.get("description", f.get("summary", ""))[:120]
            print(f"  [{f.get('type', '?')}] {desc}")

    # Save
    results_path = Path("/tmp/post_job_journey.json")
    results_path.write_text(json.dumps({
        "iterations": result.iterations,
        "status": result.status,
        "initial_url": result.initial_url,
        "final_url": result.final_url,
        "console_errors": len(result.console_errors),
        "findings": result.findings,
        "error": result.error,
        "action_history": result.action_history,
        "elapsed_seconds": elapsed,
    }, indent=2, default=str))
    print(f"\n[6] Results saved to {results_path}")

    driver.close()

    # Final summary
    print("\n" + "=" * 70)
    print("JOURNEY SUMMARY")
    print("=" * 70)

    dropdown_actions = [r for r in result.action_history if r.get("action") == "select_custom"]
    fill_actions = [r for r in result.action_history if r.get("action") == "fill"]
    click_actions = [r for r in result.action_history if r.get("action") == "click"]

    print(f"  Total actions: {result.iterations}")
    print(f"  Dropdown selections: {len(dropdown_actions)}")
    print(f"  Text fills: {len(fill_actions)}")
    print(f"  Clicks: {len(click_actions)}")

    # Detect wizard progress
    step_reached = 1
    for record in result.action_history:
        result_text = record.get("result", "")
        if "Step 2" in result_text or "Step 2" in str(record.get("parameters", {}).get("element", "")):
            step_reached = max(step_reached, 2)
        if "Step 3" in result_text or "Step 3" in str(record.get("parameters", {}).get("element", "")):
            step_reached = max(step_reached, 3)
        if "Step 4" in result_text or "Step 4" in str(record.get("parameters", {}).get("element", "")):
            step_reached = max(step_reached, 4)
        if "Step 5" in result_text or "Step 5" in str(record.get("parameters", {}).get("element", "")):
            step_reached = max(step_reached, 5)
        if "Step 6" in result_text or "Step 6" in str(record.get("parameters", {}).get("element", "")):
            step_reached = max(step_reached, 6)
        if "Step 7" in result_text or "Step 7" in str(record.get("parameters", {}).get("element", "")):
            step_reached = max(step_reached, 7)
        if "posted-jobs" in record.get("url", "").lower():
            step_reached = 99  # Complete!

    print(f"  Steps reached: {step_reached}")

    # LLM summary
    for f in result.findings:
        if f.get("type") == "summary":
            print(f"\n  LLM Summary:\n  {f.get('description', '')[:500]}")


if __name__ == "__main__":
    main()
