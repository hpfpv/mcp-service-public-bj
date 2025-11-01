import httpx
import pytest
import respx

from server.config import Settings
from server.models import Category, ServiceDetails, ServiceSummary
from server.providers.finances_bj import FinancesBJProvider
from server.registry import RegistryState


def make_settings(tmp_path):
    return Settings(
        cache_dir=tmp_path / "registry",
    )


@pytest.mark.asyncio
async def test_list_categories_fetches_wordpress_taxonomy(tmp_path):
    settings = make_settings(tmp_path)
    registry_state = RegistryState()
    provider = FinancesBJProvider(settings, registry_state=registry_state)

    with respx.mock(base_url="https://finances.bj") as mock:
        mock.get(
            "/wp-json/wp/v2/type_service",
            params={"per_page": "100", "page": "1"},
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": 1, "name": "Types", "description": "", "link": "https://finances.test/type_service/types/", "parent": 0},
                    {"id": 2, "name": "Particulier", "description": "", "link": "https://finances.test/type_service/types/particulier/", "parent": 1},
                ],
            )
        )
        categories = await provider.list_categories()

    assert [category.name for category in categories] == ["Types", "Particulier"]
    catalog = registry_state.ensure_catalog(provider.provider_id)
    assert len(catalog.categories) == 2
    assert isinstance(categories[0], Category)
    await provider.shutdown()


@pytest.mark.asyncio
async def test_search_services_returns_summaries(tmp_path):
    settings = make_settings(tmp_path)
    provider = FinancesBJProvider(settings, registry_state=RegistryState())

    payload = [
        {
            "id": 101,
            "link": "https://finances.test/services/service-a/",
            "title": {"rendered": "Service A"},
            "content": {"rendered": "<p>Intro</p>"},
            "type_service": [2],
        },
        {
            "id": 102,
            "link": "https://finances.test/services/service-b/",
            "title": {"rendered": "Service B"},
            "content": {"rendered": "<p>Autre intro</p>"},
            "type_service": [3],
        },
    ]

    with respx.mock(base_url="https://finances.bj") as mock:
        route = mock.get("/wp-json/wp/v2/services").mock(
            return_value=httpx.Response(
                200,
                json=payload,
                headers={"X-WP-Total": "25", "X-WP-TotalPages": "3"},
            )
        )

        results = await provider.search_services("service", limit=2)

    assert isinstance(results[0], ServiceSummary)
    assert [summary.id for summary in results] == ["101", "102"]
    assert route.called
    query = route.calls[0].request.url
    assert "search=service" in str(query)
    assert provider._last_search_total == 25
    await provider.shutdown()


@pytest.mark.asyncio
async def test_get_service_details_parses_sections(tmp_path):
    settings = make_settings(tmp_path)
    provider = FinancesBJProvider(settings, registry_state=RegistryState())

    with respx.mock(base_url="https://finances.bj") as mock:
        mock.get("/wp-json/wp/v2/services/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 101,
                    "link": "https://finances.test/services/service-a/",
                    "title": {"rendered": "Service A"},
                    "type_service": [2],
                    "content": {
                        "rendered": """
                        <p><strong>Description</strong></p>
                        <p>Service pour les particuliers.</p>
                        <p><strong>Adresse</strong></p>
                        <p><a href="https://example.com">https://example.com</a></p>
                        <p><strong>Structure</strong></p>
                        <p>Direction des Finances</p>
                        """
                    },
                },
            )
        )

        details = await provider.get_service_details("101", refresh=True)

    assert isinstance(details, ServiceDetails)
    assert details.summary == "Service pour les particuliers."
    assert any(contact for contact in details.contacts if contact.label == "Structure")
    assert any(str(link.url) == "https://example.com/" for link in details.external_links)
    await provider.shutdown()
