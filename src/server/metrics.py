"""Prometheus metrics helpers for the MCP Service Public BJ server."""

from __future__ import annotations

import threading

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

_LOCK = threading.Lock()
_REGISTRY: CollectorRegistry | None = None

# Prometheus collectors (initialised lazily so tests can reset the registry)
_TOOL_CALL_COUNTER: Counter
_TOOL_LATENCY_SECONDS: Histogram
_FETCH_COUNTER: Counter
_FETCH_LATENCY_SECONDS: Histogram
_HTTP_REQUEST_COUNTER: Counter
_HTTP_REQUEST_LATENCY_SECONDS: Histogram


def _initialise_registry() -> None:
    global _REGISTRY
    global _TOOL_CALL_COUNTER, _TOOL_LATENCY_SECONDS
    global _FETCH_COUNTER, _FETCH_LATENCY_SECONDS
    global _HTTP_REQUEST_COUNTER, _HTTP_REQUEST_LATENCY_SECONDS

    registry = CollectorRegistry()

    _TOOL_CALL_COUNTER = Counter(
        "mcp_tool_calls_total",
        "Number of tool invocations grouped by tool and status.",
        ["tool", "status"],
        registry=registry,
    )
    _TOOL_LATENCY_SECONDS = Histogram(
        "mcp_tool_latency_seconds",
        "Execution time of tool invocations.",
        ["tool"],
        registry=registry,
    )
    _FETCH_COUNTER = Counter(
        "mcp_provider_fetch_total",
        "Number of live fetches executed by providers.",
        ["provider", "outcome", "cache"],
        registry=registry,
    )
    _FETCH_LATENCY_SECONDS = Histogram(
        "mcp_provider_fetch_seconds",
        "Latency of provider live fetches (cache hits are recorded as zero).",
        ["provider", "cache"],
        registry=registry,
    )
    _HTTP_REQUEST_COUNTER = Counter(
        "mcp_http_requests_total",
        "HTTP requests handled by the streamable HTTP server.",
        ["method", "path", "status"],
        registry=registry,
    )
    _HTTP_REQUEST_LATENCY_SECONDS = Histogram(
        "mcp_http_request_seconds",
        "HTTP handler latency for the streamable HTTP server.",
        ["method", "path"],
        registry=registry,
    )

    _REGISTRY = registry


def _ensure_registry() -> None:
    if _REGISTRY is None:
        with _LOCK:
            if _REGISTRY is None:
                _initialise_registry()


def record_tool_invocation(tool: str, status: str, duration_seconds: float) -> None:
    """Record a tool invocation."""

    _ensure_registry()
    _TOOL_CALL_COUNTER.labels(tool=tool, status=status).inc()
    _TOOL_LATENCY_SECONDS.labels(tool=tool).observe(duration_seconds)


def record_fetch(provider: str, *, cache_hit: bool, outcome: str, duration_seconds: float) -> None:
    """Record a provider fetch (live or cache)."""

    _ensure_registry()
    cache_label = "hit" if cache_hit else "miss"
    _FETCH_COUNTER.labels(provider=provider, outcome=outcome, cache=cache_label).inc()
    _FETCH_LATENCY_SECONDS.labels(provider=provider, cache=cache_label).observe(duration_seconds)


def record_http_request(
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record an HTTP request handled by the streamable HTTP server."""

    _ensure_registry()
    _HTTP_REQUEST_COUNTER.labels(
        method=method,
        path=path,
        status=str(status_code),
    ).inc()
    _HTTP_REQUEST_LATENCY_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def metrics_payload() -> tuple[bytes, str]:
    """Return the Prometheus metrics payload and content type."""

    _ensure_registry()
    return generate_latest(_REGISTRY or CollectorRegistry()), CONTENT_TYPE_LATEST


def reset_metrics_for_tests() -> None:  # pragma: no cover - test utility
    """Reset the registry so tests can run with a clean state."""

    with _LOCK:
        _initialise_registry()
