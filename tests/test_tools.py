import pytest

from server.config import Settings
from server.models import Category, ServiceDetails, ServiceSummary
from server.providers import ProviderRegistry
from server.providers.base import BaseProvider
from server.registry import RegistryState
from server.tools import (
    get_scraper_status_tool,
    get_service_details_tool,
    list_categories_tool,
    search_services_tool,
    validate_service_tool,
)


class DummyProvider(BaseProvider):
    provider_id = "dummy"
    display_name = "Dummy"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    async def initialise(self):
        return None

    async def list_categories(self, parent_id=None, *, refresh: bool = False):
        self._last_category_source = "live"
        return [
            Category(
                id="cat",
                name="Category",
                url="https://example.com/cat",
                provider_id=self.provider_id,
            )
        ]

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
        return [
            ServiceSummary(
                id="svc",
                title="Service",
                url="https://example.com/svc",
                provider_id=self.provider_id,
                category_ids=["cat"],
            )
        ]

    async def get_service_details(self, service_id, *, refresh: bool = False):
        self._last_detail_source = "live"
        return ServiceDetails(
            id=service_id,
            title="Service",
            url="https://example.com/svc",
            provider_id=self.provider_id,
            category_ids=["cat"],
        )

    async def validate_service(self, service_id):
        return await self.get_service_details(service_id, refresh=True)

    async def get_status(self):
        return {"provider_id": self.provider_id, "healthy": True}


@pytest.mark.asyncio
async def test_tool_routing(tmp_path):
    settings = Settings(cache_dir=tmp_path, base_url="https://example.com")
    registry = ProviderRegistry()
    provider = DummyProvider(settings)
    registry.register(provider)
    registry_state = RegistryState()

    persist_calls = {"count": 0}

    async def persist():
        persist_calls["count"] += 1

    cats = await list_categories_tool(
        registry,
        registry_state,
        persist_state=persist,
    )
    assert cats["categories"][0]["name"] == "Category"
    assert cats["source"] == "live"

    results = await search_services_tool(
        registry,
        registry_state,
        query="test",
        persist_state=persist,
    )
    assert results["results"][0]["id"] == "svc"
    assert results["source"] == "live"
    assert results["offset"] == 0
    assert results["limit"] == 1
    assert results["total_results"] >= 1

    details = await get_service_details_tool(
        registry,
        registry_state,
        service_id="svc",
        persist_state=persist,
    )
    assert details["service"]["title"] == "Service"
    assert details["source"] == "live"

    validated = await validate_service_tool(
        registry,
        registry_state,
        service_id="svc",
        persist_state=persist,
    )
    assert validated["validated"] is True
    assert validated["service"]["id"] == "svc"
    assert validated["source"] == "live"

    status = await get_scraper_status_tool(registry, registry_state)
    assert status["provider_id"] == "dummy"
    assert status["registry"]["categories_indexed"] == 0

    assert persist_calls["count"] == 4
