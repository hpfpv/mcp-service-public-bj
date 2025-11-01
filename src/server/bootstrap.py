"""Bootstrap helpers for provider registry and shared state."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .config import Settings
from .health import ScraperHealthMonitor
from .providers import (
    FinancesBJProvider,
    ProviderDescriptor,
    ProviderInitialisationError,
    ProviderRegistry,
    ServicePublicBJProvider,
)
from .registry import RegistryState, RegistryStore

logger = logging.getLogger(__name__)


def load_registry_state(settings: Settings) -> tuple[RegistryState, RegistryStore]:
    """Load registry state from disk or initialise a fresh one."""

    snapshot_path = Path(settings.cache_dir) / "registry.json"
    store = RegistryStore(snapshot_path)
    state = store.load() or RegistryState()
    return state, store


async def initialise_providers(
    settings: Settings,
    registry_state: RegistryState,
    health_monitor: ScraperHealthMonitor,
) -> ProviderRegistry:
    registry = ProviderRegistry()

    for provider_id in settings.enabled_providers:
        if provider_id == ServicePublicBJProvider.provider_id:
            provider = ServicePublicBJProvider(
                settings,
                registry_state=registry_state,
                health_monitor=health_monitor,
            )
            descriptor = ProviderDescriptor(
                id=provider.provider_id,
                name="Service Public BJ",
                description="Portail officiel service-public.bj pour les demarches administratives.",
                priority=settings.provider_priorities.get(provider.provider_id, 100),
                coverage_tags=(
                    "administration",
                    "etatcivil",
                    "identite",
                    "passeport",
                    "famille",
                    "naissance",
                    "autorisations",
                    "sejour",
                    "visa",
                    "certificat",
                    "etat",
                    "travail",
                    "education",
                    "sante",
                    "sport",
                    "logement",
                    "justice",
                    "transport",
                    "urbanisme",
                    "environnement",
                    "culture",
                    "social",
                ),
                supported_tools=(
                    "list_categories",
                    "search_services",
                    "get_service_details",
                    "validate_service",
                    "get_scraper_status",
                ),
            )
        elif provider_id == FinancesBJProvider.provider_id:
            provider = FinancesBJProvider(
                settings,
                registry_state=registry_state,
                health_monitor=health_monitor,
            )
            descriptor = ProviderDescriptor(
                id=provider.provider_id,
                name="Finances BJ",
                description="Services numeriques du Ministere de l'Economie et des Finances (IFU, impots, foncier, entreprises).",
                priority=settings.provider_priorities.get(provider.provider_id, 80),
                coverage_tags=(
                    "finances",
                    "impots",
                    "taxes",
                    "tva",
                    "ifu",
                    "entreprise",
                    "comptabilite",
                    "banque",
                    "budget",
                    "tresor",
                    "change",
                    "credit",
                    "emprunt",
                    "remboursement",
                    "douane",
                    "commerce",
                    "investissement",
                    "foncier",
                    "cadastre",
                    "titrefoncier",
                    "marchepublic",
                    "retraite",
                ),
                supported_tools=(
                    "list_categories",
                    "search_services",
                    "get_service_details",
                    "validate_service",
                    "get_scraper_status",
                ),
            )
        else:
            raise ProviderInitialisationError(f"Unknown provider id '{provider_id}' in configuration")
        registry.register(provider, descriptor)

    await asyncio.gather(*(provider.initialise() for provider in registry.all()))
    return registry


async def shutdown_providers(registry: ProviderRegistry) -> None:
    tasks = [provider.shutdown() for provider in registry.all()]
    if not tasks:
        return
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, asyncio.CancelledError):
            logger.debug("Provider shutdown cancelled; ignoring.")
            continue
        if isinstance(result, Exception):
            logger.warning("Provider shutdown raised an exception: %s", result, exc_info=result)
