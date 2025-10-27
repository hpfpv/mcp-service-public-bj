"""MCP server entrypoint for the service-public.bj integration."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict

from mcp import types
from mcp.server.lowlevel import server as lowlevel_server
from mcp.server.stdio import stdio_server

from .bootstrap import initialise_providers, load_registry_state, shutdown_providers
from .config import Settings, get_settings
from .health import ScraperHealthMonitor
from .providers import ProviderRegistry
from .registry import RegistryState
from .schemas import (
    GET_SERVICE_DETAILS_INPUT_SCHEMA,
    GET_SERVICE_DETAILS_OUTPUT_SCHEMA,
    LIST_CATEGORIES_INPUT_SCHEMA,
    LIST_CATEGORIES_OUTPUT_SCHEMA,
    SCRAPER_STATUS_INPUT_SCHEMA,
    SCRAPER_STATUS_OUTPUT_SCHEMA,
    SEARCH_SERVICES_INPUT_SCHEMA,
    SEARCH_SERVICES_OUTPUT_SCHEMA,
    VALIDATE_SERVICE_OUTPUT_SCHEMA,
)
from .tools import (
    get_scraper_status_tool,
    get_service_details_tool,
    list_categories_tool,
    search_services_tool,
    validate_service_tool,
)

logger = logging.getLogger(__name__)


async def _persist_registry(store_save: Callable[[], Awaitable[None]]) -> None:
    await store_save()


def _build_tool_definitions() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_categories",
            title="Lister les catégories",
            description="Renvoie la liste des catégories de services disponibles sur service-public.bj.",
            inputSchema=LIST_CATEGORIES_INPUT_SCHEMA,
            outputSchema=LIST_CATEGORIES_OUTPUT_SCHEMA,
        ),
        types.Tool(
            name="search_services",
            title="Recherche de services",
            description="Recherche des services correspondant à un mot-clé ou à une catégorie.",
            inputSchema=SEARCH_SERVICES_INPUT_SCHEMA,
            outputSchema=SEARCH_SERVICES_OUTPUT_SCHEMA,
        ),
        types.Tool(
            name="get_service_details",
            title="Détails d'un service",
            description="Récupère les informations détaillées d'un service spécifique.",
            inputSchema=GET_SERVICE_DETAILS_INPUT_SCHEMA,
            outputSchema=GET_SERVICE_DETAILS_OUTPUT_SCHEMA,
        ),
        types.Tool(
            name="validate_service",
            title="Valider un service",
            description="Force la récupération et la validation des informations d'un service.",
            inputSchema=GET_SERVICE_DETAILS_INPUT_SCHEMA,
            outputSchema=VALIDATE_SERVICE_OUTPUT_SCHEMA,
        ),
        types.Tool(
            name="get_scraper_status",
            title="Statut du scraper",
            description="Affiche l'état du scraper et les statistiques du registre local.",
            inputSchema=SCRAPER_STATUS_INPUT_SCHEMA,
            outputSchema=SCRAPER_STATUS_OUTPUT_SCHEMA,
        ),
    ]


async def _serve_stdio(settings: Settings) -> None:
    registry_state, registry_store = load_registry_state(settings)
    health_monitor = ScraperHealthMonitor()
    registry = await initialise_providers(settings, registry_state, health_monitor)

    async def persist_state() -> None:
        await asyncio.to_thread(registry_store.save, registry_state)

    tool_definitions = _build_tool_definitions()

    app = lowlevel_server.Server(
        name="mcp-service-public-bj",
        version="0.1.0",
        instructions=(
            "Ce serveur MCP fournit un accès en direct aux informations du site "
            "service-public.bj, y compris la recherche de services, les détails de procédures "
            "et l'état du scraper."
        ),
    )

    @app.list_tools()
    async def _list_tools(_: types.ListToolsRequest | None = None) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tool_definitions)

    async def handle_list_categories(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await list_categories_tool(
            registry,
            registry_state,
            provider_id=arguments.get("provider_id"),
            parent_id=arguments.get("parent_id"),
            refresh=bool(arguments.get("refresh", False)),
            persist_state=persist_state,
        )

    async def handle_search_services(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await search_services_tool(
            registry,
            registry_state,
            provider_id=arguments.get("provider_id"),
            query=arguments.get("query", ""),
            category_id=arguments.get("category_id"),
            limit=int(arguments.get("limit", 10)),
            offset=int(arguments.get("offset", 0)),
            refresh=bool(arguments.get("refresh", False)),
            persist_state=persist_state,
        )

    async def handle_get_details(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await get_service_details_tool(
            registry,
            registry_state,
            provider_id=arguments.get("provider_id"),
            service_id=arguments["service_id"],
            refresh=bool(arguments.get("refresh", False)),
            persist_state=persist_state,
        )

    async def handle_validate_service(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await validate_service_tool(
            registry,
            registry_state,
            provider_id=arguments.get("provider_id"),
            service_id=arguments["service_id"],
            persist_state=persist_state,
        )

    async def handle_get_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await get_scraper_status_tool(
            registry,
            registry_state,
            provider_id=arguments.get("provider_id"),
        )

    tool_handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = {
        "list_categories": handle_list_categories,
        "search_services": handle_search_services,
        "get_service_details": handle_get_details,
        "validate_service": handle_validate_service,
        "get_scraper_status": handle_get_status,
    }

    @app.call_tool()
    async def _call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        handler = tool_handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool '{tool_name}'")
        return await handler(arguments or {})

    initialization_options = app.create_initialization_options()

    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                initialization_options,
                raise_exceptions=False,
            )
    finally:
        await shutdown_providers(registry)
        await persist_state()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the MCP Service Public BJ server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio"],
        help="Transport to use for serving the MCP protocol.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    settings = get_settings()

    if args.transport != "stdio":
        raise SystemExit("Only stdio transport is currently supported.")

    asyncio.run(_serve_stdio(settings))


if __name__ == "__main__":  # pragma: no cover
    main()
