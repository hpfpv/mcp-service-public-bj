"""Service search index derived from the registry."""

from __future__ import annotations

import re
from typing import Dict, List

from rapidfuzz import fuzz

from .models import ServiceSummary
from .registry import RegistryState
from .selectors import normalise_whitespace

TOKEN_PATTERN = re.compile(r"[^\w]+", re.UNICODE)


def _tokenise(text: str) -> List[str]:
    cleaned = TOKEN_PATTERN.sub(" ", normalise_whitespace(text).lower())
    return [token for token in cleaned.split(" ") if token]


class ServiceSearchIndex:
    """Lightweight inverted index with fuzzy scoring fallback."""

    def __init__(self, registry: RegistryState, provider_id: str) -> None:
        self._registry = registry
        self._provider_id = provider_id
        self._index: Dict[str, set[str]] = {}
        self.rebuild()

    def rebuild(self) -> None:
        catalog = self._registry.ensure_catalog(self._provider_id)
        self._index.clear()
        for service in catalog.services.values():
            tokens = set(_tokenise(service.title))
            if service.excerpt:
                tokens.update(_tokenise(service.excerpt))
            for token in tokens:
                self._index.setdefault(token, set()).add(service.id)

    def search(self, query: str, limit: int = 10) -> List[ServiceSummary]:
        if not query.strip():
            return []

        catalog = self._registry.ensure_catalog(self._provider_id)
        tokens = _tokenise(query)
        candidates: Dict[str, int] = {}
        for token in tokens:
            for service_id in self._index.get(token, set()):
                candidates[service_id] = candidates.get(service_id, 0) + 1

        scored: List[tuple[float, ServiceSummary]] = []
        if candidates:
            for service_id, count in candidates.items():
                service = catalog.services.get(service_id)
                if not service:
                    continue
                fuzzy = fuzz.partial_ratio(query.lower(), service.title.lower())
                score = count * 10 + fuzzy
                scored.append((score, service))
        else:
            for service in catalog.services.values():
                fuzzy = fuzz.partial_ratio(query.lower(), service.title.lower())
                if fuzzy >= 40:
                    scored.append((float(fuzzy), service))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: List[ServiceSummary] = []
        seen = set()
        for score, service in scored:
            if service.id in seen:
                continue
            seen.add(service.id)
            results.append(service.model_copy(update={"score": float(score)}))
            if len(results) >= limit:
                break
        return results
