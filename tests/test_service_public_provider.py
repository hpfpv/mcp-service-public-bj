import json

import pytest

from server.config import Settings
from server.health import ScraperHealthMonitor
from server.providers.service_public_bj import ServicePublicBJProvider


class StubFetcher:
    def __init__(self, mapping):
        self.mapping = mapping

    async def fetch_text(self, url, *, use_cache=True):
        if url in self.mapping:
            return self.mapping[url]
        if not url.startswith("http"):
            absolute = f"https://example.com/{url.lstrip('/')}"
            if absolute in self.mapping:
                return self.mapping[absolute]
        raise AssertionError(f"Unexpected URL requested: {url}")

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_list_categories_uses_api(tmp_path):
    settings = Settings(cache_dir=tmp_path, base_url="https://example.com/")
    provider = ServicePublicBJProvider(settings)
    provider._fetcher = StubFetcher(
        {
            "https://example.com/api/portal/publicservices/?categories=true": json.dumps(
                {"services": [], "categories": ["", "Affaires", "Economie"]}
            )
        }
    )

    categories = await provider.list_categories()
    assert [c.id for c in categories] == ["affaires", "economie"]
    assert str(categories[0].url).endswith("/public/services?category=affaires")


@pytest.mark.asyncio
async def test_search_services_returns_results(tmp_path):
    settings = Settings(cache_dir=tmp_path, base_url="https://example.com/")
    provider = ServicePublicBJProvider(settings)
    provider._fetcher = StubFetcher(
        {
            "https://example.com/api/portal/publicservices/search?query=test": json.dumps(
                {
                    "services": [
                        {
                            "id": "PS0001",
                            "name": "Renouvellement carte",
                            "description": "Procédure de renouvellement",
                            "categories": ["Affaires", "Administration"],
                        }
                    ]
                }
            )
        }
    )

    results = await provider.search_services("test")
    assert results
    summary = results[0]
    assert summary.id == "PS0001"
    assert "renouvellement" in summary.title.lower()
    assert "affaires" in summary.category_ids
    assert str(summary.url).endswith("/public/services/service/PS0001")


@pytest.mark.asyncio
async def test_get_service_details_parses_payload(tmp_path):
    settings = Settings(cache_dir=tmp_path, base_url="https://example.com/")
    provider = ServicePublicBJProvider(settings)
    provider._fetcher = StubFetcher(
        {
            "https://example.com/api/portal/publicservices/PS0001": json.dumps(
                {
                    "id": "PS0001",
                    "name": "Renouvellement carte",
                    "overview": {
                        "description": "Résumé du service",
                        "thematicArea": ["Affaires"],
                        "Channelssp": ["En ligne"],
                        "ownedBy": {"name": "Agence X"},
                    },
                    "files": {
                        "forms": [
                            {"name": "Formulaire A", "url": "https://files/formA.pdf"}
                        ]
                    },
                    "mServiceForms": [
                        {"formfile": "extra.pdf", "formname": "Formulaire B"}
                    ],
                    "mService": {
                        "mActivationDate": "2024-01-01T00:00:00.000Z",
                        "mDocuments": "* Pièce d'identité\n* Justificatif",
                        "mProcess": "Étape 1\n\nÉtape 2",
                        "fee": "5000 FCFA",
                        "delayTime": "48h",
                    },
                }
            )
        }
    )

    details = await provider.get_service_details("PS0001")
    assert details.title == "Renouvellement carte"
    assert str(details.url).endswith("/public/services/service/PS0001")
    assert details.summary == "Résumé du service"
    assert details.documents and details.documents[0].title == "Formulaire A"
    assert details.requirements and details.requirements[0].title.startswith("Pièce")
    assert details.steps and details.steps[0].title == "Étape 1"
    assert details.costs == ["5000 FCFA"]
    assert any(contact.value == "Agence X" for contact in details.contacts)


@pytest.mark.asyncio
async def test_get_service_details_uses_cache(tmp_path):
    settings = Settings(cache_dir=tmp_path, base_url="https://example.com/")
    provider = ServicePublicBJProvider(settings)
    detail_url = "https://example.com/api/portal/publicservices/PS0001"
    payload = json.dumps(
        {
            "id": "PS0001",
            "name": "Renouvellement carte",
            "overview": {"description": "Résumé", "thematicArea": ["Affaires"]},
            "files": {"forms": []},
            "mServiceForms": [],
            "mService": {},
        }
    )
    provider._fetcher = StubFetcher({detail_url: payload})

    details = await provider.get_service_details("PS0001")
    assert details
    provider._fetcher.mapping.pop(detail_url, None)
    cached = await provider.get_service_details("PS0001")
    assert cached
    assert provider._last_detail_source == "cache"

    provider._fetcher.mapping[detail_url] = payload
    refreshed = await provider.get_service_details("PS0001", refresh=True)
    assert refreshed
    assert provider._last_detail_source == "live"


@pytest.mark.asyncio
async def test_search_services_respects_offset(tmp_path):
    settings = Settings(cache_dir=tmp_path, base_url="https://example.com/")
    provider = ServicePublicBJProvider(settings)
    search_url = "https://example.com/api/portal/publicservices/search?query=test"
    payload = json.dumps(
        {
            "services": [
                {
                    "id": f"PS{i:04d}",
                    "name": f"Service {i}",
                    "description": "desc",
                    "categories": ["Affaires"],
                }
                for i in range(20)
            ]
        }
    )
    provider._fetcher = StubFetcher({search_url: payload})

    first_batch = await provider.search_services("test", limit=5, offset=0)
    second_batch = await provider.search_services("test", limit=5, offset=5)
    assert first_batch[0].id == "PS0000"
    assert second_batch[0].id == "PS0005"


@pytest.mark.asyncio
async def test_search_services_without_limit_returns_all(tmp_path):
    settings = Settings(cache_dir=tmp_path, base_url="https://example.com/")
    provider = ServicePublicBJProvider(settings)
    search_url = "https://example.com/api/portal/publicservices/search?query=test"
    payload = json.dumps(
        {
            "services": [
                {
                    "id": f"PS{i:04d}",
                    "name": f"Service {i}",
                    "description": "desc",
                    "categories": ["Affaires"],
                }
                for i in range(15)
            ]
        }
    )
    provider._fetcher = StubFetcher({search_url: payload})

    results = await provider.search_services("test")
    assert len(results) == 15
    assert provider._last_search_total == 15
