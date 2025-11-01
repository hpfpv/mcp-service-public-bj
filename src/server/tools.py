"""MCP tool handlers that orchestrate provider calls and registry state."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from rapidfuzz import fuzz

from .metrics import record_tool_invocation
from .providers import (
    BaseProvider,
    ProviderDescriptor,
    ProviderError,
    ProviderRegistry,
)
from .registry import RegistryState
from .search import ServiceSearchIndex

PersistCallable = Callable[[], Awaitable[None]] | None


async def _persist(persist_state: PersistCallable) -> None:
    if not persist_state:
        return
    await persist_state()


def _provider_candidates(
    registry: ProviderRegistry,
    provider_id: str | None,
    *,
    query: str | None = None,
) -> Iterable[tuple[BaseProvider, ProviderDescriptor]]:
    if provider_id:
        provider = registry.get(provider_id)
        descriptor = registry.get_descriptor(provider_id)
        yield provider, descriptor
        return

    descriptors = list(registry.ordered_descriptors())
    if query:
        query_normalized = query.lower()

        def coverage_score(descriptor: ProviderDescriptor) -> int:
            scores = [
                fuzz.partial_ratio(query_normalized, tag.lower())
                for tag in descriptor.coverage_tags
            ]
            return max(scores) if scores else 0

        descriptors.sort(
            key=lambda d: (
                coverage_score(d) >= 60,
                coverage_score(d),
                d.priority,
            ),
            reverse=True,
        )

    for descriptor in descriptors:
        provider = registry.get(descriptor.id)
        yield provider, descriptor


def _append_warnings(payload: dict[str, Any], warnings: list[str]) -> None:
    if not warnings:
        return
    existing = payload.setdefault("warnings", [])
    existing.extend(warnings)


def _descriptor_payload(descriptor: ProviderDescriptor) -> dict[str, Any]:
    return {
        "id": descriptor.id,
        "name": descriptor.name,
        "description": descriptor.description,
        "priority": descriptor.priority,
        "coverage_tags": list(descriptor.coverage_tags),
        "supported_tools": list(descriptor.supported_tools),
    }


async def _list_categories_single(
    provider: BaseProvider,
    registry_state: RegistryState,
    *,
    parent_id: str | None,
    refresh: bool,
    persist_state: PersistCallable,
) -> dict[str, Any]:
    start = time.perf_counter()
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


async def _search_services_single(
    provider: BaseProvider,
    registry_state: RegistryState,
    *,
    query: str,
    category_id: str | None,
    limit: int | None,
    offset: int,
    refresh: bool,
    persist_state: PersistCallable,
) -> dict[str, Any]:
    start = time.perf_counter()
    warnings: list[str] = []
    source = "live"
    requested_limit = limit if limit is not None else None
    status = "success"
    try:
        results = await provider.search_services(
            query,
            category_id=category_id,
            limit=requested_limit or 10,
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


async def _get_service_details_single(
    provider: BaseProvider,
    *,
    service_id: str,
    refresh: bool,
    persist_state: PersistCallable,
) -> dict[str, Any]:
    start = time.perf_counter()
    status = "success"
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

    return {
        "provider_id": provider.provider_id,
        "source": source,
        "service": details.model_dump(mode="json"),
    }


async def _validate_service_single(
    provider: BaseProvider,
    *,
    service_id: str,
    persist_state: PersistCallable,
) -> dict[str, Any]:
    start = time.perf_counter()
    status = "success"
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

    return {
        "provider_id": provider.provider_id,
        "source": source,
        "service": details.model_dump(mode="json"),
        "validated": True,
    }


async def _get_status_single(
    provider: BaseProvider,
    registry_state: RegistryState,
) -> dict[str, Any]:
    status_payload = await provider.get_status()
    catalog = registry_state.ensure_catalog(provider.provider_id)
    return {
        "provider_id": provider.provider_id,
        "status": status_payload,
        "registry": {
            "categories_indexed": len(catalog.categories),
            "services_indexed": len(catalog.services),
        },
    }


async def list_categories_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
    parent_id: str | None = None,
    refresh: bool = False,
    persist_state: PersistCallable = None,
) -> dict[str, Any]:
    aggregated_warnings: list[str] = []
    last_payload: dict[str, Any] | None = None

    for provider, _ in _provider_candidates(registry, provider_id):
        try:
            payload = await _list_categories_single(
                provider,
                registry_state,
                parent_id=parent_id,
                refresh=refresh,
                persist_state=persist_state,
            )
        except Exception as exc:  # pragma: no cover - provider error, try next
            aggregated_warnings.append(f"{provider.provider_id}: {exc}")
            continue

        if payload["categories"]:
            _append_warnings(payload, aggregated_warnings)
            return payload

        aggregated_warnings.append(f"{provider.provider_id}: no categories returned")
        last_payload = payload

    if last_payload is not None:
        _append_warnings(last_payload, aggregated_warnings)
        return last_payload

    raise ProviderError("No providers returned categories")


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
    aggregated_warnings: list[str] = []
    last_payload: dict[str, Any] | None = None

    for provider, _ in _provider_candidates(registry, provider_id, query=query):
        try:
            payload = await _search_services_single(
                provider,
                registry_state,
                query=query,
                category_id=category_id,
                limit=limit,
                offset=offset,
                refresh=refresh,
                persist_state=persist_state,
            )
        except Exception as exc:  # pragma: no cover - provider error, try next
            aggregated_warnings.append(f"{provider.provider_id}: {exc}")
            continue

        if payload["results"]:
            _append_warnings(payload, aggregated_warnings)
            return payload

        aggregated_warnings.append(f"{provider.provider_id}: no results returned")
        last_payload = payload

    if last_payload is not None:
        _append_warnings(last_payload, aggregated_warnings)
        return last_payload

    raise ProviderError("No providers returned results")


async def get_service_details_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
    service_id: str,
    refresh: bool = False,
    persist_state: PersistCallable = None,
) -> dict[str, Any]:
    aggregated_warnings: list[str] = []

    for provider, _ in _provider_candidates(registry, provider_id):
        try:
            payload = await _get_service_details_single(
                provider,
                service_id=service_id,
                refresh=refresh,
                persist_state=persist_state,
            )
        except Exception as exc:
            aggregated_warnings.append(f"{provider.provider_id}: {exc}")
            continue

        _append_warnings(payload, aggregated_warnings)
        return payload

    raise ProviderError(
        "No providers returned details for the requested service"
    )


async def validate_service_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
    service_id: str,
    persist_state: PersistCallable = None,
) -> dict[str, Any]:
    aggregated_warnings: list[str] = []

    for provider, _ in _provider_candidates(registry, provider_id):
        try:
            payload = await _validate_service_single(
                provider,
                service_id=service_id,
                persist_state=persist_state,
            )
        except Exception as exc:
            aggregated_warnings.append(f"{provider.provider_id}: {exc}")
            continue

        _append_warnings(payload, aggregated_warnings)
        return payload

    raise ProviderError("No providers validated the requested service")


async def get_scraper_status_tool(
    registry: ProviderRegistry,
    registry_state: RegistryState,
    *,
    provider_id: str | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    status_label = "success"
    items: list[dict[str, Any]] = []
    try:
        for provider, descriptor in _provider_candidates(registry, provider_id):
            item = await _get_status_single(provider, registry_state)
            item["descriptor"] = _descriptor_payload(descriptor)
            items.append(item)
    except Exception:
        status_label = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        record_tool_invocation("get_scraper_status", status_label, duration)

    return {"providers": items}


async def list_providers_tool(registry: ProviderRegistry) -> dict[str, Any]:
    start = time.perf_counter()
    providers = [
        _descriptor_payload(descriptor)
        for descriptor in registry.ordered_descriptors()
    ]
    duration = time.perf_counter() - start
    record_tool_invocation("list_providers", "success", duration)
    return {"providers": providers}
