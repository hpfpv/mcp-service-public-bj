"""Shared registry for categories, services, and selector profiles."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Sequence

from .models import Category, ServiceDetails, ServiceSummary


@dataclass
class SelectorProfile:
    """Describes the selectors used to parse a given service or category."""

    service_id: str
    css_selectors: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class ProviderCatalog:
    """Catalog of data for a single provider."""

    provider_id: str
    categories: Dict[str, Category] = field(default_factory=dict)
    services: Dict[str, ServiceSummary] = field(default_factory=dict)
    service_details: Dict[str, ServiceDetails] = field(default_factory=dict)
    selector_profiles: Dict[str, SelectorProfile] = field(default_factory=dict)
    category_children: MutableMapping[str | None, List[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    services_by_category: MutableMapping[str, List[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def update_categories(self, categories: Sequence[Category], *, replace: bool = True) -> None:
        if replace:
            self.categories.clear()
        for category in categories:
            self.categories[category.id] = category
        self.category_children.clear()
        for category in self.categories.values():
            self.category_children[category.parent_id].append(category.id)

    def update_services(
        self, services: Sequence[ServiceSummary], *, replace: bool = False
    ) -> None:
        if replace:
            self.services.clear()
            self.service_details = {
                sid: detail
                for sid, detail in self.service_details.items()
                if sid in {service.id for service in services}
            }
        for service in services:
            self.services[service.id] = service
        self.services_by_category.clear()
        for service in self.services.values():
            for category_id in service.category_ids:
                self.services_by_category[category_id].append(service.id)

    def set_service_details(self, detail: ServiceDetails) -> None:
        self.service_details[detail.id] = detail

    def get_service_details(self, service_id: str) -> ServiceDetails | None:
        return self.service_details.get(service_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "categories": [
                category.model_dump(mode="json") for category in self.categories.values()
            ],
            "services": [
                service.model_dump(mode="json") for service in self.services.values()
            ],
            "service_details": [
                detail.model_dump(mode="json")
                for detail in self.service_details.values()
            ],
            "selector_profiles": [
                {
                    "service_id": profile.service_id,
                    "css_selectors": profile.css_selectors,
                    "metadata": profile.metadata,
                }
                for profile in self.selector_profiles.values()
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ProviderCatalog":
        provider_id = str(payload.get("provider_id"))
        instance = cls(provider_id=provider_id)
        categories_payload = payload.get("categories", []) or []
        services_payload = payload.get("services", []) or []
        details_payload = payload.get("service_details", []) or []
        selector_payload = payload.get("selector_profiles", []) or []

        categories = [Category.model_validate(item) for item in categories_payload]
        services = [ServiceSummary.model_validate(item) for item in services_payload]
        instance.update_categories(categories)
        instance.update_services(services)

        details = [ServiceDetails.model_validate(item) for item in details_payload]
        for detail in details:
            instance.service_details[detail.id] = detail

        profiles = {}
        for item in selector_payload:
            service_id = str(item.get("service_id"))
            profiles[service_id] = SelectorProfile(
                service_id=service_id,
                css_selectors=dict(item.get("css_selectors", {})),
                metadata=dict(item.get("metadata", {})),
            )
        instance.selector_profiles = profiles
        return instance


class RegistryState:
    """Container for all provider catalogs."""

    def __init__(self) -> None:
        self.catalogs: Dict[str, ProviderCatalog] = {}

    def ensure_catalog(self, provider_id: str) -> ProviderCatalog:
        if provider_id not in self.catalogs:
            self.catalogs[provider_id] = ProviderCatalog(provider_id=provider_id)
        return self.catalogs[provider_id]

    def update_categories(
        self, provider_id: str, categories: Sequence[Category], *, replace: bool = True
    ) -> None:
        catalog = self.ensure_catalog(provider_id)
        catalog.update_categories(categories, replace=replace)

    def update_services(
        self, provider_id: str, services: Sequence[ServiceSummary], *, replace: bool = False
    ) -> None:
        catalog = self.ensure_catalog(provider_id)
        catalog.update_services(services, replace=replace)

    def upsert_selector_profile(self, provider_id: str, profile: SelectorProfile) -> None:
        catalog = self.ensure_catalog(provider_id)
        catalog.selector_profiles[profile.service_id] = profile

    def set_service_details(self, provider_id: str, detail: ServiceDetails) -> None:
        catalog = self.ensure_catalog(provider_id)
        catalog.set_service_details(detail)

    def get_service_details(self, provider_id: str, service_id: str) -> ServiceDetails | None:
        catalog = self.ensure_catalog(provider_id)
        return catalog.get_service_details(service_id)

    def categories_for_parent(self, provider_id: str, parent_id: str | None) -> List[Category]:
        catalog = self.ensure_catalog(provider_id)
        category_ids = catalog.category_children.get(parent_id, [])
        return [catalog.categories[cid] for cid in category_ids if cid in catalog.categories]

    def breadcrumb(self, provider_id: str, category_id: str) -> List[Category]:
        catalog = self.ensure_catalog(provider_id)
        path: List[Category] = []
        current_id: str | None = category_id
        visited = set()
        while current_id:
            if current_id in visited:
                break  # avoid cycles
            visited.add(current_id)
            category = catalog.categories.get(current_id)
            if not category:
                break
            path.append(category)
            current_id = category.parent_id
        return list(reversed(path))

    def services_for_category(self, provider_id: str, category_id: str) -> List[ServiceSummary]:
        catalog = self.ensure_catalog(provider_id)
        service_ids = catalog.services_by_category.get(category_id, [])
        return [catalog.services[sid] for sid in service_ids if sid in catalog.services]

    def to_dict(self) -> dict[str, object]:
        return {
            "providers": [catalog.to_dict() for catalog in self.catalogs.values()],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RegistryState":
        instance = cls()
        provider_payloads = payload.get("providers", []) or []
        for provider_payload in provider_payloads:
            catalog = ProviderCatalog.from_dict(provider_payload)
            instance.catalogs[catalog.provider_id] = catalog
        return instance


class RegistryStore:
    """Load/store registry snapshots from JSON files."""

    def __init__(self, snapshot_path: Path) -> None:
        self._path = snapshot_path

    def load(self) -> RegistryState | None:
        if not self._path.exists():
            return None
        with self._path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return RegistryState.from_dict(payload)

    def save(self, state: RegistryState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2)
