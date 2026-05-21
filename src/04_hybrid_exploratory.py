#!/usr/bin/env python3
"""
Spike: LLM-Augmented Exploratory Testing for Hauliage Frontend

Uses Playwright for reliable browser interaction + LLM for analyzing
page state, console errors, and identifying UX issues.

This is the practical approach — Playwright handles the browser,
the LLM analyzes what it sees and flags issues.
"""

import asyncio
import json
import os
from pathlib import Path
from openai import AsyncOpenAI
from playwright.async_api import async_playwright, Page, BrowserContext

FRONTEND_URL = "http://localhost:7174"
LLM_API_URL = "http://192.168.1.104:8000/v1"
LLM_MODEL = "qwen3"


def get_page_snapshot(page: Page) -> dict:
    """Capture the current page state for LLM analysis."""
    return {
        "title": page.title(),
        "url": page.url,
        "console_errors": [],  # populated below
        "forms": {
            "input_count": len(page.locator("input:not([type=hidden]):not([type=submit]):not([type=button])").all()),
            "textarea_count": len(page.locator("textarea").all()),
            "button_count": len(page.locator("button, [role=button]").all()),
            "dropdown_count": len(page.locator("select, [role=combobox], [role=listbox]").all()),
            "disabled_inputs": len(page.locator('input:disabled, textarea:disabled, button:disabled').all()),
        },
        "accessibility_tree": [],  # simplified
    }


async def capture_console(page: Page) -> list[str]:
    """Capture console messages."""
    console_messages = []

    def on_console(msg):
        console_messages.append(
            f"[{msg.type}] {msg.text}"
        )

    page.on("console", on_console)

    # Wait briefly for any async console output
    await asyncio.sleep(1)
    return console_messages


async def analyze_with_llm(client: AsyncOpenAI, model: str, snapshot: dict, task_desc: str) -> str:
    """Send page state to LLM for analysis."""
    system_prompt = """You are a QA analyst analyzing a web application. 
Report findings in this structured format:

FINDINGS:
- [CRITICAL] Issue description
- [WARNING] Issue description
- [INFO] Observation

SUGGESTED BDD TESTS:
- Scenario title: brief description

Focus on: navigation issues, disabled elements, loading states, 
console errors, unexpected UI states, accessibility problems."""

    # Keep snapshot concise for token limits
    analysis_input = f"""
Task: {task_desc}

Page Title: {snapshot['title']}
URL: {snapshot['url']}

Form Elements:
- Inputs: {snapshot['forms']['input_count']}
- Textareas: {snapshot['forms']['textarea_count']}
- Buttons: {snapshot['forms']['button_count']}
- Dropdowns: {snapshot['forms']['dropdown_count']}
- Disabled elements: {snapshot['forms']['disabled_inputs']}

Console Errors: {snapshot['console_errors'][:5]} if available

Please analyze this page and report any issues.
"""

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": analysis_input},
        ],
        max_tokens=2048,
        temperature=0.3,
    )

    return response.choices[0].message.content


async def run_exploratory_tests():
    """Run the full exploratory test suite."""
    client = AsyncOpenAI(
        base_url=LLM_API_URL,
        api_key="placeholder",
    )

    # Check frontend
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(FRONTEND_URL, timeout=5) as resp:
                if resp.status != 200:
                    print(f"Frontend not ready ({resp.status}). Skipping.")
                    return
        except Exception as e:
            print(f"Frontend unreachable: {e}")
            return

    print(f"Frontend ready at {FRONTEND_URL}")
    print(f"LLM: {LLM_API_URL}/{LLM_MODEL}")

    tests = [
        {
            "name": "Homepage",
            "url": FRONTEND_URL,
            "actions": "capture_state_and_analyze",
            "llm_task": "Analyze the homepage. Look for: loading states, navigation issues, broken links, console errors, empty/blank areas that should contain content."
        },
        {
            "name": "Post a Job",
            "url": f"{FRONTEND_URL}/shipper/post-a-job",
            "actions": "navigate_and_analyze",
            "llm_task": "Analyze the post-a-job form. Look for: disabled inputs, loading dropdowns, validation errors, incomplete fields, console errors."
        },
        {
            "name": "Job List",
            "url": f"{FRONTEND_URL}/shipper/my-jobs",
            "actions": "navigate_and_analyze",
            "llm_task": "Analyze the job list page. Look for: empty state handling, loading states, broken links, console errors."
        },
    ]

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )

        for i, test in enumerate(tests):
            print(f"\n{'='*70}")
            print(f"TEST {i+1}/{len(tests)}: {test['name']}")
            print(f"URL: {test['url']}")
            print('='*70)

            page = await context.new_page()

            # Capture console
            console_msgs = []
            page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

            try:
                # Navigate
                await page.goto(test['url'], wait_until="domcontentloaded", timeout=30000)
                # Wait for network to settle
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(2)  # Extra wait for JS to settle

                # Get console messages
                console = console_msgs.copy()

                # Get snapshot
                snapshot = {
                    "title": await page.title(),
                    "url": page.url,
                    "console_errors": [m for m in console if "error" in m.lower() or "[error]" in m.lower()],
                    "forms": {
                        "input_count": len(await page.locator("input:not([type=hidden]):not([type=submit]):not([type=button])").all()),
                        "textarea_count": len(await page.locator("textarea").all()),
                        "button_count": len(await page.locator("button, [role=button]").all()),
                        "dropdown_count": len(await page.locator("select, [role=combobox], [role=listbox]").all()),
                        "disabled_inputs": len(await page.locator('input:disabled, textarea:disabled, button:disabled').all()),
                    },
                }

                # LLM analysis
                llm_analysis = await analyze_with_llm(client, LLM_MODEL, snapshot, test['llm_task'])

                results.append({
                    "test": test['name'],
                    "url": test['url'],
                    "title": snapshot['title'],
                    "console_errors": snapshot['console_errors'],
                    "form_stats": snapshot['forms'],
                    "llm_analysis": llm_analysis,
                    "status": "success",
                })

            except Exception as e:
                results.append({
                    "test": test['name'],
                    "url": test['url'],
                    "status": "error",
                    "error": str(e),
                })

            finally:
                await page.close()

        await browser.close()

    # Save results
    output_path = Path("exploratory_results.json")
    output_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n{'='*70}")
    print(f"Results saved to {output_path}")

    # Print summary
    print("\nSUMMARY:")
    print(f"  Tests run: {len(results)}")
    print(f"  Success: {sum(1 for r in results if r.get('status') == 'success')}")
    print(f"  Errors: {sum(1 for r in results if r.get('status') == 'error')}")

    return results


if __name__ == "__main__":
    asyncio.run(run_exploratory_tests())
