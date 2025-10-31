from server.metrics import (
    metrics_payload,
    record_fetch,
    record_http_request,
    record_tool_invocation,
    reset_metrics_for_tests,
)


def test_metrics_payload_contains_recorded_values():
    reset_metrics_for_tests()

    record_tool_invocation("list_categories", "success", 0.05)
    record_fetch("service-public-bj", cache_hit=True, outcome="success", duration_seconds=0.0)
    record_http_request("GET", "healthz", 200, 0.01)

    payload, content_type = metrics_payload()

    assert content_type.startswith("text/plain")
    body = payload.decode()
    assert "mcp_tool_calls_total" in body
    assert "list_categories" in body
    assert "mcp_provider_fetch_total" in body
    assert "mcp_http_requests_total" in body
