"""Optional OpenTelemetry tracing integration.

Integrates with OpenTelemetry for distributed tracing. Provides spans for:
- LLM calls (to measure latency, token usage)
- State extraction (to measure DOM parsing performance)
- Action execution (to track browser automation timing)
- Full loop steps (end-to-end per iteration)

This is an optional dependency. Install with:
    pip install llm-browser-driver[tracing]

Usage::

    from llm_browser_driver.tracing import setup_tracing

    # Configure before running the driver
    setup_tracing(
        service_name="llm-browser-driver",
        endpoint="http://otel-collector:4318",  # OTLP HTTP
    )

    driver = BrowserDriver(...)
    result = driver.explore(url="...", goal="...")


If OpenTelemetry is not installed, all tracing functions become no-ops.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

logger = logging.getLogger(__name__)

# Optional OTel imports — fall back gracefully
try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class _NoOpSpan:
    """No-op span when OTel is not installed."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value):
        pass

    def set_status(self, status):
        pass

    def record_exception(self, exception, **kwargs):
        pass


class _NoOpTracer:
    """No-op tracer when OTel is not installed."""

    def start_span(self, name, **kwargs):
        return _NoOpSpan()

    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        yield _NoOpSpan()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TracingConfig:
    """Configuration for OpenTelemetry tracing."""

    def __init__(
        self,
        service_name: str = "llm-browser-driver",
        endpoint: str | None = None,
        enabled: bool = True,
    ):
        self.service_name = service_name
        self.endpoint = endpoint
        self.enabled = enabled


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup_tracing(config: TracingConfig | None = None) -> None:
    """Configure OpenTelemetry tracing.

    This must be called before any BrowserDriver instances are created
    to ensure spans are properly attributed.

    Args:
        config: Tracing configuration. If None, uses defaults.
    """
    if not _OTEL_AVAILABLE:
        logger.info(
            "OpenTelemetry not available. Install with: "
            "pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp-proto-http"
        )
        return

    if config is None:
        config = TracingConfig()

    if not config.enabled:
        return

    from opentelemetry import trace as trace_api
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    resource = Resource.create({"service.name": config.service_name})
    provider = TracerProvider(resource=resource)

    if config.endpoint:
        exporter = OTLPSpanExporter(endpoint=config.endpoint)
        provider.add_span_exporter(exporter)

    trace_api.set_tracer_provider(provider)
    logger.info(f"Tracing enabled for service '{config.service_name}'")


# ---------------------------------------------------------------------------
# Tracer singleton
# ---------------------------------------------------------------------------


_tracer: Tracer = _NoOpTracer()  # type: ignore


def _get_tracer() -> "Tracer":
    """Get the current tracer, initializing if needed."""
    global _tracer
    if _OTEL_AVAILABLE and isinstance(_tracer, _NoOpTracer):
        from opentelemetry import trace
        _tracer = trace.get_tracer("llm-browser-driver")
    return _tracer  # type: ignore


# ---------------------------------------------------------------------------
# Span helpers
# ---------------------------------------------------------------------------


@contextmanager
def span_step(step: int, total: int | None = None):
    """Span for a full loop iteration."""
    with _get_tracer().start_span("llm_browser_driver.step") as span:
        span.set_attribute("step", step)
        if total:
            span.set_attribute("step.total", total)
        yield span


@contextmanager
def span_state_extraction(state_size: int):
    """Span for page state extraction (DOM/a11y/HTML)."""
    with _get_tracer().start_span("llm_browser_driver.state_extract") as span:
        span.set_attribute("state_size", state_size)
        yield span


@contextmanager
def span_llm_call(model: str, tokens: int | None = None):
    """Span for an LLM API call."""
    with _get_tracer().start_span("llm_browser_driver.llm_call") as span:
        span.set_attribute("llm.model", model)
        if tokens:
            span.set_attribute("llm.tokens", tokens)
        yield span


@contextmanager
def span_action(action: str, target: str):
    """Span for a Playwright action execution."""
    with _get_tracer().start_span("llm_browser_driver.action") as span:
        span.set_attribute("action.type", action)
        span.set_attribute("action.target", target)
        yield span


@contextmanager
def span_screenshot(path: str):
    """Span for screenshot capture."""
    with _get_tracer().start_span("llm_browser_driver.screenshot") as span:
        span.set_attribute("screenshot.path", path)
        yield span
