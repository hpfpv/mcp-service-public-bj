"""Provider implementation for service-public.bj using its public JSON APIs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, List, Sequence
from urllib.parse import urlencode

from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings
from ..health import ScraperHealthMonitor
from ..live_fetch import LiveFetchClient
from ..models import (
    Category,
    ContactPoint,
    DocumentLink,
    Requirement,
    ServiceDetails,
    ServiceSummary,
    Step,
)
from ..registry import RegistryState, SelectorProfile
from ..search import ServiceSearchIndex
from ..selectors import normalise_whitespace
from .base import BaseProvider, ProviderError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServicePublicEndpoints:
    """Endpoint configuration for the service-public BJ provider."""

    portal_root: str = "api/{portal_type}/publicservices/"
    search: str = "api/{portal_type}/publicservices/search"
    service: str = "api/{portal_type}/publicservices/{service_id}"


class ServicePublicBJProvider(BaseProvider):
    """Provider that queries the live JSON APIs of service-public.bj."""

    provider_id = "service-public-bj"
    display_name = "Service Public BJ"

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
            base_url=str(settings.base_url),
            provider_id=self.provider_id,
            monitor=health_monitor,
        )
        self._search_index = ServiceSearchIndex(self._registry_state, self.provider_id)
        self._endpoints = ServicePublicEndpoints()
        self._portal_type = "portal"
        self._last_category_source = "live"
        self._last_search_source = "live"
        self._last_detail_source = "live"
        self._last_search_total = 0

    async def initialise(self) -> None:
        logger.info("provider_initialised provider=%s", self.provider_id)

    async def shutdown(self) -> None:
        await self._fetcher.close()

    def _api_path(self, template: str, **kwargs: str) -> str:
        return template.format(portal_type=self._portal_type, **kwargs)

    async def _get_json(
        self, path: str, params: dict[str, Any] | None = None, *, use_cache: bool = True
    ) -> dict[str, Any]:
        url = path
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}?{query}"
        text = await self._fetcher.fetch_text(url, use_cache=use_cache)
        return json.loads(text)

    def _category_url(self, slug: str) -> str:
        base = str(self.settings.base_url).rstrip("/")
        return f"{base}/public/services?category={slug}"

    def _service_url(self, service_id: str) -> str:
        base = str(self.settings.base_url).rstrip("/")
        return f"{base}/public/services/service/{service_id}"

    @retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
    async def list_categories(
        self, parent_id: str | None = None, *, refresh: bool = False
    ) -> List[Category]:
        catalog = self._registry_state.ensure_catalog(self.provider_id)
        if not refresh and catalog.categories:
            self._last_category_source = "cache"
            existing = list(catalog.categories.values())
            if parent_id:
                return [category for category in existing if category.parent_id == parent_id]
            return existing

        data = await self._get_json(
            self._api_path(self._endpoints.portal_root), params={"categories": "true"}
        )
        raw_categories: Sequence[str] = data.get("categories", [])
        categories: List[Category] = []
        for order, name in enumerate(raw_categories):
            if not name:
                continue
            clean_name = normalise_whitespace(name)
            if not clean_name:
                continue
            category_id = self._slug_from_text(clean_name)
            categories.append(
                Category(
                    id=category_id,
                    name=clean_name,
                    url=self._category_url(category_id),
                    provider_id=self.provider_id,
                    parent_id=None,
                    order=order,
                )
            )
        self._registry_state.update_categories(self.provider_id, categories, replace=True)
        self._last_category_source = "live"
        if parent_id:
            return [category for category in categories if category.parent_id == parent_id]
        return categories

    @retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
    async def search_services(
        self,
        query: str,
        *,
        category_id: str | None = None,
        limit: int = 10,
        offset: int = 0,
        refresh: bool = False,
    ) -> List[ServiceSummary]:
        data = await self._get_json(
            self._api_path(self._endpoints.search), params={"query": query}
        )
        services: Sequence[dict[str, Any]] = data.get("services", [])
        results: List[ServiceSummary] = []
        slice_end = offset + limit
        for item in services[offset:slice_end]:
            service_id = item.get("id")
            title = item.get("name")
            if not service_id or not title:
                continue
            category_slugs = [
                self._slug_from_text(cat)
                for cat in item.get("categories", [])
                if cat and cat.strip()
            ]
            if category_id and category_id not in category_slugs:
                continue
            results.append(
                ServiceSummary(
                    id=service_id,
                    title=normalise_whitespace(title),
                    url=self._service_url(service_id),
                    provider_id=self.provider_id,
                    category_ids=category_slugs,
                    excerpt=normalise_whitespace(item.get("description", "")).strip() or None,
                )
            )

        if results:
            self._registry_state.update_services(self.provider_id, results, replace=False)
            self._search_index.rebuild()
        self._last_search_source = "live"
        self._last_search_total = len(services)
        return results

    @retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
    async def get_service_details(
        self, service_id: str, *, refresh: bool = False
    ) -> ServiceDetails:
        if not refresh:
            cached_detail = self._registry_state.get_service_details(
                self.provider_id, service_id
            )
            if cached_detail is not None:
                self._last_detail_source = "cache"
                return cached_detail

        data = await self._get_json(
            self._api_path(self._endpoints.service, service_id=service_id)
        )

        title = data.get("name")
        if not title:
            raise ProviderError(f"Unable to extract title for service '{service_id}'.")

        overview = data.get("overview", {}) or {}
        m_service = data.get("mService", {}) or {}
        files = data.get("files", {}) or {}

        last_updated = None
        activation = m_service.get("mActivationDate") or overview.get("activationDate")
        if activation:
            try:
                last_updated = datetime.fromisoformat(activation.replace("Z", "+00:00"))
            except ValueError:
                last_updated = None

        documents: List[DocumentLink] = []
        for form in files.get("forms", []) or []:
            title_form = form.get("name") or form.get("formname")
            url = form.get("url")
            if title_form and url:
                documents.append(
                    DocumentLink(
                        title=normalise_whitespace(title_form),
                        url=url,
                        document_type="Formulaire",
                    )
                )

        for form in data.get("mServiceForms", []) or []:
            form_name = form.get("formname") or form.get("formfile")
            file_id = form.get("formfile")
            if not file_id:
                continue
            url = f"https://catis.xroad.bj//publicservices/{service_id}/files/{file_id}"
            documents.append(
                DocumentLink(
                    title=normalise_whitespace(form_name) if form_name else file_id,
                    url=url,
                    document_type="Formulaire",
                )
            )

        requirements: List[Requirement] = []
        docs_text = m_service.get("mDocuments") or ""
        for block in docs_text.split("\n"):
            cleaned = block.strip().lstrip("*").strip()
            if cleaned:
                requirements.append(Requirement(title=cleaned))

        steps: List[Step] = []
        process_text = m_service.get("mProcess") or ""
        if process_text.strip():
            for idx, block in enumerate(filter(None, process_text.split("\n\n")), start=1):
                steps.append(Step(title=f"Étape {idx}", content=block.strip()))

        contacts: List[ContactPoint] = []
        for channel in overview.get("Channelssp") or []:
            contacts.append(ContactPoint(label="Canal", value=channel))
        owner = overview.get("ownedBy")
        if owner and owner.get("name"):
            contacts.append(ContactPoint(label="Organisme responsable", value=owner["name"]))

        category_ids = [
            self._slug_from_text(cat)
            for cat in (overview.get("thematicArea") or [])
            if cat and cat.strip()
        ]

        details = ServiceDetails(
            id=service_id,
            title=normalise_whitespace(title),
            url=self._service_url(service_id),
            provider_id=self.provider_id,
            category_ids=category_ids,
            summary=normalise_whitespace(overview.get("description", "")) or None,
            last_updated=last_updated,
            steps=steps,
            requirements=requirements,
            documents=documents,
            costs=[m_service.get("fee")] if m_service.get("fee") else [],
            processing_time=m_service.get("delayTime") or None,
            contacts=contacts,
        )

        self._registry_state.update_services(
            self.provider_id,
            [
                ServiceSummary(
                    id=details.id,
                    title=details.title,
                    url=details.url,
                    provider_id=self.provider_id,
                    category_ids=details.category_ids,
                    excerpt=details.summary,
                )
            ],
            replace=False,
        )
        self._registry_state.set_service_details(self.provider_id, details)
        self._registry_state.upsert_selector_profile(
            self.provider_id,
            SelectorProfile(
                service_id=details.id,
                css_selectors={
                    "api": self._api_path(self._endpoints.service, service_id=service_id)
                },
            ),
        )
        self._search_index.rebuild()
        self._last_detail_source = "live"
        return details

    async def validate_service(self, service_id: str) -> ServiceDetails:
        details = await self.get_service_details(service_id, refresh=True)
        logger.info(
            "service_validated provider=%s service_id=%s title=%s",
            self.provider_id,
            service_id,
            details.title,
        )
        return details

    async def get_status(self) -> dict[str, object]:
        status = {
            "provider_id": self.provider_id,
            "base_url": str(self.settings.base_url),
            "concurrency": self.settings.concurrency,
            "cache_ttl": self.settings.cache_ttl_seconds,
        }
        if self._health_monitor:
            status["health"] = self._health_monitor.summary()
        return status

    @staticmethod
    def _slug_from_path(path: str) -> str:
        from unicodedata import normalize

        slug = path.rstrip("/").split("/")[-1]
        slug = normalize("NFKD", slug).encode("ascii", "ignore").decode("ascii")
        slug = slug.lower()
        slug = re.sub(r"[^a-z0-9\\-]+", "-", slug)
        slug = slug.strip("-")
        return slug or "service"

    @staticmethod
    def _slug_from_text(text: str) -> str:
        return ServicePublicBJProvider._slug_from_path(text.replace(" ", "-"))
