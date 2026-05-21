"""Structured JSON logging for LLM Browser Driver.

Provides structured JSON logging that integrates with log aggregation
systems (Datadog, ELK, CloudWatch) for debugging, auditing, and
performance profiling.

Usage::

    from llm_browser_driver.logging import setup_logging, log_action

    # Enable in your application
    setup_logging(level="DEBUG", output="stdout")

    # Or use the contextual loggers
    from llm_browser_driver.logging import get_logger

    logger = get_logger("llm_browser_driver.agent")
    logger.info("step_executed", step=5, action="click", success=True)


Each log entry is a JSON object with consistent fields::

    {
        "ts": "2026-05-21T10:00:00.123Z",
        "level": "INFO",
        "event": "action_executed",
        "step": 5,
        "action": "click",
        "target": "#login-btn",
        "success": true,
        "duration_ms": 423,
        "url_after": "http://localhost:3000/dashboard"
    }


Configuration via environment variables:

    LLM_BROWSER_DRIVER_LOG_LEVEL=debug
    LLM_BROWSER_DRIVER_LOG_FORMAT=json
    LLM_BROWSER_DRIVER_LOG_FILE=logs/llm-browser-driver.log
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Contextual loggers
# ---------------------------------------------------------------------------

# Pre-defined loggers for each module
_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    """Get a structured logger for the given module name.

    Returns a logger configured for JSON output if structured logging
    is enabled, otherwise returns a standard logger.
    """
    if name not in _LOGGERS:
        _LOGGERS[name] = logging.getLogger(f"llm_browser_driver.{name}")
    return _LOGGERS[name]


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Each log record becomes a JSON object with consistent fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }

        # Extract the event name from the message
        # Format: "event_name key=value key2=value2"
        parts = record.getMessage().split(" ", 1)
        entry["event"] = parts[0]

        # Extract key=value pairs from the message
        if len(parts) > 1:
            for part in parts[1].split():
                if "=" in part:
                    k, v = part.split("=", 1)
                    # Try to parse numeric values
                    if v.isdigit():
                        entry[k] = int(v)
                    else:
                        entry[k] = v

        # Include any additional fields stored on the record
        for attr in getattr(record, "_extra", {}):
            entry[attr] = record._extra.get(attr, "")

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------


def setup_logging(
    level: str = "INFO",
    output: str = "stdout",
    file_path: str | None = None,
) -> None:
    """Configure structured JSON logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        output: Where to write logs. "stdout", "stderr", or "file".
        file_path: When output="file", the log file path.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root = logging.getLogger("llm_browser_driver")
    root.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root.handlers.clear()

    # Configure formatters
    json_formatter = StructuredFormatter()
    text_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Configure output handlers
    if output in ("stdout", "all"):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(json_formatter)
        root.addHandler(handler)

    if output in ("stderr", "all"):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(json_formatter)
        root.addHandler(handler)

    if output == "file" and file_path:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(file_path, mode="a")
        handler.setFormatter(json_formatter)
        root.addHandler(handler)

    if output == "text":
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(text_formatter)
        root.addHandler(handler)


# ---------------------------------------------------------------------------
# Timing Decorator
# ---------------------------------------------------------------------------


@dataclass
class LogTimer:
    """Context manager for logging function execution time."""

    logger: logging.Logger
    event: str
    extra: dict[str, Any] = field(default_factory=dict)

    def __enter__(self) -> "LogTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        duration_ms = (time.monotonic() - self._start) * 1000
        self.logger.info(
            f"{self.event} duration_ms={duration_ms:.0f}",
            **self.extra,
        )
