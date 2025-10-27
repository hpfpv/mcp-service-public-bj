"""Bootstrap helpers for provider registry and shared state."""

from __future__ import annotations

import asyncio
from pathlib import Path

from .config import Settings, get_settings
from .health import ScraperHealthMonitor
from .providers import ProviderRegistry, ProviderInitialisationError, ServicePublicBJProvider
from .registry import RegistryState, RegistryStore


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
            registry.register(provider)
        else:
            raise ProviderInitialisationError(f"Unknown provider id '{provider_id}' in configuration")

    await asyncio.gather(*(provider.initialise() for provider in registry.all()))
    return registry


async def shutdown_providers(registry: ProviderRegistry) -> None:
    await asyncio.gather(*(provider.shutdown() for provider in registry.all()))
