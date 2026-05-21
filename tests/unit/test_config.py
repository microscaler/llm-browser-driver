"""Tests for config.py — configuration management.
"""

from __future__ import annotations

import os

import pytest

from llm_browser_driver.config import (
    AppConfig,
    BrowserConfig,
    LLMConfig,
    AgentConfig,
    _load_from_env,
    _deep_merge,
    load_config,
    model_presets,
)


# ---------------------------------------------------------------------------
# LLMConfig tests
# ---------------------------------------------------------------------------

class TestLLMConfig:
    def test_default_values(self):
        config = LLMConfig()
        assert config.api_url == "http://localhost:8000/v1"
        assert config.model == "qwen3"
        assert config.max_tokens == 2048
        assert config.temperature == 0.3
        assert config.timeout == 300.0
        assert config.streaming is False

    def test_custom_values(self):
        config = LLMConfig(
            api_url="http://custom:9000/v1",
            model="gpt-4",
            max_tokens=4096,
            temperature=0.7,
            timeout=60,
        )
        assert config.api_url == "http://custom:9000/v1"
        assert config.model == "gpt-4"
        assert config.max_tokens == 4096
        assert config.temperature == 0.7
        assert config.timeout == 60

    def test_qwen3_streaming_forced_false(self):
        """Qwen3 must never stream — spike finding #1."""
        config = LLMConfig(model="qwen3", streaming=True)
        assert config.streaming is False
        assert config.model == "qwen3"

    def test_qwen3_family_streaming_forced_false(self):
        """Any model name containing 'qwen' gets streaming auto-disabled."""
        for model in ["qwen", "qwen2", "qwen3-72b"]:
            config = LLMConfig(model=model, streaming=True)
            assert config.streaming is False, f"qwen3 streaming should be forced off for {model}"


# ---------------------------------------------------------------------------
# AgentConfig / BrowserConfig tests
# ---------------------------------------------------------------------------

class TestAgentConfig:
    def test_defaults(self):
        config = AgentConfig()
        assert config.max_iterations == 30
        assert config.max_actions_per_step == 5
        assert config.max_failures == 3


class TestBrowserConfig:
    def test_defaults(self):
        config = BrowserConfig()
        assert config.headless is True
        assert config.viewport_width == 1280
        assert config.viewport_height == 720
        assert config.timeout == 30000


# ---------------------------------------------------------------------------
# _deep_merge tests
# ---------------------------------------------------------------------------

class TestDeepMerge:
    def test_merge_overwrites_simple(self):
        base = {"a": 1, "b": 2}
        override = {"a": 10}
        result = _deep_merge(base, override)
        assert result == {"a": 10, "b": 2}

    def test_merge_nested(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"x": 10}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 10, "y": 2}, "b": 3}

    def test_merge_adds_missing(self):
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_merge_deeply_nested(self):
        base = {"a": {"b": {"c": 1}}}
        override = {"a": {"b": {"d": 2}}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 2}}}


# ---------------------------------------------------------------------------
# _load_from_env tests
# ---------------------------------------------------------------------------

class TestLoadFromEnv:
    @pytest.fixture(autouse=True)
    def clean_env(self):
        """Remove our env vars before and after each test."""
        for key in list(os.environ.keys()):
            if key.startswith("LLM_BROWSER_DRIVER"):
                del os.environ[key]
        yield
        for key in list(os.environ.keys()):
            if key.startswith("LLM_BROWSER_DRIVER"):
                del os.environ[key]

    def test_simple_env_var(self):
        os.environ["LLM_BROWSER_DRIVER__LLM_API_URL"] = "http://test:9999/v1"
        result = _load_from_env()
        assert result["llm"]["api_url"] == "http://test:9999/v1"

    def test_multiple_env_vars(self):
        os.environ["LLM_BROWSER_DRIVER__LLM_MODEL"] = "gpt-4"
        os.environ["LLM_BROWSER_DRIVER__MAX_ITERATIONS"] = "50"
        os.environ["LLM_BROWSER_DRIVER__HEADLESS"] = "false"
        result = _load_from_env()
        assert result["llm"]["model"] == "gpt-4"
        assert result["agent"]["max_iterations"] == "50"  # stays string
        assert result["browser"]["headless"] == "false"

    def test_no_matching_vars(self):
        result = _load_from_env()
        assert result == {}


# ---------------------------------------------------------------------------
# load_config tests
# ---------------------------------------------------------------------------

class TestLoadConfig:
    @pytest.fixture(autouse=True)
    def clean_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("LLM_BROWSER_DRIVER"):
                del os.environ[key]
        yield
        for key in list(os.environ.keys()):
            if key.startswith("LLM_BROWSER_DRIVER"):
                del os.environ[key]

    def test_defaults_only(self):
        config = load_config()
        assert config.url is None
        assert config.llm.model == "qwen3"
        assert config.agent.max_iterations == 30
        assert config.browser.headless is True

    def test_override_via_kwargs(self):
        config = load_config(
            url="http://myapp.com",
            llm={"model": "gpt-4"},
        )
        assert config.url == "http://myapp.com"
        assert config.llm.model == "gpt-4"

    def test_env_takes_precedence_over_defaults(self):
        os.environ["LLM_BROWSER_DRIVER__LLM_MODEL"] = "from-env"
        config = load_config()
        assert config.llm.model == "from-env"

    def test_kwargs_takes_precedence_over_env(self):
        os.environ["LLM_BROWSER_DRIVER__LLM_MODEL"] = "from-env"
        config = load_config(llm={"model": "from-kwarg"})
        assert config.llm.model == "from-kwarg"

    def test_qwen3_in_kwargs_forces_streaming_off(self):
        config = load_config(llm={"model": "qwen3", "streaming": True})
        assert config.llm.streaming is False


# ---------------------------------------------------------------------------
# model_presets tests
# ---------------------------------------------------------------------------

class TestModelPresets:
    def test_returns_dict(self):
        presets = model_presets()
        assert isinstance(presets, dict)

    def test_has_expected_models(self):
        presets = model_presets()
        assert "qwen3" in presets
        assert "claude" in presets
        assert "gpt" in presets

    def test_qwen3_no_streaming(self):
        presets = model_presets()
        assert presets["qwen3"]["streaming"] is False

    def test_claude_no_streaming(self):
        presets = model_presets()
        assert presets["claude"]["streaming"] is False
