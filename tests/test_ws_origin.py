import pytest
from starlette.testclient import TestClient

from nullain import server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server.brain, "startup", lambda: (0, 0))
    monkeypatch.setattr(server.brain, "shutdown", lambda: None)
    with TestClient(server.app) as test_client:
        yield test_client


def test_websocket_rejects_evil_origin(client: TestClient):
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/ws/chat",
            headers={"origin": "http://evil.example"},
        ):
            pass


def test_websocket_accepts_allowed_origin(client: TestClient):
    with client.websocket_connect(
        "/ws/chat",
        headers={"origin": "http://127.0.0.1:5173"},
    ):
        pass