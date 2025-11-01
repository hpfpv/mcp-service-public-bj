import asyncio
import time

import httpx
import pytest
import respx

from server.config import Settings
from server.live_fetch import LiveFetchClient
from server.models import Category, ServiceDetails, ServiceSummary
from server.providers import ProviderDescriptor, ProviderRegistry
from server.providers.base import BaseProvider
from server.registry import RegistryState
from server.tools import get_service_details_tool, search_services_tool


class NetworkFlakyProvider(BaseProvider):
    provider_id = "service-public-bj"
    display_name = "Flaky"

    def __init__(self, settings: Settings, fail_first: bool = False):
        super().__init__(settings)
        self._fail_first = fail_first
        self._calls = 0
        self._search_index = [
            ServiceSummary(
                id="PS001",
                title="Carte d'identité",
                url="https://example.com/service/PS001",
                provider_id=self.provider_id,
                category_ids=["identite"],
                excerpt="Résumé",
            )
        ]
        self._detail = ServiceDetails(
            id="PS001",
            title="Carte d'identité",
            url="https://example.com/service/PS001",
            provider_id=self.provider_id,
            category_ids=["identite"],
            summary="Résumé",
            steps=[],
            documents=[],
            requirements=[],
            costs=[],
            contacts=[],
        )
        self._categories = [
            Category(id="identite", name="Identité", url="https://example.com/identite", provider_id=self.provider_id)
        ]

    async def initialise(self):
        return None

    async def shutdown(self):
        return None

    async def list_categories(self, parent_id=None, *, refresh=False):
        return self._categories

    async def search_services(self, query, *, category_id=None, limit=None, offset=0, refresh=False):
        self._calls += 1
        if self._fail_first and self._calls == 1:
            raise httpx.ConnectError("network down")
        lowered = (query or "").lower()
        results = [svc for svc in self._search_index if lowered in svc.title.lower()]
        if limit is not None:
            return results[offset : offset + limit]
        return results[offset:]

    async def get_service_details(self, service_id, *, refresh=False):
        return self._detail

    async def validate_service(self, service_id):
        return self._detail

    async def get_status(self):
        return {"healthy": True}


class EmptyProvider(BaseProvider):
    provider_id = "empty"
    display_name = "Empty"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    async def initialise(self):
        return None

    async def shutdown(self):
        return None

    async def list_categories(self, parent_id=None, *, refresh=False):
        self._last_category_source = "live"
        return []

    async def search_services(
        self,
        query,
        *,
        category_id=None,
        limit=None,
        offset=0,
        refresh=False,
    ):
        self._last_search_source = "live"
        return []

    async def get_service_details(self, service_id, *, refresh=False):
        self._last_detail_source = "live"
        raise KeyError(service_id)

    async def validate_service(self, service_id):
        raise KeyError(service_id)

    async def get_status(self):
        return {"healthy": True}


class SuccessfulProvider(NetworkFlakyProvider):
    provider_id = "success"
    display_name = "Success"


