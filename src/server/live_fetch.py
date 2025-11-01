"""Live fetch client with optional caching and health monitoring."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urljoin

import httpx
from aiocache import Cache  # type: ignore[import-untyped]

from .config import Settings
from .health import ScraperHealthMonitor
from .metrics import record_fetch


class LiveFetchClient:
    """Handles HTTP requests with caching, concurrency limits, and metrics."""

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str,
        provider_id: str,
        monitor: ScraperHealthMonitor | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = base_url.rstrip("/") + "/"
        self._provider_id = provider_id
        self._monitor = monitor
        self._semaphore = asyncio.Semaphore(settings.concurrency)
        self._client = httpx.AsyncClient(
            timeout=settings.timeout_seconds,
            headers={"User-Agent": settings.user_agent},
        )
        self._cache: Cache | None = None
        if settings.cache_ttl_seconds > 0:
            self._cache = Cache(Cache.MEMORY, ttl=settings.cache_ttl_seconds)

    async def close(self) -> None:
        """Close underlying HTTP client and cache."""

        await self._client.aclose()
        if self._cache:
            await self._cache.close()

    def _absolute_url(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return urljoin(self._base_url, url)

    async def fetch_text(self, url: str, *, use_cache: bool = True) -> str:
        """Fetch the URL and return response text."""

        absolute_url = self._absolute_url(url)
        cache_hit = False

        if use_cache and self._cache:
            cached = await self._cache.get(absolute_url)
            if cached is not None:
                cache_hit = True
                text = cached
                record_fetch(
                    provider=self._provider_id,
                    cache_hit=True,
                    outcome="success",
                    duration_seconds=0.0,
                )
                if self._monitor:
                    self._monitor.record_fetch(
                        provider_id=self._provider_id,
                        duration_ms=0.0,
                        success=True,
                        cache_hit=True,
                    )
                return text

        start = time.perf_counter()
        try:
            async with self._semaphore:
                response = await self._client.get(absolute_url)
                response.raise_for_status()
                text = response.text
        except Exception as exc:  # pragma: no cover - network errors
            record_fetch(
                provider=self._provider_id,
                cache_hit=cache_hit,
                outcome="error",
                duration_seconds=time.perf_counter() - start,
            )
            if self._monitor:
                duration_ms = (time.perf_counter() - start) * 1000
                self._monitor.record_fetch(
                    provider_id=self._provider_id,
                    duration_ms=duration_ms,
                    success=False,
                    cache_hit=cache_hit,
                    error_message=str(exc),
                )
            raise
        else:
            if use_cache and self._cache:
                await self._cache.set(absolute_url, text)
            duration_seconds = time.perf_counter() - start
            record_fetch(
                provider=self._provider_id,
                cache_hit=cache_hit,
                outcome="success",
                duration_seconds=duration_seconds,
            )
            if self._monitor:
                duration_ms = duration_seconds * 1000
                self._monitor.record_fetch(
                    provider_id=self._provider_id,
                    duration_ms=duration_ms,
                    success=True,
                    cache_hit=cache_hit,
                )
            return text

    async def fetch_response(self, url: str, *, use_cache: bool = False) -> httpx.Response:
        """Fetch the URL and return the full HTTP response object."""

        absolute_url = self._absolute_url(url)
        start = time.perf_counter()
        try:
            async with self._semaphore:
                response = await self._client.get(absolute_url)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network errors
            record_fetch(
                provider=self._provider_id,
                cache_hit=False,
                outcome="error",
                duration_seconds=time.perf_counter() - start,
            )
            if self._monitor:
                duration_ms = (time.perf_counter() - start) * 1000
                self._monitor.record_fetch(
                    provider_id=self._provider_id,
                    duration_ms=duration_ms,
                    success=False,
                    cache_hit=False,
                    error_message=str(exc),
                )
            raise
        else:
            duration_seconds = time.perf_counter() - start
            record_fetch(
                provider=self._provider_id,
                cache_hit=False,
                outcome="success",
                duration_seconds=duration_seconds,
            )
            if self._monitor:
                duration_ms = duration_seconds * 1000
                self._monitor.record_fetch(
                    provider_id=self._provider_id,
                    duration_ms=duration_ms,
                    success=True,
                    cache_hit=False,
                )
            if use_cache and self._cache:
                await self._cache.set(absolute_url, response.text)
            return response
