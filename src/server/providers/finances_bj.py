"""Provider implementation for finances.bj using its public WordPress JSON API."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from parsel import Selector
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings
from ..health import ScraperHealthMonitor
from ..live_fetch import LiveFetchClient
from ..models import Category, ContactPoint, DocumentLink, ServiceDetails, ServiceSummary
from ..registry import RegistryState
from ..search import ServiceSearchIndex
from ..selectors import normalise_whitespace
from .base import BaseProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinancesEndpoints:
    """Endpoint configuration for the finances.bj WordPress instance."""

    taxonomy: str = "wp-json/wp/v2/type_service"
    services: str = "wp-json/wp/v2/services"


def _as_text(value: Iterable[Any]) -> str:
    """Join, normalise and strip whitespace from text fragments."""

    parts: list[str] = []
    for part in value:
        if not part:
            continue
        if isinstance(part, Selector):
            extracted = part.get()
        else:
            extracted = str(part)
        if extracted:
            parts.append(extracted)
    combined = " ".join(parts).strip()
    return normalise_whitespace(combined)


class FinancesBJProvider(BaseProvider):
    """Provider that queries the finances.bj WordPress JSON API."""

    provider_id = "finances-bj"
    display_name = "Finances BJ"
    _PER_PAGE_DEFAULT = 20
    _PER_PAGE_MAX = 100

    def __init__(
        self,
        settings: Settings,
        *,
        registry_state: RegistryState | None = None,
        health_monitor: ScraperHealthMonitor | None = None,
    ) -> None:
        super().__init__(settings)
        self._health_monitor = health_monitor
        self._registry_state = registry_state or RegistryState()
        self._fetcher = LiveFetchClient(
            settings,
            base_url=str(settings.finances_base_url),
            provider_id=self.provider_id,
            monitor=health_monitor,
        )
        self._endpoints = FinancesEndpoints()
        self._search_index = ServiceSearchIndex(self._registry_state, self.provider_id)
        self._last_category_source = "live"
        self._last_search_source = "live"
        self._last_detail_source = "live"
        self._last_search_total = 0

    async def initialise(self) -> None:
        logger.info("provider_initialised provider=%s", self.provider_id)

    async def shutdown(self) -> None:
        await self._fetcher.close()

    async def _get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
    ) -> Any:
        url = path
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}?{query}"
        text = await self._fetcher.fetch_text(url, use_cache=use_cache)
        return json.loads(text)

    async def _get_json_with_headers(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        refresh: bool,
    ) -> tuple[Any, dict[str, Any]]:
        url = path
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}?{query}"
        response = await self._fetcher.fetch_response(url, use_cache=not refresh)
        return json.loads(response.text), response.headers

    @retry(wait=wait_exponential(multiplier=1, min=1, max=6), stop=stop_after_attempt(3))
    async def list_categories(
        self,
        parent_id: str | None = None,
        *,
        refresh: bool = False,
    ) -> list[Category]:
        catalog = self._registry_state.ensure_catalog(self.provider_id)
        if not refresh and catalog.categories:
            self._last_category_source = "cache"
            categories = list(catalog.categories.values())
            if parent_id is None:
                return categories
            return [category for category in categories if category.parent_id == parent_id]

        per_page = self._PER_PAGE_MAX
        page = 1
        categories: list[Category] = []
        while True:
            payload = await self._get_json(
                self._endpoints.taxonomy,
                params={"per_page": per_page, "page": page},
                use_cache=not refresh,
            )
            if not payload:
                break
            for order, item in enumerate(payload, start=len(categories)):
                name = normalise_whitespace(item.get("name", ""))
                if not name:
                    continue
                category = Category(
                    id=str(item.get("id")),
                    name=name,
                    url=item.get("link") or str(self.settings.finances_base_url),
                    provider_id=self.provider_id,
                    description=normalise_whitespace(item.get("description", "")) or None,
                    parent_id=str(item.get("parent")) if item.get("parent") else None,
                    order=order,
                )
                categories.append(category)
            if len(payload) < per_page:
                break
            page += 1

        self._registry_state.update_categories(self.provider_id, categories, replace=True)
        self._last_category_source = "live"
        if parent_id is not None:
            return [category for category in categories if category.parent_id == parent_id]
        return categories

    def _resolve_category_filter(self, category_id: str | None) -> dict[str, str]:
        if not category_id:
            return {}
        return {"type_service": category_id}

    def _per_page_for_limit(self, limit: int | None) -> int:
        if limit is None or limit <= 0:
            return self._PER_PAGE_DEFAULT
        return min(limit, self._PER_PAGE_MAX)

    @retry(wait=wait_exponential(multiplier=1, min=1, max=6), stop=stop_after_attempt(3))
    async def search_services(
        self,
        query: str,
        *,
        category_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        refresh: bool = False,
    ) -> list[ServiceSummary]:
        per_page = self._per_page_for_limit(limit)
        per_page = max(per_page, self._PER_PAGE_DEFAULT)
        per_page = min(per_page, self._PER_PAGE_MAX)

        page = max(offset // per_page + 1, 1)
        offset_in_page = offset % per_page

        results: list[ServiceSummary] = []
        total_results: int | None = None
        total_pages: int | None = None
        current_page = page
        first_page = True

        while True:
            params: dict[str, Any] = {
                "search": query,
                "per_page": per_page,
                "page": current_page,
                "status": "publish",
                "_embed": "false",
                "_fields": "id,link,title,excerpt.rendered,content.rendered,type_service",
            }
            params.update(self._resolve_category_filter(category_id))

            payload, headers = await self._get_json_with_headers(
                self._endpoints.services,
                params=params,
                refresh=refresh,
            )
            if not isinstance(payload, list):
                payload = []

            if total_results is None:
                raw_total = headers.get("X-WP-Total")
                try:
                    total_results = int(raw_total) if raw_total else None
                except (TypeError, ValueError):
                    total_results = None
            if total_pages is None:
                raw_pages = headers.get("X-WP-TotalPages")
                try:
                    total_pages = int(raw_pages) if raw_pages else None
                except (TypeError, ValueError):
                    total_pages = None

            slice_start = offset_in_page if first_page else 0
            for item in payload[slice_start:]:
                service_id = item.get("id")
                title = normalise_whitespace(item.get("title", {}).get("rendered", ""))
                link = item.get("link")
                if not service_id or not title or not link:
                    continue
                summary = ServiceSummary(
                    id=str(service_id),
                    title=title,
                    url=link,
                    provider_id=self.provider_id,
                    category_ids=[str(cat_id) for cat_id in item.get("type_service", [])],
                    excerpt=self._extract_excerpt(item),
                )
                results.append(summary)
                if limit and len(results) >= limit:
                    break

            if limit and len(results) >= limit:
                break
            if total_pages is not None and current_page >= total_pages:
                break
            if not payload:
                break

            current_page += 1
            first_page = False
            offset_in_page = 0

        if results:
            self._registry_state.update_services(self.provider_id, results, replace=False)
            self._search_index.rebuild()
        self._last_search_source = "live"
        if total_results is None:
            total_results = offset + len(results)
        self._last_search_total = total_results
        return results

    def _extract_excerpt(self, item: dict[str, Any]) -> str | None:
        content = item.get("excerpt", {}).get("rendered") or item.get("content", {}).get("rendered")
        if not content:
            return None
        selector = Selector(text=content)
        paragraph = selector.xpath("//p[normalize-space()]").get()
        if not paragraph:
            text = selector.xpath("normalize-space(//text())").get()
            return normalise_whitespace(text or "") or None
        paragraph_text = Selector(text=paragraph).xpath("normalize-space(.)").get()
        return normalise_whitespace(paragraph_text or "") or None

    @retry(wait=wait_exponential(multiplier=1, min=1, max=6), stop=stop_after_attempt(3))
    async def get_service_details(
        self,
        service_id: str,
        *,
        refresh: bool = False,
    ) -> ServiceDetails:
        if not refresh:
            cached = self._registry_state.get_service_details(self.provider_id, service_id)
            if cached is not None:
                self._last_detail_source = "cache"
                return cached

        payload = await self._get_json(
            f"{self._endpoints.services}/{service_id}",
            params={
                "_fields": "id,link,title,content.rendered,excerpt.rendered,type_service,guid",
            },
            use_cache=not refresh,
        )

        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected payload for service {service_id!r}")

        title = normalise_whitespace(payload.get("title", {}).get("rendered", ""))
        link = payload.get("link") or payload.get("guid", {}).get("rendered")
        if not title or not link:
            raise ValueError(f"Incomplete service payload for {service_id!r}")

        category_ids = [str(cat_id) for cat_id in payload.get("type_service", [])]

        summary_text, contacts, external_links = self._parse_content(payload.get("content", {}))

        details = ServiceDetails(
            id=str(payload.get("id")),
            title=title,
            url=link,
            provider_id=self.provider_id,
            category_ids=category_ids,
            excerpt=self._extract_excerpt(payload),
            summary=summary_text,
            contacts=contacts,
            external_links=external_links,
        )

        self._registry_state.set_service_details(self.provider_id, details)
        self._last_detail_source = "live"
        return details

    def _parse_content(
        self,
        content_payload: dict[str, Any] | None,
    ) -> tuple[str | None, list[ContactPoint], list[DocumentLink]]:
        html = content_payload.get("rendered") if content_payload else None
        if not html:
            return None, [], []

        selector = Selector(text=html)
        current_section: str | None = None
        sections: dict[str, list[str]] = {}
        contacts: list[ContactPoint] = []
        external_links: list[DocumentLink] = []

        for element in selector.xpath("//p|//ul|//ol"):
            strong_text = element.xpath("string(child::strong)").get()
            non_strong_text = _as_text(element.xpath("text()[normalize-space()]"))
            is_heading = bool(strong_text and not non_strong_text)
            if is_heading:
                heading_text = normalise_whitespace(strong_text or "")
                current_section = heading_text.lower()
                sections.setdefault(current_section, [])
                continue

            text_value = normalise_whitespace(element.xpath("normalize-space(.)").get() or "")
            if not text_value:
                continue
            key = current_section or "body"
            sections.setdefault(key, []).append(text_value)

            links = [
                normalise_whitespace(href)
                for href in element.xpath(".//a/@href").getall()
                if href
            ]
            for href in links:
                link_title = normalise_whitespace(element.xpath("string(.//a[1])").get() or href)
                external_links.append(
                    DocumentLink(
                        title=link_title or href,
                        url=href,
                    )
                )
            if current_section and current_section.startswith("adresse"):
                contacts.append(ContactPoint(label="Adresse", value=text_value))
            if current_section and "structure" in current_section:
                contacts.append(ContactPoint(label="Structure", value=text_value))

        summary_text: str | None = None
        if sections.get("description"):
            summary_text = normalise_whitespace(sections["description"][0])
        elif sections.get("body"):
            for candidate in sections["body"]:
                normalised = normalise_whitespace(candidate)
                if normalised.lower() in {"description", "adresse", "structure"}:
                    continue
                summary_text = normalised
                break
        else:
            fallback = selector.xpath("normalize-space(//p[not(child::strong)][1])").get()
            if fallback:
                summary_text = normalise_whitespace(fallback)

        # Deduplicate contacts based on (label, value)
        seen_contacts = set()
        deduped_contacts: list[ContactPoint] = []
        for contact in contacts:
            key = (contact.label, contact.value)
            if key in seen_contacts:
                continue
            seen_contacts.add(key)
            deduped_contacts.append(contact)

        # Deduplicate external links by URL
        seen_links = set()
        deduped_links: list[DocumentLink] = []
        for link in external_links:
            key = (link.title, link.url)
            if key in seen_links:
                continue
            seen_links.add(key)
            deduped_links.append(link)

        return summary_text, deduped_contacts, deduped_links

    async def validate_service(self, service_id: str) -> ServiceDetails:
        validated = await super().validate_service(service_id)
        return validated

    async def get_status(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "category_source": self._last_category_source,
            "search_source": self._last_search_source,
            "detail_source": self._last_detail_source,
            "last_search_total": self._last_search_total,
        }
