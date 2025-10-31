
from server.models import Category, ServiceSummary
from server.registry import RegistryState, RegistryStore, SelectorProfile


def test_registry_updates_and_persistence(tmp_path):
    state = RegistryState()
    categories = [
        Category(id="root", name="Root", url="https://example.com/root", provider_id="p"),
        Category(
            id="child",
            name="Child",
            url="https://example.com/child",
            provider_id="p",
            parent_id="root",
        ),
    ]
    services = [
        ServiceSummary(
            id="svc",
            title="Service",
            url="https://example.com/svc",
            provider_id="p",
            category_ids=["child"],
        )
    ]

    state.update_categories("p", categories)
    state.update_services("p", services)
    state.upsert_selector_profile(
        "p",
        SelectorProfile(service_id="svc", css_selectors={"title": "h1"}),
    )

    children = state.categories_for_parent("p", "root")
    assert [child.id for child in children] == ["child"]

    breadcrumb = state.breadcrumb("p", "child")
    assert [cat.id for cat in breadcrumb] == ["root", "child"]

    svc_list = state.services_for_category("p", "child")
    assert svc_list[0].id == "svc"

    store = RegistryStore(tmp_path / "registry.json")
    store.save(state)
    loaded = store.load()
    assert loaded is not None
    assert "svc" in loaded.ensure_catalog("p").services
