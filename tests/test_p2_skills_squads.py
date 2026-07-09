"""P2: Skills, Squads, MCP sync incremental e tools registradas."""

from __future__ import annotations

from pathlib import Path

import pytest

from nullain.skills.loader import parse_skill_file
from nullain.skills.registry import SkillRegistry, build_skill_tools, init_skills
from nullain.squads.orchestrator import (
    SquadBudget,
    SquadOrchestrator,
    plan_roles_heuristic,
)
from nullain.squads.roles import ROLE_SPECS, list_roles
from nullain import memory, server
from nullain import tools as tools_mod
from nullain.mcp_client import McpManager, ServerState, ServerStatus
from nullain.tools import init_tools, restricted
from starlette.testclient import TestClient


@pytest.fixture
def sample_skills(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Skill de teste\n"
        "needs_confirmation: false\n"
        "tools: [read_file]\n"
        "---\n\n"
        "Corpo da skill demo.\n",
        encoding="utf-8",
    )
    (skill_dir / "handler.py").write_text(
        "def run(input_text='', confirm=None):\n"
        "    return f'demo:{input_text}'\n",
        encoding="utf-8",
    )
    return tmp_path / "skills"


def test_parse_skill_file(sample_skills: Path):
    skill = parse_skill_file(sample_skills / "demo" / "SKILL.md")
    assert skill.name == "demo"
    assert skill.description == "Skill de teste"
    assert skill.tools == ["read_file"]
    assert skill.handler is not None
    assert "Corpo" in skill.body


def test_discover_and_run_handler(sample_skills: Path):
    registry = SkillRegistry()
    count = registry.reload([sample_skills])
    assert count == 1
    result = registry.run("demo", input_text="hola")
    assert result == "demo:hola"


def test_run_skill_unknown():
    registry = SkillRegistry({})
    out = registry.run("nope")
    assert "desconhecida" in out


def test_run_skill_requires_confirm_when_flagged(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "safe"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: safe\ndescription: x\nneeds_confirmation: true\n---\nbody\n",
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.reload([tmp_path / "skills"])
    assert "nenhum confirmador" in registry.run("safe", "x", confirm=None)
    assert registry.run("safe", "x", confirm=lambda _: False) == "Operação cancelada pelo usuário."
    out = registry.run("safe", "x", confirm=lambda _: True)
    assert "Skill: safe" in out


def test_build_skill_tools_registered(sample_skills: Path):
    init_skills([sample_skills])
    tools = build_skill_tools()
    assert "list_skills" in tools
    assert "run_skill" in tools
    listed = tools["list_skills"]["fn"]()
    assert "demo" in listed
    result = tools["run_skill"]["fn"](name="demo", input="z")
    assert result == "demo:z"


def test_init_tools_includes_skills_and_squads(sample_skills: Path):
    init_skills([sample_skills])
    total = init_tools(None)
    assert total >= 4 + 2 + 2  # native + skill tools + squad tools
    assert "list_skills" in tools_mod.TOOL_REGISTRY
    assert "run_squad" in tools_mod.TOOL_REGISTRY
    assert tools_mod.TOOL_REGISTRY["run_squad"]["needs_confirmation"] is True


def test_plan_roles_heuristic_engineering():
    plan = plan_roles_heuristic("implemente um fix no código do README", max_roles=3)
    roles = [r for r, _ in plan]
    assert "engineering" in roles


def test_plan_roles_heuristic_default_has_research():
    plan = plan_roles_heuristic("faça algo genérico por favor", max_roles=2)
    assert len(plan) >= 1
    assert plan[0][0] in ROLE_SPECS


def test_list_roles_public():
    roles = list_roles()
    names = {r["name"] for r in roles}
    assert names == {"research", "engineering", "ops"}


def test_squad_orchestrator_runs_with_fake_agent(monkeypatch):
    calls: list[str] = []

    class FakeAgent:
        def __init__(self, registry, confirm, **kwargs):
            self.registry = registry
            self.role_hint = kwargs.get("session_id", "")

        def run(self, messages):
            role = self.role_hint.split(":")[-1]
            calls.append(role)
            return f"ok-{role}"

    monkeypatch.setattr("nullain.squads.orchestrator.Agent", FakeAgent)
    monkeypatch.setattr(
        "nullain.squads.orchestrator.plan_roles_with_llm",
        lambda goal, max_roles=3: None,
    )
    monkeypatch.setattr(
        "nullain.squads.orchestrator.complete",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no llm")),
    )

    init_tools(None)
    orch = SquadOrchestrator(
        budget=SquadBudget(max_roles=2, max_iterations_per_agent=2),
        use_llm_planner=False,
    )
    result = orch.run(
        "pesquise e implemente um ajuste",
        confirm=lambda _: True,
        plan=[
            ("research", "pesquisar"),
            ("engineering", "implementar"),
        ],
    )
    assert all(r.ok for r in result.role_results)
    assert len(result.role_results) == 2
    assert "research" in calls
    assert "engineering" in calls
    assert "Objetivo" in result.summary or "research" in result.summary


def test_restricted_squad_role_registry():
    init_tools(None)
    reg = restricted(list(ROLE_SPECS["research"].tools))
    assert "read_file" in reg
    assert "write_file" not in reg


def test_mcp_sync_from_config_reports_structure(monkeypatch, tmp_path):
    manager = McpManager()
    manager._server_configs = {"old": {"name": "old", "transport": "stdio"}}
    manager._servers = {}
    manager._server_status = {
        "old": ServerStatus(name="old", state=ServerState.DISABLED),
    }

    config = tmp_path / "mcp.config.json"
    config.write_text('{"servers": []}', encoding="utf-8")

    async def fake_disconnect(name: str):
        manager._server_configs.pop(name, None)

    monkeypatch.setattr(manager, "_disconnect_server_async", fake_disconnect)
    import asyncio

    result = asyncio.run(manager._sync_from_config_async(config))
    assert "old" in result["disconnected"]
    assert result["tool_count"] == 0


def test_api_skills_and_mcp_status_endpoints(monkeypatch, tmp_path, sample_skills):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "p2.db")
    memory.init_db()
    init_skills([sample_skills])
    init_tools(None)

    monkeypatch.setattr(server.brain, "startup", lambda: (0, 0))
    monkeypatch.setattr(server.brain, "shutdown", lambda: None)
    monkeypatch.setattr(
        server.brain,
        "reload_skills",
        lambda: {"skills": 1, "tools": 10},
    )
    monkeypatch.setattr(
        server.brain.mcp_manager,
        "health_snapshot",
        lambda: {"connected": True, "servers": [], "tool_count": 0, "errors": []},
    )

    with TestClient(server.app) as client:
        skills = client.get("/skills")
        assert skills.status_code == 200
        body = skills.json()
        assert any(s["name"] == "demo" for s in body)

        status = client.get("/mcp/status")
        assert status.status_code == 200
        assert status.json()["connected"] is True

        roles = client.get("/squads/roles")
        assert roles.status_code == 200
        assert len(roles.json()) == 3

        reloaded = client.post("/skills/reload")
        assert reloaded.status_code == 200
        assert reloaded.json()["skills"] == 1
