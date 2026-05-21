#!/usr/bin/env python3
"""
Spike: Use browser-use to explore the Hauliage frontend and identify issues
that deterministic BDD tests might miss.
"""

import asyncio
import json
from pathlib import Path
from openai import AsyncOpenAI

FRONTEND_URL = "http://localhost:7174"
LLM_API_URL = "http://192.168.1.104:8000/v1"
LLM_MODEL = "qwen3"

async def main():
    # Initialize OpenAI-compatible client
    client = AsyncOpenAI(
        base_url=LLM_API_URL,
        api_key="placeholder"
    )
    
    # Verify LLM connectivity
    try:
        models = await client.models.list()
        model_list = [m.id for m in models.data]
        print(f"LLM models available: {model_list}")
    except Exception as e:
        print(f"LLM connection failed: {e}")
        return
    
    from browser_use import Agent, BrowserSession
    
    # Check frontend accessibility
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(FRONTEND_URL, timeout=5) as resp:
                status = resp.status
                print(f"Frontend status: {status}")
        except Exception as e:
            print(f"Frontend not reachable: {e}")
            return
    
    # Create browser session (not async context manager)
    browser = BrowserSession(headless=True, user_data_dir=None)
    
    tasks = [
        "Navigate to the homepage. Report what you see: the title, any navigation links, buttons visible. Is there a 'Post a Job' button?",
        "Check for JavaScript console errors on the page. Report any errors or warnings you can detect.",
        "Try to interact with any dropdown or select element you find. Report if it's enabled, disabled, or in a loading state.",
    ]
    
    results = []
    
    for i, task in enumerate(tasks):
        print(f"\n{'='*60}")
        print(f"TASK {i+1}/{len(tasks)}: {task}")
        print('='*60)
        
        try:
            agent = Agent(
                task=task,
                llm=client,
                model=LLM_MODEL,
                browser_session=browser,
                max_actions_per_step=5,
                generate_gif=False,
            )
            
            result = await agent.run()
            
            results.append({
                "task": task,
                "success": result.success,
                "metrics": result.metrics.__dict__ if hasattr(result.metrics, '__dict__') else str(result.metrics),
                "last_error": result.last_error,
            })
            
        except Exception as e:
            results.append({
                "task": task,
                "error": str(e),
            })
    
    # Save results
    output_path = Path("exploratory_results.json")
    output_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
