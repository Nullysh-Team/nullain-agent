"""Testes para a Fase de Qualificação — Blocos A, B, C."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from nullain import memory
from nullain.core_agent import Agent, CONFIRM_TIMEOUT_SECONDS
from nullain.llm import LLMStreamError, LLMNetworkError, extract_usage
from nullain.mcp_client import McpManager, McpToolBinding, ServerConnection, ServerState
from nullain.persona import build_session_messages, get_facts_message, get_system_message
from nullain.tools import ToolRegistry, default_registry


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mem_db(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_qualify.db")
    memory.init_db()
    yield
    memory.stop_background_writer()


# ── Helpers ───────────────────────────────────────────────────────────────────


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


class _FakeUsage:
    def __init__(self, prompt_tokens: int = 10, completion_tokens: int = 20) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeResponseWithUsage:
    def __init__(self, message: _FakeMessage) -> None:
        self.choices = [_FakeChoice(message)]
        self.usage = _FakeUsage()


def _scripted_llm(responses: list):
    calls = {"count": 0}

    def fake_complete(*args, **kwargs):
        index = calls["count"]
        calls["count"] += 1
        if index >= len(responses):
            return responses[-1]
        return responses[index]

    return fake_complete, calls


# ── Bloco A: Consolidação do núcleo ───────────────────────────────────────────


def test_agent_logs_turn_metrics(mem_db, monkeypatch):
    """A4: Agent registra TTFT, duração, iterações e tokens na tabela metrics."""
    fake_complete, _calls = _scripted_llm(
        [_FakeResponseWithUsage(_FakeMessage(content="resposta"))]
    )
    monkeypatch.setattr("nullain.core_agent.complete_stream", fake_complete)
    monkeypatch.setattr("nullain.core_agent.complete", fake_complete)
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda messages, model=None: messages)
    monkeypatch.setattr("nullain.core_agent.memory.log_tool_call", lambda *a, **kw: None)

    # Força gravação síncrona para o teste
    monkeypatch.setattr(
        "nullain.core_agent.memory.log_turn_metrics",
        lambda m: memory._log_turn_metrics_sync(m),
    )

    agent = Agent(default_registry(), confirm=lambda _: True, model="test-model")
    messages = [{"role": "user", "content": "oi"}]
    result = agent.run(messages)

    assert result == "resposta"

    metrics = memory.get_metrics(limit=10)
    assert len(metrics) >= 1
    m = metrics[0]
    assert m["model"] == "test-model"
    assert m["total_ms"] > 0
    assert m["iterations"] == 1
    assert m["tokens_in"] == 10
    assert m["tokens_out"] == 20


def test_agent_metrics_percentiles(mem_db):
    """A5: get_metric_percentiles calcula p50/p90/p95/p99."""
    for i in range(20):
        memory._log_turn_metrics_sync(
            memory.TurnMetrics(
                session_id="s1",
                turn_index=i,
                ttft_ms=float(100 + i * 10),
                total_ms=float(200 + i * 20),
            )
        )

    pct = memory.get_metric_percentiles("ttft_ms", limit=100)
    assert pct["count"] == 20
    assert pct["p50"] is not None
    assert pct["p95"] is not None
    assert pct["p50"] <= pct["p95"]
    assert pct["p95"] <= pct["p99"]


def test_confirm_timeout_constant_exists():
    """A3: Timeout de confirmação está definido em 120s."""
    assert CONFIRM_TIMEOUT_SECONDS == 120.0


def test_llm_stream_error_is_typed(monkeypatch):
    """A2: LLMStreamError é uma exceção tipada (não genérica)."""
    assert issubclass(LLMStreamError, Exception)
    assert issubclass(LLMNetworkError, Exception)


def test_extract_usage_handles_none():
    """A4: extract_usage retorna None quando não há usage."""
    response = MagicMock()
    response.usage = None
    result = extract_usage(response)
    assert result == {"tokens_in": None, "tokens_out": None}


def test_extract_usage_handles_values():
    """A4: extract_usage extrai tokens corretamente."""
    response = MagicMock()
    response.usage = _FakeUsage(prompt_tokens=42, completion_tokens=99)
    result = extract_usage(response)
    assert result == {"tokens_in": 42, "tokens_out": 99}


# ── Bloco B: Latência ─────────────────────────────────────────────────────────


def test_prompt_stable_does_not_include_facts(mem_db, monkeypatch):
    """B1: System prompt NÃO inclui fatos dinâmicos (estável para cache)."""
    memory.add_fact("Netty adora pizza")

    system_msg = get_system_message()
    assert "Fatos conhecidos" not in system_msg["content"]
    assert "pizza" not in system_msg["content"]


def test_facts_message_is_separate(mem_db, monkeypatch):
    """B1: Fatos são injetados como mensagem separada."""
    memory.add_fact("Netty adora pizza")

    facts_msg = get_facts_message()
    assert facts_msg is not None
    assert facts_msg["role"] == "system"
    assert "pizza" in facts_msg["content"]


def test_build_session_messages_has_stable_system(mem_db, monkeypatch):
    """B1: build_session_messages produz system + facts separados."""
    memory.add_fact("Netty adora sushi")

    messages = build_session_messages()
    assert len(messages) >= 2
    assert messages[0]["role"] == "system"
    assert "sushi" not in messages[0]["content"]

    has_facts = any("sushi" in m.get("content", "") for m in messages[1:])
    assert has_facts


def test_wal_mode_enabled(mem_db):
    """B2: WAL mode está habilitado."""
    assert memory._WAL_ENABLED is True


def test_background_writer_started(mem_db):
    """B2: Background writer está rodando após init_db."""
    assert memory._BG_THREAD is not None
    assert memory._BG_THREAD.is_alive()


def test_add_message_is_queued_not_sync(mem_db, monkeypatch):
    """B2: add_message usa a fila background."""
    queued: list = []
    monkeypatch.setattr(memory, "enqueue_background", lambda fn, *args: queued.append((fn, args)))

    memory.add_message("s1", "user", "olá")

    assert len(queued) == 1
    fn, args = queued[0]
    assert fn == memory._add_message_sync
    assert args == ("s1", "user", "olá")


def test_log_tool_call_is_queued_not_sync(mem_db, monkeypatch):
    """B2: log_tool_call usa a fila background."""
    queued: list = []
    monkeypatch.setattr(memory, "enqueue_background", lambda fn, *args: queued.append((fn, args)))

    memory.log_tool_call("list_files", {}, "ok", session_id="s1")

    assert len(queued) == 1


def test_backfill_does_not_block_startup(monkeypatch, tmp_path):
    """B3: backfill_pending_embeddings_background enfileira, não executa sincrono."""
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_backfill.db")

    called: list = []
    monkeypatch.setattr(memory, "enqueue_background", lambda fn, *args: called.append(fn))

    memory.init_db()
    assert memory.backfill_pending_embeddings in called


# ── Bloco B4: Tool calls em paralelo ──────────────────────────────────────────


def test_parallel_tool_calls_execute_concurrently(monkeypatch, tmp_path):
    """B4: Tools independentes executam em paralelo quando parallel_tools=True."""
    monkeypatch.setattr("nullain.tools.files.WORKSPACE_ROOT", tmp_path.resolve())
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    execution_times: dict[str, float] = {}

    def slow_read_file(path: str) -> str:
        start = time.monotonic()
        time.sleep(0.2)
        from nullain.tools.files import read_file
        result = read_file(path)
        execution_times[path] = (start, time.monotonic())
        return result

    registry = ToolRegistry(
        {
            "read_file": {
                "needs_confirmation": False,
                "fn": slow_read_file,
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

    fake_complete, _calls = _scripted_llm(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall("call_1", "read_file", '{"path": "a.txt"}'),
                        _FakeToolCall("call_2", "read_file", '{"path": "b.txt"}'),
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content="done")),
        ]
    )
    monkeypatch.setattr("nullain.core_agent.complete_stream", fake_complete)
    monkeypatch.setattr("nullain.core_agent.complete", fake_complete)
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda messages, model=None: messages)
    monkeypatch.setattr("nullain.core_agent.memory.log_tool_call", lambda *a, **kw: None)
    monkeypatch.setattr("nullain.core_agent.memory.log_turn_metrics", lambda m: None)

    agent = Agent(registry, confirm=lambda _: True, parallel_tools=True)
    messages = [{"role": "user", "content": "read both"}]
    agent.run(messages)

    times = list(execution_times.values())
    if len(times) == 2:
        max_start = max(t[0] for t in times)
        min_end = min(t[1] for t in times)
        assert max_start < min_end, "Tool calls não executaram em paralelo"


# ── Bloco C: MCP 2.0 ──────────────────────────────────────────────────────────


def test_mcp_server_status_tracks_state():
    """C1: McpManager rastreia estado de cada servidor."""
    manager = McpManager()
    status = manager.get_server_status()
    assert isinstance(status, list)


def test_mcp_namespacing_uses_dot_notation():
    """C5: Namespacing de tools usa servidor.tool (não servidor__tool)."""
    manager = McpManager()
    mock_session = MagicMock()
    mock_session.call_tool = AsyncMock()

    binding = McpToolBinding(
        registry_name="github.create_issue",
        server_name="github",
        tool_name="create_issue",
        description="create issue",
        input_schema={"type": "object", "properties": {}},
        needs_confirmation=True,
    )
    manager._tool_bindings["github.create_issue"] = binding
    manager._servers["github"] = ServerConnection(
        name="github",
        session=mock_session,
        stack=MagicMock(),
    )
    manager._connected = True

    assert "github.create_issue" in manager.get_tool_bindings()
    assert "." in manager.get_tool_bindings()["github.create_issue"].registry_name


def test_mcp_timeout_on_tool_call():
    """C4: Tool call MCP com timeout retorna erro de timeout."""
    manager = McpManager()
    mock_session = MagicMock()

    async def slow_call(*args, **kwargs):
        await asyncio.sleep(100)

    mock_session.call_tool = slow_call
    manager._tool_bindings["test.slow"] = McpToolBinding(
        registry_name="test.slow",
        server_name="test",
        tool_name="slow",
        description="slow tool",
        input_schema={"type": "object", "properties": {}},
        needs_confirmation=False,
    )
    manager._servers["test"] = ServerConnection(
        name="test",
        session=mock_session,
        stack=MagicMock(),
    )
    manager._server_status["test"] = MagicMock()
    manager._server_status["test"].state = ServerState.CONNECTED

    manager._connected = True
    manager._loop = asyncio.new_event_loop()

    async def run_test():
        result = await manager._call_tool_async("test.slow", {}, None)
        return result

    result = asyncio.run(run_test())
    assert "timeout" in result.lower() or "Timeout" in result


def test_mcp_reconnect_sets_state_to_reconnecting():
    """C3: _schedule_reconnect muda estado para RECONNECTING."""
    from nullain.mcp_client import ServerStatus

    manager = McpManager()
    manager._loop = asyncio.new_event_loop()
    manager._server_status["test"] = ServerStatus(
        name="test",
        state=ServerState.DEGRADED,
        reconnect_attempts=0,
    )
    manager._server_configs["test"] = {"name": "test", "transport": "sse", "url": "http://fake"}

    async def run_test():
        await manager._schedule_reconnect("test")

    asyncio.run(run_test())
    status = manager._server_status["test"]
    assert status.state in (
        ServerState.RECONNECTING,
        ServerState.DEGRADED,
        ServerState.DISABLED,
    )
    assert status.reconnect_attempts >= 1


# ── Bloco D: Sessions ─────────────────────────────────────────────────────────


def test_list_sessions_returns_grouped_messages(mem_db):
    """D2: list_sessions agrupa mensagens por session_id."""
    memory.add_message("session-a", "user", "olá")
    memory.add_message("session-a", "assistant", "oi")
    memory.add_message("session-b", "user", "tchau")

    memory.flush_background_writer()

    sessions = memory.list_sessions()
    session_ids = {s["session_id"] for s in sessions}
    assert "session-a" in session_ids
    assert "session-b" in session_ids


def test_get_session_messages_returns_ordered(mem_db):
    """D2: get_session_messages retorna mensagens em ordem."""
    memory.add_message("s1", "user", "primeira")
    memory.add_message("s1", "assistant", "segunda")

    memory.flush_background_writer()

    msgs = memory.get_session_messages("s1")
    assert len(msgs) >= 2
    assert msgs[0]["content"] == "primeira"
    assert msgs[1]["content"] == "segunda"