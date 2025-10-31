import argparse

import pytest

from server import cli


@pytest.fixture
def parser():
    return cli.build_parser()


def test_build_parser_has_commands(parser: argparse.ArgumentParser):
    # Parse minimal arguments for each command to ensure they are registered.
    serve_args = parser.parse_args(["serve"])
    assert serve_args.command == "serve"

    serve_http_args = parser.parse_args(["serve-http"])
    assert serve_http_args.command == "serve-http"

    scrape_args = parser.parse_args(["scrape", "--limit", "1"])
    assert scrape_args.command == "scrape"

    status_args = parser.parse_args(["status"])
    assert status_args.command == "status"


def test_main_serve_dispatch(monkeypatch):
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


def test_main_serve_http_dispatch(monkeypatch):
    called = {}

    def fake_get_settings():
        return "settings"

    async def fake_serve(settings, *, host, port, log_level, json_response):
        called["args"] = {
            "settings": settings,
            "host": host,
            "port": port,
            "log_level": log_level,
            "json_response": json_response,
        }

    monkeypatch.setattr(cli, "get_settings", fake_get_settings)
    monkeypatch.setattr(cli, "serve_http", fake_serve)

    exit_code = cli.main(
        [
            "serve-http",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--log-level",
            "DEBUG",
            "--json-response",
        ]
    )
    assert exit_code == 0
    assert called["args"] == {
        "settings": "settings",
        "host": "127.0.0.1",
        "port": 9000,
        "log_level": "DEBUG",
        "json_response": True,
    }


def test_main_scrape_dispatch(monkeypatch):
    called = {}

    def fake_get_settings():
        return "settings"

    async def fake_scrape(settings, *, provider_id, query, service_id, limit):
        called["args"] = {
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
    assert called["args"] == {
        "settings": "settings",
        "provider_id": None,
        "query": "test",
        "service_id": None,
        "limit": 5,
    }


def test_main_status_dispatch(monkeypatch):
    called = {}

    def fake_get_settings():
        return "settings"

    async def fake_status(settings, *, provider_id, live):
        called["args"] = {
            "settings": settings,
            "provider_id": provider_id,
            "live": live,
        }

    monkeypatch.setattr(cli, "get_settings", fake_get_settings)
    monkeypatch.setattr(cli, "_status_async", fake_status)

    exit_code = cli.main(["status", "--provider", "service-public-bj", "--live"])
    assert exit_code == 0
    assert called["args"] == {
        "settings": "settings",
        "provider_id": "service-public-bj",
        "live": True,
    }
