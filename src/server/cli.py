"""Command-line interface for the MCP Service Public BJ project."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Iterable, Optional

from .bootstrap import initialise_providers, load_registry_state, shutdown_providers
from .config import Settings, get_settings
from .health import ScraperHealthMonitor
from .main import serve_stdio


async def _scrape_async(
    settings: Settings,
    *,
    provider_id: str | None,
    query: str | None,
    service_id: str | None,
    limit: int,
) -> None:
    state, store = load_registry_state(settings)
    monitor = ScraperHealthMonitor()
    registry = await initialise_providers(settings, state, monitor)

    try:
        providers = list(registry.all())
        if provider_id:
            providers = [registry.get(provider_id)]

        for provider in providers:
            print(f"→ Provider: {provider.provider_id}")

            categories = await provider.list_categories(refresh=True)
            print(f"   Categories refreshed: {len(categories)}")

            if query:
                results = await provider.search_services(
                    query, limit=limit, offset=0, refresh=True
                )
                print(f"   Search '{query}': {len(results)} result(s) (limit={limit})")
                for hit in results:
                    print(f"      - {hit.id}: {hit.title}")

            if service_id:
                details = await provider.get_service_details(service_id, refresh=True)
                print(f"   Service '{service_id}': {details.title}")

            await asyncio.to_thread(store.save, state)
    finally:
        await shutdown_providers(registry)


async def _status_async(
    settings: Settings,
    *,
    provider_id: str | None,
    live: bool,
) -> None:
    state, _ = load_registry_state(settings)

    catalog_items: Iterable[str] = list(state.catalogs.keys())
    target_ids: Iterable[str]
    if provider_id:
        target_ids = [provider_id]
    else:
        target_ids = catalog_items or []

    if live:
        monitor = ScraperHealthMonitor()
        registry = await initialise_providers(settings, state, monitor)
        try:
            providers = list(registry.all())
            if provider_id:
                providers = [registry.get(provider_id)]

            for provider in providers:
                status = await provider.get_status()
                catalog = state.ensure_catalog(provider.provider_id)
                print(f"→ Provider: {provider.provider_id}")
                print(f"   Categories indexed: {len(catalog.categories)}")
                print(f"   Services indexed: {len(catalog.services)}")
                print(f"   Status: {status}")
        finally:
            await shutdown_providers(registry)
    else:
        if not target_ids:
            print("No cached provider data. Use --live to fetch status.")
            return
        for pid in target_ids:
            catalog = state.ensure_catalog(pid)
            print(f"→ Provider: {pid}")
            print(f"   Categories indexed: {len(catalog.categories)}")
            print(f"   Services indexed: {len(catalog.services)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI helpers for the MCP Service Public BJ project",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the MCP server over stdio")
    serve_parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    scrape_parser = subparsers.add_parser(
        "scrape", help="Refresh cached data or collect specific resources"
    )
    scrape_parser.add_argument("--provider", help="Limit to a specific provider id")
    scrape_parser.add_argument("--query", help="Run a live search query")
    scrape_parser.add_argument("--service-id", help="Refresh details for a given service id")
    scrape_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results to fetch for --query (default: 10)",
    )

    status_parser = subparsers.add_parser(
        "status", help="Display registry and provider status information"
    )
    status_parser.add_argument("--provider", help="Limit to a specific provider id")
    status_parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch live status from providers (may hit the network)",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "serve":
        import logging

        logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
        asyncio.run(serve_stdio(settings))
        return 0

    if args.command == "scrape":
        asyncio.run(
            _scrape_async(
                settings,
                provider_id=args.provider,
                query=args.query,
                service_id=args.service_id,
                limit=args.limit,
            )
        )
        return 0

    if args.command == "status":
        asyncio.run(
            _status_async(
                settings,
                provider_id=args.provider,
                live=args.live,
            )
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
