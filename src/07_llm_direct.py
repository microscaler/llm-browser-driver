#!/usr/bin/env python3
"""Test LLM call with error handling."""

import asyncio
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI(
        base_url="http://192.168.1.104:8000/v1",
        api_key="placeholder",
        timeout=60,
    )
    
    print("Calling LLM...")
    try:
        response = await client.chat.completions.create(
            model="qwen3",
            messages=[
                {"role": "system", "content": "You are a QA analyst."},
                {"role": "user", "content": "Say 'Hello World' in 5 words or less."},
            ],
            max_tokens=512,
            temperature=0.3,
            timeout=60,
        )
        print(f"Response: {response}")
        print(f"Choices: {response.choices}")
        print(f"Message: {response.choices[0].message}")
        print(f"Content: {response.choices[0].message.content}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
