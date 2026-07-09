"""P3: Loop Engineering, NULLAIN-CODING e sandbox de shell."""

from __future__ import annotations

from unittest.mock import MagicMock

from starlette.testclient import TestClient

from nullain import memory, server
from nullain import tools as tools_mod
from nullain.coding.harness import CodingHarness, build_coding_tools
from nullain.loop.engine import EngineeringLoop, LoopBudget, build_loop_tools
from nullain.tools import init_tools
from nullain.tools.sandbox import evaluate_command
from nullain.tools.shell import run_command
from nullain.tools import files


# ── Sandbox ───────────────────────────────────────────────────────────────────


def test_sandbox_blocks_rm_rf_root():
    decision = evaluate_command("rm -rf /")
    assert decision.allowed is False
    assert "bloqueado" in decision.reason or "deny" in decision.reason


def test_sandbox_blocks_format():
    assert evaluate_command("format c:").allowed is False


def test_sandbox_allows_safe_command():
    assert evaluate_command("python -m pytest -q").allowed is True


def test_sandbox_allowlist_blocks_unknown():
    decision = evaluate_command(
        "curl http://evil",
        allowlist=["python", "pytest"],
        enabled=True,
    )
    assert decision.allowed is False
    assert "allowlist" in decision.reason


def test_sandbox_allowlist_allows_prefix():
    decision = evaluate_command(
        "python -m pytest",
        allowlist=["python"],
        enabled=True,
    )
    assert decision.allowed is True


def test_sandbox_allowlist_regex():
    decision = evaluate_command(
        "uv run pytest -q",
        allowlist=["re:^uv\\s+run"],
        enabled=True,
    )
    assert decision.allowed is True


def test_run_command_sandbox_blocks_without_subprocess(monkeypatch, tmp_path):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())

    class Settings:
        nullain_shell_sandbox = True
        nullain_shell_allowlist = ""
        nullain_shell_deny_extra = ""

    monkeypatch.setattr("nullain.config.get_settings", lambda: Settings())
    monkeypatch.setattr(
        "nullain.tools.shell.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deve rodar")),
    )
    out = run_command("rm -rf /", confirm=lambda _: True)
    assert "sandbox bloqueou" in out


def test_run_command_still_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())
    out = run_command("echo hi", confirm=None)
    assert "nenhum confirmador" in out


# ── Loop Engineering ──────────────────────────────────────────────────────────


def test_loop_converges_with_fakes(monkeypatch):
    plans = ["plano 1"]
    actions = ["implementei com sucesso"]
    evals = [
        '{"done": true, "score": 0.95, "rationale": "objetivo atingido"}',
    ]

    def fake_complete(messages, **kwargs):
        content = messages[-1]["content"]
        if "planeja" in (messages[0].get("content") or "").lower() or "Plano do próximo" in content:
            text = plans[0]
        elif "Avalie" in content or "done" in (messages[0].get("content") or ""):
            text = evals[0]
        else:
            text = "ok"

        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    class FakeAgent:
        def __init__(self, *a, **k):
            pass

        def run(self, messages):
            return actions[0]

    monkeypatch.setattr("nullain.loop.engine.complete", fake_complete)
    monkeypatch.setattr("nullain.loop.engine.Agent", FakeAgent)
    monkeypatch.setattr("nullain.loop.engine.restricted", lambda names: MagicMock())

    engine = EngineeringLoop(budget=LoopBudget(max_cycles=3, max_iterations_per_cycle=2))
    result = engine.run("faça X", confirm=lambda _: True)

    assert result.converged is True
    assert result.stop_reason == "converged"
    assert len(result.cycles) == 1
    assert result.cycles[0].score == 0.95


def test_loop_stops_at_max_cycles(monkeypatch):
    def fake_complete(messages, **kwargs):
        content = messages[-1]["content"]
        if "Avalie" in content or "JSON" in (messages[0].get("content") or ""):
            text = '{"done": false, "score": 0.3, "rationale": "ainda não"}'
        else:
            text = "plano genérico"

        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    class FakeAgent:
        def __init__(self, *a, **k):
            pass

        def run(self, messages):
            return "ainda trabalhando"

    monkeypatch.setattr("nullain.loop.engine.complete", fake_complete)
    monkeypatch.setattr("nullain.loop.engine.Agent", FakeAgent)
    monkeypatch.setattr("nullain.loop.engine.restricted", lambda names: MagicMock())

    engine = EngineeringLoop(budget=LoopBudget(max_cycles=2))
    result = engine.run("objetivo longo", confirm=lambda _: True)
    assert result.converged is False
    assert result.stop_reason == "max_cycles"
    assert len(result.cycles) == 2


