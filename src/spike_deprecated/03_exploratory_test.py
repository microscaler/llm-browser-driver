#!/usr/bin/env python3
"""
Spike: Use browser-use to explore the Hauliage frontend and identify issues
that deterministic BDD tests might miss.
"""

import asyncio
import json
from pathlib import Path
from browser_use import Agent, BrowserSession, SystemPrompt
from browser_use.llm.litellm.chat import ChatLiteLLM

FRONTEND_URL = "http://localhost:7174"
LLM_API_URL = "http://192.168.1.104:8000/v1"
LLM_MODEL = "qwen3"


async def main():
    # Use LiteLLM as the LLM backend (supports any OpenAI-compatible endpoint)
    llm = ChatLiteLLM(
        model=LLM_MODEL,
        api_base=LLM_API_URL,
        api_key="placeholder",  # Their server doesn't require auth
        max_tokens=8192,
    )

    # Check frontend accessibility
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(FRONTEND_URL, timeout=5) as resp:
                status = resp.status
                print(f"Frontend status: {status}")
                if status != 200:
                    print("Frontend not ready. Skipping.")
                    return
        except Exception as e:
            print(f"Frontend not reachable: {e}")
            return

    # Create browser session (headless, no user profile)
    browser = BrowserSession(
        headless=True,
        user_data_dir=None,
        disable_security=True,
    )

    tasks = [
        "Navigate to the homepage at {url}. Report what you see: the page title, any navigation links, buttons visible. Is there a 'Post a Job' button?",
        "Look for any JavaScript errors or console warnings on the page. Report any errors or warnings you detect.",
        "Find the pickup country dropdown or any select element on the page. Try to click it. Report if it's enabled, disabled, or in a loading state.",
    ]

    results = []

    for i, task in enumerate(tasks):
        task_text = task.replace("{url}", FRONTEND_URL)
        print(f"\n{'='*60}")
        print(f"TASK {i+1}/{len(tasks)}: {task_text}")
        print('='*60)

        try:
            agent = Agent(
                task=task_text,
                llm=llm,
                browser_session=browser,
                max_actions_per_step=5,
                max_failures=3,
                generate_gif=False,
                system_prompt=SystemPrompt(
                    override_system_message="You are a QA tester exploring a web app. Report what you observe about the UI, navigation, errors, and usability.",
                ),
            )

            result = await agent.run()

            results.append({
                "task": task_text,
                "success": result.success,
                "metrics": {
                    "total_steps": result.metrics.total_steps,
                    "total_tokens": result.metrics.total_tokens,
                    "total_cost": result.metrics.total_cost,
                },
                "last_error": result.last_error,
            })

        except Exception as e:
            results.append({
                "task": task_text,
                "error": str(e),
            })

    # Save results
    output_path = Path("exploratory_results.json")
    output_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
