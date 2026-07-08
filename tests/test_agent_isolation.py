from nullain.agent import run_agent
from nullain.core_agent import Agent
from nullain.tools import ToolRegistry, default_registry, restricted


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


def _scripted_llm(responses: list[_FakeResponse]):
    calls = {"count": 0}

    def fake_complete(*args, **kwargs):
        index = calls["count"]
        calls["count"] += 1
        if index >= len(responses):
            return responses[-1]
        return responses[index]

    return fake_complete, calls


def test_restricted_agent_blocks_disallowed_tool(monkeypatch):
    run_command_called = {"value": False}

    def sentinel_run_command(**kwargs):
        run_command_called["value"] = True
        return "não deveria executar"

    monkeypatch.setattr(
        "nullain.tools.shell.run_command",
        sentinel_run_command,
    )

    fake_complete, _calls = _scripted_llm(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall("call_1", "run_command", '{"cmd": "echo x"}'),
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content="ok, entendi")),
        ]
    )
    monkeypatch.setattr("nullain.core_agent.complete_stream", fake_complete)
    monkeypatch.setattr("nullain.core_agent.complete", fake_complete)
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda messages, model=None: messages)
    monkeypatch.setattr("nullain.core_agent.memory.log_tool_call", lambda *args, **kwargs: None)

    agent = Agent(
        restricted(["read_file"]),
        confirm=lambda _: True,
    )
    messages = [{"role": "user", "content": "rode um comando"}]

    result = agent.run(messages)

    assert "tool não permitida" in messages[-2]["content"]
    assert run_command_called["value"] is False
    assert result == "ok, entendi"


def test_two_agents_with_different_registries_do_not_interfere(monkeypatch):
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda messages, model=None: messages)
    monkeypatch.setattr("nullain.core_agent.memory.log_tool_call", lambda *args, **kwargs: None)

    read_agent = Agent(restricted(["read_file"]), confirm=lambda _: True)
    list_agent = Agent(restricted(["list_files"]), confirm=lambda _: True)

    blocked_for_read = read_agent.registry.execute("list_files", {}, confirm=lambda _: True)
    blocked_for_list = list_agent.registry.execute("read_file", {"path": "x.txt"}, confirm=lambda _: True)

    assert "tool desconhecida" in blocked_for_read
    assert "tool desconhecida" in blocked_for_list
    assert "read_file" in read_agent.registry.schemas()[0]["function"]["name"]
    assert "list_files" in list_agent.registry.schemas()[0]["function"]["name"]
    assert read_agent.registry is not list_agent.registry


def test_confirm_all_requires_confirmation_for_read_only_tools(monkeypatch, tmp_path):
    monkeypatch.setattr("nullain.tools.files.WORKSPACE_ROOT", tmp_path.resolve())
    sample = tmp_path / "sample.txt"
    sample.write_text("conteudo", encoding="utf-8")

    registry = ToolRegistry(
        {"read_file": default_registry().get("read_file")},
        confirm_all=True,
    )

    result = registry.execute(
        "read_file",
        {"path": "sample.txt"},
        confirm=None,
    )

    assert "nenhum confirmador foi fornecido" in result


def test_run_agent_wrapper_preserves_current_behavior(monkeypatch, tmp_path):
    monkeypatch.setattr("nullain.tools.files.WORKSPACE_ROOT", tmp_path.resolve())

    fake_complete, _calls = _scripted_llm(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall("call_1", "list_files", "{}"),
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content="resposta final")),
        ]
    )
    monkeypatch.setattr("nullain.core_agent.complete_stream", fake_complete)
    monkeypatch.setattr("nullain.core_agent.complete", fake_complete)
    monkeypatch.setattr("nullain.core_agent.trim_history", lambda messages, model=None: messages)
    monkeypatch.setattr("nullain.core_agent.memory.log_tool_call", lambda *args, **kwargs: None)

    messages = [{"role": "user", "content": "liste arquivos"}]
    result = run_agent(messages, confirm=lambda _: True)

    assert result == "resposta final"
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "resposta final"