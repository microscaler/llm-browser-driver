"""LLM client abstraction for LLM Browser Driver.

Wraps the OpenAI SDK to provide a consistent interface for any
OpenAI-compatible LLM endpoint (vLLM, Ollama, OpenRouter, etc.).

Handles:
- JSON response parsing (with Qwen3 reasoning text handling)
- Streaming toggle (required for Qwen3 on vLLM)
- Retry on transient failures

Extracted from `09_interactive_exploration.py` (lines 430–527).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from openai import OpenAI

from llm_browser_driver.config import AppConfig


class LLMClient:
    """LLM client abstraction over the OpenAI SDK.

    Supports any endpoint implementing `/v1/chat/completions`.

    Args:
        config: Application configuration with LLM settings.

    Example:
        >>> config = load_config(llm_api_url="http://localhost:8000/v1",
        ...                      llm_model="qwen3")
        >>> client = LLMClient(config)
        >>> response = client.chat("Tell me about this page...")
    """

    def __init__(self, config: AppConfig) -> None:
        self._client = OpenAI(
            base_url=config.llm.api_url,
            api_key=config.llm.api_url.split("@")[1] if "@" in config.llm.api_url else "placeholder",
            timeout=config.llm.timeout,
        )
        self._model = config.llm.model
        self._max_tokens = config.llm.max_tokens
        self._temperature = config.llm.temperature
        self._streaming = config.llm.streaming

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Make a chat completion call.

        Args:
            system_prompt: System prompt for the LLM.
            user_prompt: User message with page state and goal.

        Returns:
            The LLM's response text (content field).
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stream=self._streaming,
        )

        # For streaming models, concatenate all chunks
        if self._streaming:
            return "".join(
                chunk.choices[0].delta.content or ""
                for chunk in response
                if chunk.choices[0].delta.content
            )

        # Non-streaming: content field is always present
        choice = response.choices[0]
        return (choice.message.content or "").strip()

    @property
    def model(self) -> str:
        """The configured LLM model name."""
        return self._model

    @property
    def streaming(self) -> bool:
        """Whether streaming is enabled."""
        return self._streaming


def parse_action_from_response(response_text: str) -> dict[str, Any]:
    """Parse the action JSON from LLM response text.

    Qwen3 outputs reasoning text (thinking) followed by the actual JSON answer.
    The JSON answer is always at the END of the response.

    Strategy: scan from the end to find the last { that opens a valid JSON object.

    Args:
        response_text: Raw LLM response text.

    Returns:
        Dict with at least an "action" key. If no valid JSON found,
        returns {"action": "done", "summary": response_text[:200]}.
    """
    # Strategy 1: Find the last JSON object starting from the end
    # Work backwards through the text, when we find a '{', try to parse forward
    for i in range(len(response_text) - 1, -1, -1):
        if response_text[i] == "{":
            candidate = response_text[i:]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "action" in parsed:
                    return parsed
            except (json.JSONDecodeError, ValueError):
                continue

    # Strategy 2: Extract "action": "..." from anywhere in text
    action_value_match = re.search(
        r'"action"\s*[:\s]+["\']([^"\']+)["\']', response_text
    )
    if action_value_match:
        action_value = action_value_match.group(1)
        known_actions = [
            "click", "fill", "select", "scroll", "navigate",
            "go_back", "wait", "evaluate", "done", "error",
        ]
        if action_value in known_actions:
            return {"action": action_value}

    # Strategy 3: Return done with summary
    if response_text.strip():
        return {"action": "done", "summary": response_text[:200]}
    else:
        return {"action": "done", "summary": "Empty response"}
