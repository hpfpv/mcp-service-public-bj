import json

import httpx
import pytest

from server.config import Settings
from server.main import MCPServerRuntime, build_http_app
from server.models import Category, ServiceDetails, ServiceSummary
from server.providers import ProviderRegistry
from server.providers.base import BaseProvider
from server.registry import RegistryState


class DummyStore:
    def save(self, state: RegistryState) -> None:  # pragma: no cover - simple stub
        self.state = state


class StubProvider(BaseProvider):
    provider_id = "service-public-bj"
    display_name = "Stub Provider"

    def __init__(self, settings: Settings, data):
        super().__init__(settings)
        self._data = data
        self._status = {"healthy": True}
        self._last_search_total = len(data["services"])

    async def initialise(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def list_categories(self, parent_id=None, *, refresh: bool = False):
        self._last_category_source = "live"
        return self._data["categories"]

    async def search_services(
        self,
        query,
        *,
        category_id=None,
        limit=None,
        offset=0,
        refresh: bool = False,
    ):
        self._last_search_source = "live"
        results = self._data["services"]
        if category_id:
            results = [svc for svc in results if category_id in svc.category_ids]
        if limit is not None:
            results = results[offset : offset + limit]
        else:
            results = results[offset:]
        self._last_search_total = len(self._data["services"])
        return results

    async def get_service_details(self, service_id, *, refresh: bool = False):
        self._last_detail_source = "live"
        if service_id == self._data["detail"].id:
            return self._data["detail"]
        raise KeyError(service_id)

    async def validate_service(self, service_id):
        return await self.get_service_details(service_id, refresh=True)

    async def get_status(self):
        return self._status


@pytest.mark.asyncio
async def test_http_endpoint_end_to_end(tmp_path):
    settings = Settings(
        cache_dir=tmp_path / "registry",
        base_url="https://example.com/",
        enabled_providers=["service-public-bj"],
    )

    data = {
        "categories": [
            Category(
                id="identite",
                name="Identité",
                url="https://example.com/identite",
                provider_id="service-public-bj",
            )
        ],
        "services": [
            ServiceSummary(
                id="PS0001",
                title="Immatriculation consulaire",
                url="https://example.com/service/PS0001",
                provider_id="service-public-bj",
                category_ids=["identite"],
                excerpt="Procédure d'immatriculation",
            )
        ],
        "detail": ServiceDetails(
            id="PS0001",
            title="Immatriculation consulaire",
            url="https://example.com/service/PS0001",
            provider_id="service-public-bj",
            category_ids=["identite"],
            summary="Résumé",
            steps=[],
            documents=[],
            requirements=[],
            costs=[],
            contacts=[],
        ),
    }

    registry_state = RegistryState()
    store = DummyStore()
    registry = ProviderRegistry()
    registry.register(StubProvider(settings, data))

    runtime = MCPServerRuntime(
        settings=settings,
        registry_state=registry_state,
        registry_store=store,
        registry=registry,
    )

    app, transport = build_http_app(runtime, settings, json_response=True)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            headers = {
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
            session_id = None

            async def rpc(payload):
                nonlocal session_id
                final_headers = dict(headers)
                if session_id:
                    final_headers["MCP-Session-Id"] = session_id
                response = await client.post("/mcp/", content=json.dumps(payload), headers=final_headers)
                assert response.status_code == 200
                if "MCP-Session-Id" in response.headers:
                    session_id = response.headers["MCP-Session-Id"]
                body = response.json()
                assert "error" not in body, f"RPC error: {body['error']}"
                return body

            initialize = await rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0.0.0"},
                    },
                }
            )
            assert initialize["id"] == 1

            list_tools = await rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            assert "result" in list_tools, list_tools
            tool_names = {tool["name"] for tool in list_tools["result"]["tools"]}
            assert {"list_categories", "search_services", "get_service_details", "get_scraper_status"}.issubset(tool_names)

            categories = await rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "list_categories", "arguments": {}},
                }
            )
            assert "result" in categories, categories
            structured_categories = categories["result"]["structuredContent"]
            assert structured_categories["categories"][0]["id"] == "identite"

            search = await rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "search_services",
                        "arguments": {"query": "immatriculation"},
                    },
                }
            )
            assert "result" in search, search
            structured_search = search["result"]["structuredContent"]
            assert structured_search["results"][0]["id"] == "PS0001"

            details = await rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "get_service_details",
                        "arguments": {"service_id": "PS0001"},
                    },
                }
            )
            assert "result" in details, details
            structured_details = details["result"]["structuredContent"]
            assert structured_details["service"]["title"] == "Immatriculation consulaire"

            status = await rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "get_scraper_status", "arguments": {}},
                }
            )
            assert "result" in status, status
            structured_status = status["result"]["structuredContent"]
            assert structured_status["status"]["healthy"] is True

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as metrics_client:
            metrics_resp = await metrics_client.get("/metrics")
            assert metrics_resp.status_code == 200
            assert b"mcp_tool_calls_total" in metrics_resp.content

    await transport.terminate()
    await runtime.shutdown()
