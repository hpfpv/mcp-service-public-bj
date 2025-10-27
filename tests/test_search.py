from server.models import ServiceSummary
from server.registry import RegistryState
from server.search import ServiceSearchIndex


def test_search_returns_ranked_results():
    state = RegistryState()
    services = [
        ServiceSummary(
            id="svc-1",
            title="Demande de carte d'identité",
            url="https://example.com/service1",
            provider_id="p",
            category_ids=["id"],
            excerpt="Carte d'identité nationale",
        ),
        ServiceSummary(
            id="svc-2",
            title="Renouvellement de passeport",
            url="https://example.com/service2",
            provider_id="p",
            category_ids=["passport"],
        ),
    ]
    state.update_services("p", services, replace=True)
    index = ServiceSearchIndex(state, "p")

    results = index.search("carte identite")
    assert results
    assert results[0].id == "svc-1"
    assert results[0].score is not None

    # ensure fuzzy fallback works
    fuzzy_results = index.search("passeport")
    assert any(result.id == "svc-2" for result in fuzzy_results)
