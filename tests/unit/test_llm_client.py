"""Tests for llm_client.py — LLM abstraction and JSON parsing.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from llm_browser_driver.llm_client import (
    LLMClient,
    parse_action_from_response,
)


# ---------------------------------------------------------------------------
# parse_action_from_response tests
# ---------------------------------------------------------------------------

class TestParseActionFromResponse:
    """Test the JSON parser that handles Qwen3 reasoning text + trailing JSON."""

    def test_pure_json(self):
        """Pure JSON response parses correctly."""
        text = '{"action": "click", "element": "Sign In"}'
        result = parse_action_from_response(text)
        assert result == {"action": "click", "element": "Sign In"}

    def test_json_with_leading_text(self):
        """Qwen3 reasoning text before JSON."""
        text = 'Let me think...\nHere is the action:\n{"action": "fill", "field": "email", "value": "test@example.com"}'
        result = parse_action_from_response(text)
        assert result["action"] == "fill"
        assert result["field"] == "email"

    def test_json_with_markdown_code_block(self):
        """JSON inside markdown code blocks."""
        text = '{"action": "navigate", "url": "http://example.com"}\n```json\nnot-json\n```'
        result = parse_action_from_response(text)
        assert result["action"] == "navigate"
        assert result["url"] == "http://example.com"

    def test_finds_last_json_from_end(self):
        """Scans from end, finds the last valid JSON object."""
        text = "First attempt: {'action': 'click', 'element': 'wrong'}\nSecond attempt: {'action': 'done', 'summary': 'Testing complete'}"
        result = parse_action_from_response(text)
        assert result["action"] == "done"
        assert "Testing complete" in result["summary"]

    def test_empty_text(self):
        """Empty text returns done with empty summary."""
        result = parse_action_from_response("")
        assert result == {"action": "done", "summary": "Empty response"}

    def test_unrecognized_action_returns_done(self):
        """Unrecognized action text returns done."""
        result = parse_action_from_response("The user needs to dance")
        assert result["action"] == "done"

    def test_nested_json(self):
        """Nested JSON objects parse correctly."""
        text = json.dumps({
            "action": "evaluate",
            "script": "return document.querySelectorAll('input').length",
        })
        result = parse_action_from_response(text)
        assert result["action"] == "evaluate"
        assert result["script"] == "return document.querySelectorAll('input').length"

    def test_json_with_unicode(self):
        """JSON containing unicode characters."""
        text = '{"action": "fill", "field": "name", "value": "日本語テスト"}'
        result = parse_action_from_response(text)
        assert result["value"] == "日本語テスト"


# ---------------------------------------------------------------------------
# LLMClient tests
# ---------------------------------------------------------------------------

class TestLLMClient:
    @pytest.fixture
    def config(self, minimal_config):
        return minimal_config

    def test_init_creates_openai_client(self, config):
        """LLMClient initializes an OpenAI client with correct settings."""
        with patch("llm_browser_driver.llm_client.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client

            client = LLMClient(config)

            MockOpenAI.assert_called_once_with(
                base_url=config.llm.api_url,
                api_key="placeholder",
                timeout=config.llm.timeout,
            )
            assert client._client == mock_client

    def test_model_property(self, config):
        with patch("llm_browser_driver.llm_client.OpenAI"):
            client = LLMClient(config)
            assert client.model == config.llm.model

    def test_streaming_property(self, config):
        with patch("llm_browser_driver.llm_client.OpenAI"):
            client = LLMClient(config)
            assert client.streaming is False

    def test_chat_calls_create(self, config):
        """chat() calls OpenAI with correct parameters."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"

        with patch("llm_browser_driver.llm_client.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            client = LLMClient(config)
            result = client.chat(
                system_prompt="You are a tester.",
                user_prompt="Click the login button.",
            )

            assert result == "Test response"
            mock_client.chat.completions.create.assert_called_once_with(
                model=config.llm.model,
                messages=[
                    {"role": "system", "content": "You are a tester."},
                    {"role": "user", "content": "Click the login button."},
                ],
                max_tokens=config.llm.max_tokens,
                temperature=config.llm.temperature,
                stream=False,
            )

    def test_chat_handles_empty_content(self, config):
        """chat() returns empty string when content is None."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        with patch("llm_browser_driver.llm_client.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            client = LLMClient(config)
            result = client.chat("system", "user")
            assert result == ""