def test_loop_checkpoint_denied(monkeypatch):
    def fake_complete(messages, **kwargs):
        text = '{"done": false, "score": 0.1, "rationale": "nope"}'
        if "plano" in (messages[0].get("content") or "").lower() or "Plano" in messages[-1]["content"]:
            text = "passo 1"
        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    class FakeAgent:
        def __init__(self, *a, **k):
            pass

        def run(self, messages):
            return "parcial"

    confirms = {"n": 0}

    def confirm(preview: str) -> bool:
        confirms["n"] += 1
        # 1ª: início implícito via tools no act — aqui só checkpoint entre ciclos
        if "checkpoint" in preview.lower():
            return False
        return True

    monkeypatch.setattr("nullain.loop.engine.complete", fake_complete)
    monkeypatch.setattr("nullain.loop.engine.Agent", FakeAgent)
    monkeypatch.setattr("nullain.loop.engine.restricted", lambda names: MagicMock())

    engine = EngineeringLoop(
        budget=LoopBudget(max_cycles=3, require_checkpoint=True),
    )
    result = engine.run("obj", confirm=confirm)
    assert result.stop_reason == "checkpoint_denied"
    assert len(result.cycles) == 1


def test_build_loop_tools_fail_closed():
    tools = build_loop_tools()
    assert tools["run_engineering_loop"]["needs_confirmation"] is True
    out = tools["run_engineering_loop"]["fn"](goal="x", confirm=None)
    assert "nenhum confirmador" in out


# ── Coding harness ────────────────────────────────────────────────────────────


def test_coding_harness_runs(monkeypatch):
    class FakeAgent:
        def __init__(self, *a, **k):
            pass

        def run(self, messages):
            assert "system" in messages[0]["role"]
            return "diff: fix aplicado"

    monkeypatch.setattr("nullain.coding.harness.Agent", FakeAgent)
    monkeypatch.setattr("nullain.coding.harness.restricted", lambda names: MagicMock())

    harness = CodingHarness()
    result = harness.run("corrija o bug", confirm=lambda _: True)
    assert result.ok is True
    assert "fix" in result.output


def test_coding_tools_registered():
    init_tools(None)
    assert "run_engineering_loop" in tools_mod.TOOL_REGISTRY
    assert "run_coding_task" in tools_mod.TOOL_REGISTRY
    assert tools_mod.TOOL_REGISTRY["run_coding_task"]["needs_confirmation"] is True


def test_build_coding_tools_cancel():
    tools = build_coding_tools()
    out = tools["run_coding_task"]["fn"](goal="x", confirm=lambda _: False)
    assert out == "Operação cancelada pelo usuário."


# ── API ───────────────────────────────────────────────────────────────────────


def test_api_loop_and_coding_endpoints(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "p3.db")
    memory.init_db()
    monkeypatch.setattr(server.brain, "startup", lambda: (0, 0))
    monkeypatch.setattr(server.brain, "shutdown", lambda: None)

    class FakeLoopResult:
        def to_dict(self):
            return {"converged": True, "goal": "g", "cycles": []}

    class FakeCodingResult:
        def to_dict(self):
            return {"ok": True, "goal": "g", "output": "done"}

    class FakeLoop:
        def __init__(self, *a, **k):
            pass

        def run(self, *a, **k):
            return FakeLoopResult()

    class FakeHarness:
        def __init__(self, *a, **k):
            pass

        def run(self, *a, **k):
            return FakeCodingResult()

    monkeypatch.setattr("nullain.loop.EngineeringLoop", FakeLoop)
    monkeypatch.setattr("nullain.loop.LoopBudget", lambda **k: MagicMock())
    monkeypatch.setattr("nullain.coding.CodingHarness", FakeHarness)
    monkeypatch.setattr("nullain.coding.CodingBudget", lambda **k: MagicMock())

    with TestClient(server.app) as client:
        loop_resp = client.post("/loop/run", json={"goal": "test"})
        assert loop_resp.status_code == 200
        assert loop_resp.json()["converged"] is True

        code_resp = client.post("/coding/run", json={"goal": "fix"})
        assert code_resp.status_code == 200
        assert code_resp.json()["ok"] is True
