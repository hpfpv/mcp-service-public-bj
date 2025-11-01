"""Provider abstraction for live scraping sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings

if False:  # pragma: no cover
    pass

try:
    from typing import TYPE_CHECKING
except ImportError:  # pragma: no cover
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from ..models import Category, ServiceDetails, ServiceSummary


class ProviderError(Exception):
    """Base exception raised for provider-specific failures."""


class ProviderInitialisationError(ProviderError):
    """Raised when a provider cannot initialise correctly."""


@dataclass(frozen=True)
class ProviderDescriptor:
    """Metadata describing a provider for discovery and routing."""

    id: str
    name: str
    description: str
    priority: int = 0
    coverage_tags: tuple[str, ...] = field(default_factory=tuple)
    supported_tools: tuple[str, ...] = field(default_factory=tuple)


class BaseProvider(ABC):
    """Abstract base class defining the provider interface."""

    provider_id: str
    display_name: str

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        """Return application settings."""

        return self._settings

    @abstractmethod
    async def initialise(self) -> None:
        """Perform any asynchronous setup required before serving requests."""

    @abstractmethod
    async def list_categories(
        self, parent_id: str | None = None, *, refresh: bool = False
    ) -> Sequence[Category]:
        """Return categories discovered by the provider."""

    @abstractmethod
    async def search_services(
        self,
        query: str,
        *,
        category_id: str | None = None,
        limit: int = 10,
        offset: int = 0,
        refresh: bool = False,
    ) -> Sequence[ServiceSummary]:
        """Search services matching the query."""

    @abstractmethod
    async def get_service_details(
        self, service_id: str, *, refresh: bool = False
    ) -> ServiceDetails:
        """Return full details for a service."""

    async def validate_service(self, service_id: str) -> ServiceDetails:
        """Optional hook to force-refresh and validate a service."""

        return await self.get_service_details(service_id, refresh=True)

    async def get_status(self) -> dict[str, Any]:
        """Return provider status information."""

        return {
            "provider_id": self.provider_id,
        }

    async def shutdown(self) -> None:
        """Hook invoked during application shutdown to release resources."""

        return None


class ProviderRegistry:
    """In-memory registry of provider instances keyed by identifier."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._descriptors: dict[str, ProviderDescriptor] = {}

    def register(self, provider: BaseProvider, descriptor: ProviderDescriptor) -> None:
        if provider.provider_id in self._providers:
            raise ProviderInitialisationError(
                f"Provider '{provider.provider_id}' already registered."
            )
        if descriptor.id != provider.provider_id:
            raise ProviderInitialisationError(
                f"Descriptor id '{descriptor.id}' does not match provider id '{provider.provider_id}'."
            )
        self._providers[provider.provider_id] = provider
        self._descriptors[provider.provider_id] = descriptor

    def get(self, provider_id: str) -> BaseProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:  # pragma: no cover - defensive path
            raise ProviderError(f"Provider '{provider_id}' not registered.") from exc

    def get_descriptor(self, provider_id: str) -> ProviderDescriptor:
        try:
            return self._descriptors[provider_id]
        except KeyError as exc:  # pragma: no cover - defensive path
            raise ProviderError(f"Provider '{provider_id}' descriptor missing.") from exc

    def all(self) -> Iterable[BaseProvider]:
        return self._providers.values()

    def descriptors(self) -> Iterable[ProviderDescriptor]:
        return self._descriptors.values()

    def ordered_descriptors(self) -> list[ProviderDescriptor]:
        return sorted(
            self._descriptors.values(),
            key=lambda descriptor: descriptor.priority,
            reverse=True,
        )

    def clear(self) -> None:
        self._providers.clear()
        self._descriptors.clear()
