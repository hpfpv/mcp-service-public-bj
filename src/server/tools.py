"""MCP tool handlers that orchestrate provider calls and registry state."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from .providers import BaseProvider, ProviderRegistry
from .registry import RegistryState
from .search import ServiceSearchIndex

PersistCallable = Callable[[], Awaitable[None]] | None


def _resolve_provider(registry: ProviderRegistry, provider_id: str | None) -> BaseProvider:
    if provider_id:
        return registry.get(provider_id)
    for provider in registry.all():
        return provider
    raise RuntimeError("No providers registered.")


async def _persist(persist_state: PersistCallable) -> None:
    if not persist_state:
        return
    await persist_state()


async def list_categories_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
    parent_id: str | None = None,
    refresh: bool = False,
    persist_state: PersistCallable = None,
) -> Dict[str, Any]:
    provider = _resolve_provider(registry, provider_id)
    warnings: List[str] = []
    source = "live"
    try:
        categories = await provider.list_categories(parent_id=parent_id, refresh=refresh)
        source = getattr(provider, "_last_category_source", source)
        await _persist(persist_state)
    except Exception as exc:  # pragma: no cover - fallback path
        source = "cache"
        warnings.append(str(exc))
        catalog = registry_state.ensure_catalog(provider.provider_id)
        if parent_id is None:
            categories = list(catalog.categories.values())
        else:
            categories = registry_state.categories_for_parent(provider.provider_id, parent_id)
        if not categories:
            raise

    payload: Dict[str, Any] = {
        "provider_id": provider.provider_id,
        "source": source,
        "categories": [category.model_dump(mode="json") for category in categories],
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


async def search_services_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
    query: str,
    category_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    refresh: bool = False,
    persist_state: PersistCallable = None,
) -> Dict[str, Any]:
    provider = _resolve_provider(registry, provider_id)
    warnings: List[str] = []
    source = "live"
    try:
        results = await provider.search_services(
            query,
            category_id=category_id,
            limit=limit,
            offset=offset,
            refresh=refresh,
        )
        source = getattr(provider, "_last_search_source", source)
        await _persist(persist_state)
    except Exception as exc:  # pragma: no cover - fallback path
        source = "cache"
        warnings.append(str(exc))
        index = ServiceSearchIndex(registry_state, provider.provider_id)
        results = index.search(query, limit=offset + limit)[offset : offset + limit]
        if not results:
            raise

    total_results = getattr(provider, "_last_search_total", None)
    if total_results is None:
        total_results = offset + len(results)
    next_offset = offset + len(results)
    if next_offset >= total_results:
        next_offset = None

    payload: Dict[str, Any] = {
        "provider_id": provider.provider_id,
        "source": source,
        "results": [result.model_dump(mode="json") for result in results[:limit]],
        "limit": limit,
        "offset": offset,
        "total_results": total_results,
        "next_offset": next_offset,
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


async def get_service_details_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
    service_id: str,
    refresh: bool = False,
    persist_state: PersistCallable = None,
) -> Dict[str, Any]:
    provider = _resolve_provider(registry, provider_id)
    details = await provider.get_service_details(service_id, refresh=refresh)
    source = getattr(provider, "_last_detail_source", "live")
    await _persist(persist_state)

    payload: Dict[str, Any] = {
        "provider_id": provider.provider_id,
        "source": source,
        "service": details.model_dump(mode="json"),
    }
    return payload


async def validate_service_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
    service_id: str,
    persist_state: PersistCallable = None,
) -> Dict[str, Any]:
    provider = _resolve_provider(registry, provider_id)
    details = await provider.validate_service(service_id)
    source = getattr(provider, "_last_detail_source", "live")
    await _persist(persist_state)

    payload: Dict[str, Any] = {
        "provider_id": provider.provider_id,
        "source": source,
        "service": details.model_dump(mode="json"),
        "validated": True,
    }
    return payload


async def get_scraper_status_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
) -> Dict[str, Any]:
    provider = _resolve_provider(registry, provider_id)
    status = await provider.get_status()
    catalog = registry_state.ensure_catalog(provider.provider_id)
    registry_meta = {
        "categories_indexed": len(catalog.categories),
        "services_indexed": len(catalog.services),
    }
    return {
        "provider_id": provider.provider_id,
        "status": status,
        "registry": registry_meta,
    }
