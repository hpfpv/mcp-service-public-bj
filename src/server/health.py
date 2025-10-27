"""Scraper health monitoring utilities."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FetchRecord:
    """Represents a single fetch event."""

    duration_ms: float
    success: bool
    timestamp: float
    provider_id: str
    cache_hit: bool = False
    error_message: str | None = None


class ScraperHealthMonitor:
    """Collects lightweight health metrics for live fetch operations."""

    def __init__(self, max_records: int = 1000) -> None:
        self._max_records = max_records
        self._records: List[FetchRecord] = []
        self._cache_hits = 0
        self._cache_misses = 0

    def record_fetch(
        self,
        *,
        provider_id: str,
        duration_ms: float,
        success: bool,
        cache_hit: bool = False,
        error_message: str | None = None,
    ) -> None:
        record = FetchRecord(
            provider_id=provider_id,
            duration_ms=duration_ms,
            success=success,
            cache_hit=cache_hit,
            error_message=error_message,
            timestamp=time.time(),
        )
        self._records.append(record)
        if cache_hit:
            self._cache_hits += 1
        else:
            self._cache_misses += 1

        if len(self._records) > self._max_records:
            excess = len(self._records) - self._max_records
            dropped = self._records[:excess]
            self._records = self._records[excess:]
            for item in dropped:
                if item.cache_hit:
                    self._cache_hits -= 1
                else:
                    self._cache_misses -= 1

    def cache_hit_ratio(self) -> float:
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return self._cache_hits / total

    def summary(self) -> Dict[str, object]:
        if not self._records:
            return {
                "recent_fetches": 0,
                "avg_duration_ms": 0.0,
                "success_rate": 1.0,
                "cache_hit_ratio": self.cache_hit_ratio(),
            }

        durations = [record.duration_ms for record in self._records]
        successes = sum(1 for record in self._records if record.success)
        errors = [record.error_message for record in self._records if record.error_message]
        provider_counts: Dict[str, int] = {}
        for record in self._records:
            provider_counts[record.provider_id] = provider_counts.get(record.provider_id, 0) + 1

        return {
            "recent_fetches": len(self._records),
            "avg_duration_ms": sum(durations) / len(durations),
            "success_rate": successes / len(self._records),
            "cache_hit_ratio": self.cache_hit_ratio(),
            "recent_errors": errors[-5:],  # limit to last few messages
            "requests_by_provider": provider_counts,
        }
