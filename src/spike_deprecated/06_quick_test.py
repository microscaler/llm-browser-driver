#!/usr/bin/env python3
"""Quick test: Playwright + LLM in one script."""

import asyncio
import json
from pathlib import Path
from openai import AsyncOpenAI
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:7174"
LLM_API_URL = "http://192.168.1.104:8000/v1"
LLM_MODEL = "qwen3"

async def main():
    client = AsyncOpenAI(
        base_url=LLM_API_URL,
        api_key="placeholder",
        timeout=60,
    )
    
    print("Starting browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Navigating to homepage...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_load_state("networkidle", timeout=10000)
        await asyncio.sleep(1)
        
        title = await page.title()
        print(f"Page title: {title}")
        
        input_count = len(await page.locator("input:not([type=hidden]):not([type=submit]):not([type=button])").all())
        print(f"Inputs: {input_count}")
        
        snapshot = {
            "title": title,
            "url": page.url,
            "forms": {
                "input_count": input_count,
                "textarea_count": len(await page.locator("textarea").all()),
                "button_count": len(await page.locator("button, [role=button]").all()),
                "dropdown_count": len(await page.locator("select, [role=combobox], [role=listbox]").all()),
                "disabled_inputs": len(await page.locator('input:disabled, textarea:disabled, button:disabled').all()),
            },
        }
        print(f"Snapshot: {json.dumps(snapshot, indent=2)}")
        
        print("\nCalling LLM...")
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a QA analyst."},
                {"role": "user", "content": f"Analyze: {json.dumps(snapshot)}"},
            ],
            max_tokens=512,
            temperature=0.3,
            timeout=60,
        )
        llm_text = response.choices[0].message.content
        print(f"\nLLM response ({len(llm_text)} chars):\n{llm_text}")
        
        await browser.close()
    
    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
