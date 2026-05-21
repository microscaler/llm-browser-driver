"""Configuration management for LLM Browser Driver.

Configuration is loaded in priority order:
1. Constructor args (highest priority)
2. Environment variables (LLM_BROWSER_DRIVER_*)
3. Config file (YAML)
4. Defaults (lowest priority)

Example environment variables:

    export LLM_BROWSER_DRIVER__LLM_API_URL=http://localhost:8000/v1
    export LLM_BROWSER_DRIVER__LLM_MODEL=qwen3
    export LLM_BROWSER_DRIVER__MAX_ITERATIONS=30
    export LLM_BROWSER_DRIVER__HEADLESS=true
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    """LLM endpoint configuration."""

    api_url: str = "http://localhost:8000/v1"
    model: str = "qwen3"
    max_tokens: int = 2048
    temperature: float = 0.3
    timeout: float = 300.0
    streaming: bool = False

    def __post_init__(self) -> None:
        """Enforce Qwen3 streaming constraint from spike findings."""
        if self.streaming and "qwen" in self.model.lower():
            self.streaming = False
            print(
                f"[llm-browser-driver] WARNING: model '{self.model}' requires "
                "streaming=false (Qwen3 on vLLM puts all output in reasoning field). "
                "Setting streaming=false automatically."
            )


@dataclass
class AgentConfig:
    """Agent loop configuration."""

    max_iterations: int = 30
    max_actions_per_step: int = 5
    max_failures: int = 3


@dataclass
class BrowserConfig:
    """Browser configuration."""

    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout: int = 30000


@dataclass
class AppConfig:
    """Top-level application configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    url: str | None = None
    config_file: str | Path | None = None


# ---------------------------------------------------------------------------
# Environment variable loading
# ---------------------------------------------------------------------------

def _load_from_env() -> dict[str, Any]:
    """Load configuration from environment variables.

    Convention: LLM_BROWSER_DRIVER__<SECTION>_<KEY> → nested config.
    Section is the first word after the prefix; key is the rest.

        LLM_BROWSER_DRIVER__LLM_API_URL       → llm.api_url
        LLM_BROWSER_DRIVER__LLM_MODEL         → llm.model
        LLM_BROWSER_DRIVER__AGENT_MAX_ITERATIONS → agent.max_iterations
        LLM_BROWSER_DRIVER__BROWSER_HEADLESS  → browser.headless
        LLM_BROWSER_DRIVER__URL               → top-level url

    """
    prefix = "LLM_BROWSER_DRIVER__"
    result: dict[str, Any] = {}

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        # Strip prefix and determine section vs key
        remainder = key[len(prefix):].lower()
        parts = remainder.split("_", 1)  # split on FIRST underscore only

        if len(parts) == 1:
            # Top-level key, e.g. "URL"
            result[parts[0]] = value
        else:
            # Section + key, e.g. "llm_api_url" → section="llm", key="api_url"
            section, key = parts
            if section not in result:
                result[section] = {}
            result[section][key] = value

    return result


# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------

def _load_from_yaml(path: Path) -> dict[str, Any] | None:
    """Load configuration from a YAML file. Returns None if file not found."""
    import yaml

    if not path.is_file():
        return None

    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Merge helper
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge `override` into `base`. Mutates and returns `base`."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(**overrides: Any) -> AppConfig:
    """Load and merge configuration from all sources.

    Priority order (highest to lowest):
    1. Keyword arguments passed to this function
    2. Environment variables (LLM_BROWSER_DRIVER_*)
    3. Config file (YAML) — path from `config_file` override or default location
    4. Hardcoded defaults (in dataclass definitions)

    Args:
        **overrides: Top-level config overrides (e.g. url="http://localhost:3000").
                     Nested overrides use dict keys: llm={"model": "claude"}.

    Returns:
        Fully resolved AppConfig.

    Example:
        >>> config = load_config(url="http://localhost:3000",
        ...                       llm={"model": "gpt-4"})
    """
    # Start with defaults
    env_cfg = _load_from_env()

    # Determine config file path
    config_file: str | Path | None = overrides.pop("config_file", None)
    if config_file is None:
        default_paths = [
            Path.home() / ".llm-browser-driver" / "config.yaml",
            Path("config.yaml"),
        ]
        for p in default_paths:
            if p.is_file():
                config_file = p
                break

    # Load from config file if found
    file_cfg: dict[str, Any] = {}
    if config_file is not None:
        file_cfg = _load_from_yaml(Path(config_file)) or {}

    # Deep merge: defaults < env < file < overrides
    merged: dict[str, Any] = {}
    _deep_merge(merged, env_cfg)
    _deep_merge(merged, file_cfg)
    _deep_merge(merged, overrides)

    # Build dataclass tree
    config = AppConfig()

    # Apply top-level overrides
    if "url" in merged:
        config.url = str(merged["url"])
    if "config_file" in merged:
        config.config_file = merged["config_file"]

    # Apply LLM sub-config
    if "llm" in merged:
        llm_data = merged["llm"]
        config.llm = LLMConfig(**{k: v for k, v in llm_data.items()})

    # Apply Agent sub-config
    if "agent" in merged:
        agent_data = merged["agent"]
        config.agent = AgentConfig(**{k: v for k, v in agent_data.items()})

    # Apply Browser sub-config
    if "browser" in merged:
        browser_data = merged["browser"]
        config.browser = BrowserConfig(**{k: v for k, v in browser_data.items()})

    return config


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def model_presets() -> dict[str, dict[str, Any]]:
    """Return preset configurations for common LLM models.

    These are convenience presets users can select via `--model claude`, etc.
    The actual model name and endpoint still need to be configured.
    """
    return {
        "qwen3": {
            "model": "qwen3",
            "max_tokens": 2048,
            "temperature": 0.3,
            "streaming": False,
        },
        "claude": {
            "model": "claude-sonnet-4",
            "max_tokens": 4096,
            "temperature": 0.3,
            "streaming": False,
        },
        "gpt": {
            "model": "gpt-4o",
            "max_tokens": 4096,
            "temperature": 0.3,
            "streaming": False,
        },
    }
