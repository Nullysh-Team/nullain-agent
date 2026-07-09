"""P1: compactação, confirmação serial, workspace/shell, retenção, e2e Agent, lifespan."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from nullain import memory, server
from nullain.core_agent import Agent, compact_tool_result
from nullain.tools import ToolRegistry, files
from nullain.tools.shell import run_command
from nullain.workspace import set_workspace_root


# ── Helpers LLM fake ──────────────────────────────────────────────────────────


class _FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, tool_id: str, name: str, arguments: str) -> None:
        self.id = tool_id
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content: str = "", tool_calls: list[_FakeToolCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message


class _FakeResponse:
    def __init__(self, message: _FakeMessage) -> None:
        self.choices = [_FakeChoice(message)]
        self.usage = None


def _scripted_llm(responses: list[_FakeResponse]):
    calls = {"count": 0}

    def fake_complete(*args, **kwargs):
        index = calls["count"]
        calls["count"] += 1
        if index >= len(responses):
            return responses[-1]
        return responses[index]

    return fake_complete, calls


# ── Compactação ───────────────────────────────────────────────────────────────


def test_compact_tool_result_under_limit_unchanged():
    text = "x" * 100
    assert compact_tool_result(text, max_chars=200) == text


def test_compact_tool_result_truncates_with_marker():
    text = "A" * 500 + "B" * 500
    out = compact_tool_result(text, max_chars=200)
    assert len(out) <= 220
    assert "omitidos" in out or "truncado" in out
    assert out.startswith("A")
    assert out.endswith("B")


# ── Confirmação serial ────────────────────────────────────────────────────────


def test_confirmation_broker_serializes_requests():
    broker = server.ConfirmationBroker(timeout_seconds=5)
    order: list[str] = []
    active = {"count": 0, "max": 0}
    lock = threading.Lock()

    def send_and_approve(event: dict) -> None:
        with lock:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
            order.append(event["preview"])
        time.sleep(0.05)
        broker.respond(event["request_id"], True)
        with lock:
            active["count"] -= 1

    def worker(label: str) -> bool:
        return broker.request(label, send_and_approve)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(worker, f"c{i}") for i in range(3)]
        results = [f.result(timeout=10) for f in futures]

    assert all(results)
    assert active["max"] == 1
    assert len(order) == 3


def test_agent_serializes_confirm_across_parallel_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    confirm_active = {"count": 0, "max": 0}
    lock = threading.Lock()

    def slow_confirm(preview: str) -> bool:
        with lock:
            confirm_active["count"] += 1
            confirm_active["max"] = max(confirm_active["max"], confirm_active["count"])
        time.sleep(0.08)
        with lock:
            confirm_active["count"] -= 1
        return True

    def read_needing_confirm(path: str, confirm=None) -> str:
        # Simula tool sensível: pede confirm antes de ler
        if confirm is None or not confirm(f"read {path}"):
            return "cancelado"
        return files.read_file(path)

    registry = ToolRegistry(
        {
            "read_file": {
                "needs_confirmation": True,
                "fn": read_needing_confirm,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "read",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    },
                },
            }
        }
    )

    tool_calls = [
        _FakeToolCall("c1", "read_file", '{"path": "a.txt"}'),
        _FakeToolCall("c2", "read_file", '{"path": "b.txt"}'),
    ]
    responses = [
        _FakeResponse(_FakeMessage(tool_calls=tool_calls)),
        _FakeResponse(_FakeMessage(content="li os dois")),
    ]
    fake_complete, _ = _scripted_llm(responses)
    monkeypatch.setattr("nullain.core_agent.complete_stream", fake_complete)
    monkeypatch.setattr("nullain.core_agent.complete", fake_complete)
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda msgs, model=None: msgs)
    monkeypatch.setattr(memory, "log_tool_call", lambda *a, **k: None)
    monkeypatch.setattr(memory, "log_turn_metrics", lambda *a, **k: None)

    agent = Agent(registry, slow_confirm, parallel_tools=True)
    messages = [{"role": "user", "content": "leia"}]
    answer = agent.run(messages)

    assert answer == "li os dois"
    assert confirm_active["max"] == 1


# ── Workspace + shell cwd ─────────────────────────────────────────────────────


def test_set_workspace_root_updates_files_module(tmp_path):
    root = set_workspace_root(tmp_path)
    assert root == tmp_path.resolve()
    assert files.WORKSPACE_ROOT == root


def test_run_command_uses_workspace_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        result = MagicMock()
        result.stdout = "ok"
        result.stderr = ""
        result.returncode = 0
        return result

    monkeypatch.setattr("nullain.tools.shell.subprocess.run", fake_run)
    out = run_command("echo ok", confirm=lambda _: True)
    assert out == "ok"
    assert Path(captured["cwd"]).resolve() == tmp_path.resolve()


# ── Retenção ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mem_db(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "p1.db")
    memory.init_db()
    yield
    memory.stop_background_writer()


def test_purge_retention_by_max_rows(mem_db):
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with memory._connect() as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO tool_logs (tool_name, arguments, result, session_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"t{i}", "{}", "r", "s", old if i < 3 else datetime.now(timezone.utc).isoformat()),
            )
            conn.execute(
                "INSERT INTO metrics (session_id, turn_index, total_ms, iterations, "
                "tool_count, tool_total_ms, created_at) VALUES (?, 0, 1.0, 1, 0, 0, ?)",
                ("s", old if i < 3 else datetime.now(timezone.utc).isoformat()),
            )

    deleted = memory.purge_retention(
        log_retention_days=0,
        log_max_rows=2,
        metrics_retention_days=0,
        metrics_max_rows=2,
    )
    assert deleted["tool_logs"] >= 3
    assert deleted["metrics"] >= 3

    with memory._connect() as conn:
        logs = conn.execute("SELECT COUNT(*) AS c FROM tool_logs").fetchone()["c"]
        mets = conn.execute("SELECT COUNT(*) AS c FROM metrics").fetchone()["c"]
    assert logs == 2
    assert mets == 2


def test_purge_retention_by_age(mem_db):
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    recent = datetime.now(timezone.utc).isoformat()
    with memory._connect() as conn:
        conn.execute(
            "INSERT INTO tool_logs (tool_name, arguments, result, session_id, created_at) "
            "VALUES ('old', '{}', 'r', 's', ?)",
            (old,),
        )
        conn.execute(
            "INSERT INTO tool_logs (tool_name, arguments, result, session_id, created_at) "
            "VALUES ('new', '{}', 'r', 's', ?)",
            (recent,),
        )

    memory.purge_retention(
        log_retention_days=30,
        log_max_rows=0,
        metrics_retention_days=0,
        metrics_max_rows=0,
    )

    with memory._connect() as conn:
        names = [
            row["tool_name"]
            for row in conn.execute("SELECT tool_name FROM tool_logs").fetchall()
        ]
    assert names == ["new"]


# ── E2E Agent loop ────────────────────────────────────────────────────────────


def test_agent_e2e_tool_then_final_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())
    (tmp_path / "note.txt").write_text("conteudo-e2e", encoding="utf-8")

    responses = [
        _FakeResponse(
            _FakeMessage(
                tool_calls=[
                    _FakeToolCall("call1", "read_file", '{"path": "note.txt"}'),
                ]
            )
        ),
        _FakeResponse(_FakeMessage(content="O arquivo diz conteudo-e2e")),
    ]
    fake_complete, calls = _scripted_llm(responses)
    monkeypatch.setattr("nullain.core_agent.complete_stream", fake_complete)
    monkeypatch.setattr("nullain.core_agent.complete", fake_complete)
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda msgs, model=None: msgs)
    monkeypatch.setattr(memory, "log_tool_call", lambda *a, **k: None)
    monkeypatch.setattr(memory, "log_turn_metrics", lambda *a, **k: None)

    registry = ToolRegistry(
        {
            "read_file": {
                "needs_confirmation": False,
                "fn": files.read_file,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Lê arquivo",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    },
                },
            }
        }
    )

    events: list[str] = []
    agent = Agent(
        registry,
        confirm=lambda _: True,
        on_event=lambda e: events.append(e.get("type", "")),
        tool_result_max_chars=50,
    )
    messages: list[dict] = [{"role": "user", "content": "leia note.txt"}]
    answer = agent.run(messages)

    assert answer == "O arquivo diz conteudo-e2e"
    assert calls["count"] == 2
    assert "tool_call" in events
    assert "tool_result" in events
    assert "answer" in events
    # tool result entrou no histórico
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "conteudo-e2e" in tool_msgs[0]["content"]


def test_agent_e2e_compacts_large_tool_result(monkeypatch, tmp_path):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())
    big = "Z" * 5000
    (tmp_path / "big.txt").write_text(big, encoding="utf-8")

    responses = [
        _FakeResponse(
            _FakeMessage(
                tool_calls=[_FakeToolCall("c1", "read_file", '{"path": "big.txt"}')]
            )
        ),
        _FakeResponse(_FakeMessage(content="ok")),
    ]
    fake_complete, _ = _scripted_llm(responses)
    monkeypatch.setattr("nullain.core_agent.complete_stream", fake_complete)
    monkeypatch.setattr("nullain.core_agent.complete", fake_complete)
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda msgs, model=None: msgs)
    monkeypatch.setattr(memory, "log_tool_call", lambda *a, **k: None)
    monkeypatch.setattr(memory, "log_turn_metrics", lambda *a, **k: None)

    registry = ToolRegistry(
        {
            "read_file": {
                "needs_confirmation": False,
                "fn": files.read_file,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "read",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    },
                },
            }
        }
    )

    agent = Agent(registry, confirm=lambda _: True, tool_result_max_chars=200)
    messages: list[dict] = [{"role": "user", "content": "leia"}]
    agent.run(messages)

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert len(tool_msgs[0]["content"]) < 500
    assert "omitidos" in tool_msgs[0]["content"] or "truncado" in tool_msgs[0]["content"]


# ── Lifespan (sem on_event) ───────────────────────────────────────────────────


def test_server_uses_lifespan_not_on_event():
    source = Path("src/nullain/server.py").read_text(encoding="utf-8")
    assert "@app.on_event" not in source
    assert "lifespan=lifespan" in source or "lifespan =" in source


def test_app_lifespan_starts_brain(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "life.db")
    started = {"value": False}
    stopped = {"value": False}

    monkeypatch.setattr(
        server.brain,
        "startup",
        lambda: started.__setitem__("value", True) or (0, 0),
    )
    monkeypatch.setattr(
        server.brain,
        "shutdown",
        lambda: stopped.__setitem__("value", True),
    )

    with TestClient(server.app) as client:
        assert started["value"] is True
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "workspace" in body

    assert stopped["value"] is True
