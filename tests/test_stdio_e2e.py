import asyncio

import pytest
from anyio import create_memory_object_stream
from mcp import types
from mcp.shared.message import SessionMessage

from server.config import Settings
from server.main import MCPServerRuntime
from server.models import Category, ServiceDetails, ServiceSummary
from server.providers import ProviderDescriptor, ProviderRegistry
from server.providers.base import BaseProvider
from server.registry import RegistryState


class FakeStore:
    def save(self, state):  # pragma: no cover - simple stub
        self.state = state


class StdioStubProvider(BaseProvider):
    provider_id = "service-public-bj"
    display_name = "Stub"

    def __init__(self, settings, data):
        super().__init__(settings)
        self._data = data
        self._status = {"healthy": True}

    async def initialise(self):  # pragma: no cover
        return None

    async def shutdown(self):  # pragma: no cover
        return None

    async def list_categories(self, parent_id=None, *, refresh=False):
        self._last_category_source = "live"
        return self._data["categories"]

    async def search_services(self, query, *, category_id=None, limit=None, offset=0, refresh=False):
        self._last_search_source = "live"
        services = [svc for svc in self._data["services"] if query.lower() in svc.title.lower()]
        return services[offset : offset + limit] if limit else services[offset:]

    async def get_service_details(self, service_id, *, refresh=False):
        self._last_detail_source = "live"
        if service_id == self._data["detail"].id:
            return self._data["detail"]
        raise KeyError(service_id)

    async def validate_service(self, service_id):
        return await self.get_service_details(service_id, refresh=True)

    async def get_status(self):  # pragma: no cover
        return self._status


@pytest.mark.asyncio
async def test_stdio_runtime_end_to_end(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry", base_url="https://example.com/")
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
                id="PS001",
                title="Immatriculation consulaire",
                url="https://example.com/service/PS001",
                provider_id="service-public-bj",
                category_ids=["identite"],
                excerpt="Procédure",
            )
        ],
        "detail": ServiceDetails(
            id="PS001",
            title="Immatriculation consulaire",
            url="https://example.com/service/PS001",
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
    registry = ProviderRegistry()
    stdio_provider = StdioStubProvider(settings, data)
    registry.register(
        stdio_provider,
        ProviderDescriptor(
            id=stdio_provider.provider_id,
            name=stdio_provider.display_name,
            description="Stub provider for stdio e2e tests",
            priority=100,
            coverage_tags=("test",),
            supported_tools=(
                "list_categories",
                "search_services",
                "get_service_details",
                "validate_service",
                "get_scraper_status",
            ),
        ),
    )

    runtime = MCPServerRuntime(
        settings=settings,
        registry_state=registry_state,
        registry_store=FakeStore(),
        registry=registry,
    )

    read_writer, read_stream = create_memory_object_stream[SessionMessage | Exception](0)
    write_stream, write_reader = create_memory_object_stream[SessionMessage](0)

    async def send(request):
        message = types.JSONRPCMessage.model_validate(request)
        await read_writer.send(SessionMessage(message))
        response = await write_reader.receive()
        return response.message.model_dump()

    async def run_session():
        await runtime.run_session(read_stream, write_stream)

    task = asyncio.create_task(run_session())

    try:
        initialize = await send(
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
        assert initialize["result"] is not None

        list_tools = await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {tool["name"] for tool in list_tools["result"]["tools"]}
        assert {"list_providers", "search_services"}.issubset(tool_names)

        providers_listing = await send(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "list_providers", "arguments": {}},
            }
        )
        assert providers_listing["result"]["structuredContent"]["providers"][0]["id"] == "service-public-bj"

        categories_msg = await send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_categories", "arguments": {}},
            }
        )
        assert (
            categories_msg["result"]["structuredContent"]["categories"][0]["id"] == "identite"
        )

        search_msg = await send(
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
        assert search_msg["result"]["structuredContent"]["results"][0]["id"] == "PS001"

        status_msg = await send(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "get_scraper_status", "arguments": {}},
            }
        )
        assert (
            status_msg["result"]["structuredContent"]["providers"][0]["provider_id"]
            == "service-public-bj"
        )

    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
