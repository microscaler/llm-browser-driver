"""Minimal debug test: check if nav fallback triggers."""
import json
import os
import sys
from pathlib import Path

os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

# Ensure hauliage config is available
_hauliage_config_paths = [
    Path("/home/casibbald/Workspace/microscaler/hauliage/microservices/consignments/impl/tests"),
    Path("/home/casibbald/Workspace/microscaler/hauliage/microservices/consignments/impl/tests"),
]
for p in _hauliage_config_paths:
    if p.exists():
        sys.path.insert(0, str(p))
        break

from playwright.sync_api import sync_playwright
from llm_browser_driver.config import load_config
from llm_browser_driver.state import (
    get_page_state,
    build_page_summary,
    build_action_history_summary,
)
from llm_browser_driver.llm_client import LLMClient, parse_action_from_response
from llm_browser_driver.actions import execute_action
from llm_browser_driver.agent import INTERACTIVE_SYSTEM_PROMPT

config = load_config(
    url="http://localhost:7174/shipper/post-a-job",
    llm={"api_url": "http://192.168.1.104:8000/v1", "model": "qwen3"},
)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1280, "height": 720})
    pg = c.new_page()
    pg.goto("http://localhost:7174/shipper/post-a-job", wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)

    llm = LLMClient(config)
    system_prompt = INTERACTIVE_SYSTEM_PROMPT.format(max_iter=80)
    goal = "Complete the Post-a-Job wizard"

    action_history = []

    for iteration in range(1, 20):
        snapshot = get_page_state(pg)
        page_summary = build_page_summary(snapshot)
        history_summary = build_action_history_summary(action_history)

        # Heuristic
        fill_count = len([r for r in action_history if r.get("action") == "fill"])
        dropdown_actions = [
            r
            for r in action_history
            if r.get("action") in ("select_custom", "select")
        ]
        nav_attempted = any(
            r.get("action") == "click" and "Next" in str(r.get("result", ""))
            for r in action_history
        )
        nav_buttons = [
            btn
            for btn in snapshot.get("details", {}).get("buttons", [])
            if btn.get("text", "")
            in ("Next Step", "Next", "Continue", "Submit")
            and not btn.get("disabled", False)
        ]

        navigation_hint = ""
        auto_click_nav = False
        if (
            fill_count >= 3
            and len(dropdown_actions) >= 3
            and nav_buttons
            and not nav_attempted
        ):
            btn_text = ", ".join(b["text"] for b in nav_buttons)
            navigation_hint = (
                "\n**NAVIGATION SUGGESTION**: All form fields filled. "
                "Nav buttons: " + btn_text + ". Click one to proceed.\n"
            )
            auto_click_nav = True
            print(
                f"[ITER {iteration}] NAV HINT TRIGGERED: "
                f"fill={fill_count}, dropdowns={len(dropdown_actions)}, nav={btn_text}",
                flush=True,
            )

        user_prompt = (
            "TASK: " + goal + "\n\n"
            + history_summary + "\n\n"
            "CURRENT PAGE STATE:\n"
            + page_summary + "\n"
            + navigation_hint + "\n\n"
            "Based on the goal, action history, and current page state, "
            "decide the next action to take.\n"
        )

        llm_response = llm.chat(system_prompt, user_prompt)
        action = parse_action_from_response(llm_response)

        # Fallback
        print(
            f"[ITER {iteration}] LLM said: {action.get('action')}, auto_click_nav={auto_click_nav}",
            flush=True,
        )

        if auto_click_nav and action.get("action") != "click":
            nav_btn_text = nav_buttons[0]["text"]
            print(
                f"[ITER {iteration}] FALLBACK: forcing click '{nav_btn_text}'",
                flush=True,
            )
            action = {"action": "click", "element": nav_btn_text, "auto_forced": True}
        else:
            print(f"[ITER {iteration}] No fallback triggered", flush=True)

        try:
            result_msg, is_done = execute_action(pg, action)
        except Exception as e:
            print(f"[ITER {iteration}] ERROR executing action: {e}", flush=True)
            break

        action_record = {
            "step": iteration,
            "action": action.get("action", "unknown"),
            "parameters": {
                k: v for k, v in action.items() if k != "action"
            },
            "result": result_msg[:200],
            "url": pg.url,
        }
        action_history.append(action_record)

        print(f"  -> {result_msg[:100]}", flush=True)

        if is_done or action.get("action") == "done":
            print(f"DONE at iteration {iteration}", flush=True)
            break

        if pg.url != "http://localhost:7174/shipper/post-a-job":
            print(f"NAVIGATED AWAY: {pg.url}", flush=True)
            break

    print(f"\nFinal URL: {pg.url}", flush=True)
    print(f"Total actions: {len(action_history)}", flush=True)

    results = {
        "iterations": len(action_history),
        "status": "success",
        "final_url": pg.url,
        "action_history": action_history,
    }
    Path("/tmp/debug_test.json").write_text(
        json.dumps(results, indent=2, default=str)
    )

    pg.close()
    c.close()
    b.close()

print("\nDebug results saved to /tmp/debug_test.json", flush=True)
