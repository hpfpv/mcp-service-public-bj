"""MCP server entrypoint for the service-public.bj integration."""

from __future__ import annotations

import argparse
import asyncio
import logging
from asyncio import Lock
from contextlib import asynccontextmanager, suppress
from typing import Any, Awaitable, Callable, Dict

import uvicorn
from mcp import types
from mcp.server.lowlevel import server as lowlevel_server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.server.stdio import stdio_server
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from .bootstrap import initialise_providers, load_registry_state, shutdown_providers
from .config import Settings, get_settings
from .health import ScraperHealthMonitor
from .providers import ProviderRegistry
from .registry import RegistryState, RegistryStore
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


class MCPServerRuntime:
    """Shared runtime objects for both stdio and SSE transports."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry_state: RegistryState,
        registry_store: RegistryStore,
        registry: ProviderRegistry,
    ) -> None:
        self.settings = settings
        self.registry_state = registry_state
        self._registry_store = registry_store
        self.registry = registry
        self._persist_lock = Lock()
        self._shutdown_lock = Lock()
        self._is_shutdown = False

        self._tool_definitions = _build_tool_definitions()
        self._app = self._build_low_level_app()
        self._initialization_options = self._app.create_initialization_options()

    @classmethod
    async def create(cls, settings: Settings) -> "MCPServerRuntime":
        registry_state, registry_store = load_registry_state(settings)
        health_monitor = ScraperHealthMonitor()
        registry = await initialise_providers(settings, registry_state, health_monitor)
        return cls(
            settings=settings,
            registry_state=registry_state,
            registry_store=registry_store,
            registry=registry,
        )

    def _build_low_level_app(self) -> lowlevel_server.Server:
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
            return types.ListToolsResult(tools=self._tool_definitions)

        async def handle_list_categories(arguments: Dict[str, Any]) -> Dict[str, Any]:
            return await list_categories_tool(
                self.registry,
                self.registry_state,
                provider_id=arguments.get("provider_id"),
                parent_id=arguments.get("parent_id"),
                refresh=bool(arguments.get("refresh", False)),
                persist_state=self.persist_state,
            )

        async def handle_search_services(arguments: Dict[str, Any]) -> Dict[str, Any]:
            return await search_services_tool(
                self.registry,
                self.registry_state,
                provider_id=arguments.get("provider_id"),
                query=arguments.get("query", ""),
                category_id=arguments.get("category_id"),
                limit=int(arguments.get("limit", 10)),
                offset=int(arguments.get("offset", 0)),
                refresh=bool(arguments.get("refresh", False)),
                persist_state=self.persist_state,
            )

        async def handle_get_details(arguments: Dict[str, Any]) -> Dict[str, Any]:
            return await get_service_details_tool(
                self.registry,
                self.registry_state,
                provider_id=arguments.get("provider_id"),
                service_id=arguments["service_id"],
                refresh=bool(arguments.get("refresh", False)),
                persist_state=self.persist_state,
            )

        async def handle_validate_service(arguments: Dict[str, Any]) -> Dict[str, Any]:
            return await validate_service_tool(
                self.registry,
                self.registry_state,
                provider_id=arguments.get("provider_id"),
                service_id=arguments["service_id"],
                persist_state=self.persist_state,
            )

        async def handle_get_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
            return await get_scraper_status_tool(
                self.registry,
                self.registry_state,
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

        return app

    async def persist_state(self) -> None:
        async with self._persist_lock:
            await asyncio.to_thread(self._registry_store.save, self.registry_state)

    async def run_session(self, read_stream: Any, write_stream: Any) -> None:
        await self._app.run(
            read_stream,
            write_stream,
            self._initialization_options,
            raise_exceptions=False,
        )

    async def shutdown(self) -> None:
        async with self._shutdown_lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True
            await shutdown_providers(self.registry)
            await self.persist_state()


async def serve_stdio(settings: Settings) -> None:
    runtime = await MCPServerRuntime.create(settings)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await runtime.run_session(read_stream, write_stream)
    finally:
        await runtime.shutdown()


async def serve_http(
    settings: Settings,
    *,
    host: str,
    port: int,
    log_level: str,
    json_response: bool = False,
) -> None:
    runtime = await MCPServerRuntime.create(settings)
    transport = StreamableHTTPServerTransport(
        mcp_session_id=None,
        is_json_response_enabled=json_response,
    )

    @asynccontextmanager
    async def lifespan(_app):
        async with transport.connect() as (read_stream, write_stream):
            session_task = asyncio.create_task(runtime.run_session(read_stream, write_stream))
            try:
                yield
            finally:
                session_task.cancel()
                with suppress(asyncio.CancelledError):
                    await session_task

    async def health_endpoint(_request) -> JSONResponse:
        registry_metadata = {
            provider_id: {
                "categories": len(catalog.categories),
                "services": len(catalog.services),
            }
            for provider_id, catalog in runtime.registry_state.catalogs.items()
        }
        return JSONResponse(
            {
                "status": "ok",
                "providers": list(runtime.registry_state.catalogs.keys()),
                "registry": registry_metadata,
            }
        )

    routes = [
        Route("/healthz", endpoint=health_endpoint, methods=["GET"]),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)

    async def transport_app(scope, receive, send):
        await transport.handle_request(scope, receive, send)

    app.mount("/mcp", transport_app)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    try:
        logger.info("Starting streamable HTTP server on %s:%s", host, port)
        await server.serve()
    finally:
        await transport.terminate()
        await runtime.shutdown()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the MCP Service Public BJ server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http"],
        help="Transport to use for serving the MCP protocol.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host/IP to bind when using the HTTP transport.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind when using the HTTP transport.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    parser.add_argument(
        "--http-json-response",
        action="store_true",
        help="Return JSON responses when using the HTTP transport (default is streaming).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    settings = get_settings()

    if args.transport == "stdio":
        asyncio.run(serve_stdio(settings))
        return

    asyncio.run(
        serve_http(
            settings,
            host=args.host,
            port=args.port,
            log_level=args.log_level,
            json_response=args.http_json_response,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    main()
