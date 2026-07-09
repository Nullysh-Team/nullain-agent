"""Auth mínima da API: NULLAIN_API_TOKEN."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from nullain import memory, server
from nullain.config import get_settings


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test.db")
    memory.init_db()
    monkeypatch.setattr(server.brain, "startup", lambda: (0, 0))
    monkeypatch.setattr(server.brain, "shutdown", lambda: None)
    get_settings.cache_clear()
    with TestClient(server.app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_health_is_public_without_token(client: TestClient, monkeypatch):
    monkeypatch.setenv("NULLAIN_API_TOKEN", "")
    get_settings.cache_clear()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["auth_required"] is False


def test_protected_route_open_when_token_unset(client: TestClient, monkeypatch):
    monkeypatch.setenv("NULLAIN_API_TOKEN", "")
    get_settings.cache_clear()
    response = client.get("/config")
    assert response.status_code == 200


def test_protected_route_rejects_without_bearer(client: TestClient, monkeypatch):
    monkeypatch.setenv("NULLAIN_API_TOKEN", "secret-token-xyz")
    get_settings.cache_clear()
    response = client.get("/config")
    assert response.status_code == 401


def test_protected_route_accepts_bearer(client: TestClient, monkeypatch):
    monkeypatch.setenv("NULLAIN_API_TOKEN", "secret-token-xyz")
    get_settings.cache_clear()
    response = client.get(
        "/config",
        headers={"Authorization": "Bearer secret-token-xyz"},
    )
    assert response.status_code == 200


def test_protected_route_accepts_query_token(client: TestClient, monkeypatch):
    monkeypatch.setenv("NULLAIN_API_TOKEN", "secret-token-xyz")
    get_settings.cache_clear()
    response = client.get("/config?token=secret-token-xyz")
    assert response.status_code == 200


def test_websocket_rejects_without_token_when_auth_on(client: TestClient, monkeypatch):
    monkeypatch.setenv("NULLAIN_API_TOKEN", "secret-token-xyz")
    get_settings.cache_clear()
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/ws/chat",
            headers={"origin": "http://127.0.0.1:5173"},
        ):
            pass


def test_websocket_accepts_query_token_when_auth_on(client: TestClient, monkeypatch):
    monkeypatch.setenv("NULLAIN_API_TOKEN", "secret-token-xyz")
    get_settings.cache_clear()
    with client.websocket_connect(
        "/ws/chat?token=secret-token-xyz",
        headers={"origin": "http://127.0.0.1:5173"},
    ):
        pass
