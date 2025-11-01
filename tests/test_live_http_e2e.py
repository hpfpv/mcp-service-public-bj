import json
import os

import httpx
import pytest

RUN_LIVE = os.getenv("RUN_LIVE_HTTP_E2E") is not None
LIVE_URL = os.getenv("MCP_LIVE_HTTP_URL", "http://localhost:8000/mcp").rstrip("/") + "/"


@pytest.mark.asyncio
async def test_live_http_endpoint_end_to_end() -> None:
    if not RUN_LIVE:
        pytest.skip("Set RUN_LIVE_HTTP_E2E=1 to run live HTTP e2e tests against a running server.")

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    session_id: str | None = None

    async def rpc(client: httpx.AsyncClient, payload: dict) -> dict:
        nonlocal session_id
        request_headers = dict(headers)
        if session_id:
            request_headers["MCP-Session-Id"] = session_id
        response = await client.post(
            LIVE_URL,
            content=json.dumps(payload),
            headers=request_headers,
            follow_redirects=True,
        )
        response.raise_for_status()
        if "MCP-Session-Id" in response.headers:
            session_id = response.headers["MCP-Session-Id"]
        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("text/event-stream"):
            # The first SSE data line contains the JSON payload.
            text = response.text
            data_line = next(
                (line for line in text.splitlines() if line.startswith("data: ")),
                None,
            )
            if not data_line:
                pytest.fail(f"Unexpected SSE payload:\n{text}")
            body = json.loads(data_line[len("data: ") :])
        else:
            body = response.json()
        if "error" in body:
            pytest.fail(f"MCP error response: {body['error']}")
        return body

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            initialize = await rpc(
                client,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "live-e2e", "version": "0.0.0"},
                    },
                },
            )
        except httpx.RequestError as exc:
            pytest.skip(f"Could not reach live MCP server at {LIVE_URL}: {exc}")

        assert initialize["id"] == 1

        list_tools = await rpc(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {tool["name"] for tool in list_tools["result"]["tools"]}
        assert {"list_providers", "search_services", "get_scraper_status"}.issubset(tool_names)

        provider_listing = await rpc(
            client,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_providers", "arguments": {}},
            },
        )
        providers = provider_listing["result"]["structuredContent"]["providers"]
        assert len(providers) >= 1

        search = await rpc(
            client,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "search_services",
                    "arguments": {
                        "query": "passeport",
                        "limit": 5,
                    },
                },
            },
        )
        search_payload = search["result"]["structuredContent"]
        assert "provider_id" in search_payload
        assert "results" in search_payload

        status = await rpc(
            client,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "get_scraper_status", "arguments": {}},
            },
        )
        status_payload = status["result"]["structuredContent"]
        assert isinstance(status_payload.get("providers"), list)
        assert status_payload["providers"], "Expected at least one provider status entry"
