"""MCP tool handlers that orchestrate provider calls and registry state."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from .metrics import record_tool_invocation
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
) -> dict[str, Any]:
    start = time.perf_counter()
    provider = _resolve_provider(registry, provider_id)
    warnings: list[str] = []
    source = "live"
    status = "success"
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
            status = "error"
            raise
    finally:
        duration = time.perf_counter() - start
        record_tool_invocation("list_categories", status, duration)

    payload: dict[str, Any] = {
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
    limit: int | None = None,
    offset: int = 0,
    refresh: bool = False,
    persist_state: PersistCallable = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    provider = _resolve_provider(registry, provider_id)
    warnings: list[str] = []
    source = "live"
    requested_limit = limit if limit is not None else None
    status = "success"
    try:
        results = await provider.search_services(
            query,
            category_id=category_id,
            limit=requested_limit,
            offset=offset,
            refresh=refresh,
        )
        source = getattr(provider, "_last_search_source", source)
        await _persist(persist_state)
    except Exception as exc:  # pragma: no cover - fallback path
        source = "cache"
        warnings.append(str(exc))
        index = ServiceSearchIndex(registry_state, provider.provider_id)
        catalog = registry_state.ensure_catalog(provider.provider_id)
        fallback_limit = offset + requested_limit if requested_limit is not None else len(
            catalog.services
        ) or 0
        if fallback_limit == 0:
            fallback_limit = 100
        cache_hits = index.search(query, limit=fallback_limit)
        results = cache_hits[offset : offset + (requested_limit or len(cache_hits))]
        if not results:
            status = "error"
            raise

    total_results = getattr(provider, "_last_search_total", None)
    if total_results is None:
        total_results = offset + len(results)
    if requested_limit is None:
        next_offset = None
    else:
        next_offset = offset + len(results)
        if next_offset >= total_results:
            next_offset = None

    effective_limit = requested_limit if requested_limit is not None else len(results)
    duration = time.perf_counter() - start
    record_tool_invocation("search_services", status, duration)

    payload: dict[str, Any] = {
        "provider_id": provider.provider_id,
        "source": source,
        "results": [result.model_dump(mode="json") for result in results],
        "limit": effective_limit,
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
) -> dict[str, Any]:
    start = time.perf_counter()
    status = "success"
    provider = _resolve_provider(registry, provider_id)
    try:
        details = await provider.get_service_details(service_id, refresh=refresh)
        source = getattr(provider, "_last_detail_source", "live")
        await _persist(persist_state)
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        record_tool_invocation("get_service_details", status, duration)

    payload: dict[str, Any] = {
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
) -> dict[str, Any]:
    start = time.perf_counter()
    status = "success"
    provider = _resolve_provider(registry, provider_id)
    try:
        details = await provider.validate_service(service_id)
        source = getattr(provider, "_last_detail_source", "live")
        await _persist(persist_state)
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        record_tool_invocation("validate_service", status, duration)

    payload: dict[str, Any] = {
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
) -> dict[str, Any]:
    start = time.perf_counter()
    status_label = "success"
    provider = _resolve_provider(registry, provider_id)
    try:
        status = await provider.get_status()
        catalog = registry_state.ensure_catalog(provider.provider_id)
    except Exception:
        status_label = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        record_tool_invocation("get_scraper_status", status_label, duration)

    registry_meta = {
        "categories_indexed": len(catalog.categories),
        "services_indexed": len(catalog.services),
    }
    return {
        "provider_id": provider.provider_id,
        "status": status,
        "registry": registry_meta,
    }
