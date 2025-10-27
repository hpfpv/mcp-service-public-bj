import asyncio

import pytest

from server import cli


def test_cli_serve_dispatch(monkeypatch):
    called = {}

    def fake_get_settings():
        return "settings"

    async def fake_serve(settings):
        called["settings"] = settings

    monkeypatch.setattr(cli, "get_settings", fake_get_settings)
    monkeypatch.setattr(cli, "serve_stdio", fake_serve)

    exit_code = cli.main(["serve"])

    assert exit_code == 0
    assert called["settings"] == "settings"


def test_cli_scrape_dispatch(monkeypatch):
    called = {}

    def fake_get_settings():
        return "settings"

    async def fake_scrape(settings, *, provider_id, query, service_id, limit):
        called["params"] = {
            "settings": settings,
            "provider_id": provider_id,
            "query": query,
            "service_id": service_id,
            "limit": limit,
        }

    monkeypatch.setattr(cli, "get_settings", fake_get_settings)
    monkeypatch.setattr(cli, "_scrape_async", fake_scrape)

    exit_code = cli.main(["scrape", "--query", "test", "--limit", "5"])

    assert exit_code == 0
    assert called["params"] == {
        "settings": "settings",
        "provider_id": None,
        "query": "test",
        "service_id": None,
        "limit": 5,
    }


def test_cli_status_dispatch(monkeypatch):
    called = {}

    def fake_get_settings():
        return "settings"

    async def fake_status(settings, *, provider_id, live):
        called["params"] = {
            "settings": settings,
            "provider_id": provider_id,
            "live": live,
        }

    monkeypatch.setattr(cli, "get_settings", fake_get_settings)
    monkeypatch.setattr(cli, "_status_async", fake_status)

    exit_code = cli.main(["status", "--live", "--provider", "service-public-bj"])

    assert exit_code == 0
    assert called["params"] == {
        "settings": "settings",
        "provider_id": "service-public-bj",
        "live": True,
    }
