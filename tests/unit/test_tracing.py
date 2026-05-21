"""Tests for OpenTelemetry tracing integration.

Covers:
- TracingConfig initialization
- No-op behavior when OTel is not installed
- Tracer initialization after setup_tracing
- Span helpers (step, state, llm, action, screenshot)
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
import sys

import pytest

from llm_browser_driver.tracing import (
    TracingConfig,
    setup_tracing,
    _OTEL_AVAILABLE,
    _get_tracer,
    span_step,
    span_state_extraction,
    span_llm_call,
    span_action,
    span_screenshot,
)


# ---------------------------------------------------------------------------
# TracingConfig tests
# ---------------------------------------------------------------------------


class TestTracingConfig:
    def test_default_values(self):
        config = TracingConfig()
        assert config.service_name == "llm-browser-driver"
        assert config.endpoint is None
        assert config.enabled is True

    def test_custom_values(self):
        config = TracingConfig(
            service_name="my-app",
            endpoint="http://localhost:4318",
            enabled=False,
        )
        assert config.service_name == "my-app"
        assert config.endpoint == "http://localhost:4318"
        assert config.enabled is False

    def test_config_is_disabled(self):
        config = TracingConfig(enabled=False)
        assert not config.enabled


# ---------------------------------------------------------------------------
# setup_tracing tests
# ---------------------------------------------------------------------------


class TestSetupTracing:
    def test_noop_when_otel_not_available(self):
        if not _OTEL_AVAILABLE:
            setup_tracing()
            # Should not raise — just logs a warning

    def test_skipped_when_disabled(self):
        setup_tracing(TracingConfig(enabled=False))
        # Should not call any OTel APIs — just returns early

    @patch("llm_browser_driver.tracing.logger")
    def test_logs_when_otel_unavailable(self, mock_logger):
        if _OTEL_AVAILABLE:
            pytest.skip("OTel is installed, can't test unavailable path")
        setup_tracing()
        mock_logger.info.assert_called()

    def test_get_tracer_returns_span_methods(self):
        tracer = _get_tracer()
        assert hasattr(tracer, "start_span")
        assert callable(tracer.start_span)
        assert hasattr(tracer, "start_as_current_span")

    def test_get_tracer_returns_same_instance(self):
        t1 = _get_tracer()
        t2 = _get_tracer()
        assert t1 is t2


# ---------------------------------------------------------------------------
# _get_tracer tests
# ---------------------------------------------------------------------------


class TestGetTracer:
    def test_returns_tracer(self):
        tracer = _get_tracer()
        # Should have start_span method
        assert hasattr(tracer, "start_span")

    def test_returns_same_instance(self):
        tracer1 = _get_tracer()
        tracer2 = _get_tracer()
        assert tracer1 is tracer2

    def test_start_span_exists(self):
        tracer = _get_tracer()
        assert callable(tracer.start_span)

    def test_start_as_current_span_exists(self):
        tracer = _get_tracer()
        assert hasattr(tracer, "start_as_current_span")


# ---------------------------------------------------------------------------
# Span helper tests
# ---------------------------------------------------------------------------


class TestSpanHelpers:
    def test_span_step(self):
        with span_step(5, total=30):
            pass  # Should not raise

    def test_span_step_without_total(self):
        with span_step(1):
            pass  # Should not raise

    def test_span_state_extraction(self):
        with span_state_extraction(12345):
            pass  # Should not raise

    def test_span_llm_call(self):
        with span_llm_call("qwen3", tokens=1024):
            pass  # Should not raise

    def test_span_llm_call_no_tokens(self):
        with span_llm_call("gpt-4o"):
            pass  # Should not raise

    def test_span_action(self):
        with span_action("click", "#login-btn"):
            pass  # Should not raise

    def test_span_screenshot(self):
        with span_screenshot("screenshots/step-5.png"):
            pass  # Should not raise
