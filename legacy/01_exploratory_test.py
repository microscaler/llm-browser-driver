#!/usr/bin/env python3
"""
Spike: Use browser-use to explore the Hauliage frontend and identify issues
that deterministic BDD tests might miss.

This is exploratory testing - the agent navigates the app like a real user would,
reporting issues in structured JSON format.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:7174")
LLM_API_URL = os.getenv("LLM_API_URL", "http://192.168.1.104:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3")

async def run_exploration(tasks: list[str], frontend_url: str, api_url: str, model: str) -> dict:
    """
    Run browser-use exploratory tests and return structured results.
    """
    from browser_use import Agent, Browser, SystemPrompt
    from browser_use import Tools
    from openai import AsyncOpenAI
    
    # Initialize OpenAI-compatible client pointing to their LLM server
    client = AsyncOpenAI(
        base_url=api_url,
        api_key="placeholder"  # Their server doesn't seem to require auth
    )
    
    async with Browser() as browser:
        results = []
        
        for i, task in enumerate(tasks):
            print(f"\n{'='*80}")
            print(f"EXPLORATION TASK {i+1}/{len(tasks)}")
            print(f"{'='*80}")
            print(f"Task: {task}\n")
            
            # Configure agent
            agent = Agent(
                task=task,
                llm=client,
                model=model,
                browser=browser,
                max_actions_per_step=5,
                max_failures=3,
                generate_gif=False,
                # Use a concise system prompt
                system_prompt=SystemPrompt(
                    web_agent_task="Explore and report on the current page state",
                ),
            )
            
            # Run the agent
            try:
                result = await agent.run()
                
                # Extract structured findings
                findings = {
                    "task": task,
                    "success": result.success,
                    "final_state": result.current_state,
                    "metrics": result.metrics,
                    "last_error": result.last_error,
                }
                
                results.append(findings)
                
            except Exception as e:
                results.append({
                    "task": task,
                    "error": str(e),
                    "success": False,
                })
        
        return {"results": results}

async def main():
    """
    Run a series of exploratory tests against the Hauliage frontend.
    """
    # Check if frontend is accessible
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(FRONTEND_URL, timeout=5) as resp:
                if resp.status != 200:
                    print(f"Frontend not accessible at {FRONTEND_URL} (status: {resp.status})")
                    print("Skipping exploratory tests.")
                    return
        except Exception as e:
            print(f"Cannot reach frontend at {FRONTEND_URL}: {e}")
            print("Skipping exploratory tests.")
            return
    
    print(f"Frontend accessible at {FRONTEND_URL}")
    print(f"LLM API: {LLM_API_URL}")
    print(f"Model: {LLM_MODEL}")
    
    # Define exploratory tasks
    tasks = [
        "Navigate to the homepage and report what you see. Is the 'Post a Job' button visible and clickable?",
        "Check if the app loads without JavaScript errors. Report any console errors or warnings.",
        "Try to find the pickup country dropdown. Is it disabled or in a loading state?",
        "Navigate to the job details page (if there's a link to it). Does it render correctly or show errors?",
    ]
    
    results = await run_exploration(tasks, FRONTEND_URL, LLM_API_URL, LLM_MODEL)
    
    # Save results
    output_path = Path("exploratory_results.json")
    output_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {output_path}")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())
