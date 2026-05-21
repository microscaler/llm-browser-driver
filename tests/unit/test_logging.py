"""Tests for structured JSON logging.

Covers:
- StructuredFormatter JSON output
- setup_logging configuration
- LogTimer timing
- get_logger returns consistent instances
"""

from __future__ import annotations

import json
import logging
import time
import pytest

from llm_browser_driver.logging import (
    StructuredFormatter,
    setup_logging,
    get_logger,
    LogTimer,
    _LOGGERS,
)


# ---------------------------------------------------------------------------
# StructuredFormatter tests
# ---------------------------------------------------------------------------


class TestStructuredFormatter:
    def test_basic_json_output(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="step_executed step=5 action=click success=true",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["event"] == "step_executed"
        assert data["level"] == "INFO"
        assert data["step"] == 5
        assert data["action"] == "click"
        assert data["success"] == "true"
        assert "ts" in data
        assert "logger" in data

    def test_numeric_values_parsed(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="action_executed step=42 duration_ms=123",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["step"] == 42
        assert data["duration_ms"] == 123

    def test_extra_fields_included(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="action_failed target=#btn",
            args=None,
            exc_info=None,
        )
        record._extra = {"error": "Element not found"}
        output = formatter.format(record)
        data = json.loads(output)

        assert data["error"] == "Element not found"

    def test_empty_message(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["event"] == ""

    def test_message_without_equals(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="connection_timeout",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["event"] == "connection_timeout"
        assert data["level"] == "ERROR"


# ---------------------------------------------------------------------------
# get_logger tests
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_consistent_instance(self):
        logger1 = get_logger("test")
        logger2 = get_logger("test")
        assert logger1 is logger2

    def test_returns_different_instances_for_different_names(self):
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        assert logger1 is not logger2

    def test_logger_name_prefixed(self):
        logger = get_logger("agent")
        assert logger.name == "llm_browser_driver.agent"

    def test_logger_name_prefixed_submodule(self):
        logger = get_logger("agent.selector")
        assert logger.name == "llm_browser_driver.agent.selector"


# ---------------------------------------------------------------------------
# setup_logging tests
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_sets_level(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logging(level="DEBUG", output="file", file_path=str(log_file))

        logger = get_logger("test_level")
        logger.setLevel(logging.DEBUG)
        logger.debug("debug message")

        assert log_file.read_text() != ""

    def test_configures_root_logger(self):
        setup_logging(level="DEBUG")
        root = logging.getLogger("llm_browser_driver")
        assert root.level == logging.DEBUG

    def test_reentrant_safe(self):
        setup_logging(level="DEBUG")
        setup_logging(level="INFO")
        root = logging.getLogger("llm_browser_driver")
        assert root.level == logging.INFO

    def test_standalone(self):
        """Call without any parameters to verify defaults work."""
        setup_logging()
        root = logging.getLogger("llm_browser_driver")
        assert root.level == logging.INFO


# ---------------------------------------------------------------------------
# LogTimer tests
# ---------------------------------------------------------------------------


class TestLogTimer:
    def test_logs_duration(self, caplog):
        logger = get_logger("test_timer")
        logger.setLevel(logging.DEBUG)
        # Add a basic handler to capture output
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

        with LogTimer(logger, "test_step"):
            time.sleep(0.01)

        assert any("duration_ms" in record.message for record in caplog.records)
        assert any("test_step" in record.message for record in caplog.records)