def register_test_provider(registry: ProviderRegistry, provider: BaseProvider, *, priority: int = 50) -> None:
    registry.register(
        provider,
        ProviderDescriptor(
            id=provider.provider_id,
            name=provider.display_name,
            description="Test provider",
            priority=priority,
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


@pytest.mark.asyncio
async def test_live_fetch_network_failure(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    client = LiveFetchClient(settings, base_url="https://example.com/", provider_id="service-public-bj")
    async with respx.mock(base_url="https://example.com") as resmock:
        resmock.get("/api/test").side_effect = httpx.ConnectError("down")
        with pytest.raises(httpx.ConnectError):
            await client.fetch_text("/api/test", use_cache=False)
    await client.close()


@pytest.mark.asyncio
async def test_search_concurrent_access(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    provider = NetworkFlakyProvider(settings)
    registry_state = RegistryState()
    registry = ProviderRegistry()
    register_test_provider(registry, provider)

    async def run_query():
        return await search_services_tool(
            registry,
            registry_state,
            query="carte",
            limit=1,
        )

    results = await asyncio.gather(*(run_query() for _ in range(5)))
    assert all(result["results"][0]["id"] == "PS001" for result in results)


@pytest.mark.asyncio
async def test_search_malformed_data(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    provider = NetworkFlakyProvider(settings)
    provider._search_index = [
        ServiceSummary(
            id="PS001",
            title="Carte",
            url="https://example.com/service/PS001",
            provider_id=provider.provider_id,
            category_ids=["identite"],
            excerpt=None,
        )
    ]
    registry_state = RegistryState()
    registry = ProviderRegistry()
    register_test_provider(registry, provider)

    result = await search_services_tool(
        registry,
        registry_state,
        query="carte",
    )
    assert result["results"][0]["title"] == "Carte"


@pytest.mark.asyncio
async def test_provider_failover_cache(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    provider = NetworkFlakyProvider(settings)
    registry_state = RegistryState()
    registry = ProviderRegistry()
    register_test_provider(registry, provider)

    # Prime cache with a successful fetch to seed registry state
    await search_services_tool(registry, registry_state, query="carte")
    registry_state.update_services(provider.provider_id, provider._search_index)

    # Next call should hit cache due to induced failure
    provider._fail_first = True
    provider._calls = 0
    result = await search_services_tool(registry, registry_state, query="carte")
    assert result["source"] in ("cache", "live")
    assert result["results"][0]["id"] == "PS001"


@pytest.mark.performance
@pytest.mark.asyncio
async def test_search_performance(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    provider = NetworkFlakyProvider(settings)
    registry_state = RegistryState()
    registry = ProviderRegistry()
    register_test_provider(registry, provider)

    start = time.perf_counter()
    await search_services_tool(registry, registry_state, query="carte")
    duration = time.perf_counter() - start
    assert duration < 0.5


@pytest.mark.asyncio
async def test_security_input_sanitization(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    provider = NetworkFlakyProvider(settings)
    registry_state = RegistryState()
    registry = ProviderRegistry()
    register_test_provider(registry, provider)

    malicious_query = "<script>alert('xss')</script>"
    result = await search_services_tool(registry, registry_state, query=malicious_query)
    assert result["results"] == []


@pytest.mark.asyncio
async def test_fallback_to_next_provider(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    empty_provider = EmptyProvider(settings)
    success_provider = SuccessfulProvider(settings)
    registry_state = RegistryState()
    registry = ProviderRegistry()
    register_test_provider(registry, empty_provider, priority=100)
    register_test_provider(registry, success_provider, priority=50)

    search_result = await search_services_tool(registry, registry_state, query="carte")
    assert search_result["provider_id"] == success_provider.provider_id
    assert search_result["results"][0]["id"] == "PS001"
    assert any("empty" in warning for warning in search_result.get("warnings", []))

    details_result = await get_service_details_tool(
        registry,
        registry_state,
        service_id="PS001",
    )
    assert details_result["provider_id"] == success_provider.provider_id
    assert any("empty" in warning for warning in details_result.get("warnings", []))


@pytest.mark.asyncio
async def test_chaos_random_failures(tmp_path):
    settings = Settings(cache_dir=tmp_path / "registry")
    provider = NetworkFlakyProvider(settings)
    registry_state = RegistryState()
    registry = ProviderRegistry()
    register_test_provider(registry, provider)

    async def flaky_call(i):
        if i % 2 == 0:
            provider._fail_first = True
        else:
            provider._fail_first = False
        try:
            return await search_services_tool(registry, registry_state, query="carte")
        except Exception:
            return {"error": True}

    results = await asyncio.gather(*(flaky_call(i) for i in range(10)))
    assert any(r.get("error") for r in results)
    assert any(r.get("results") for r in results if isinstance(r, dict))
