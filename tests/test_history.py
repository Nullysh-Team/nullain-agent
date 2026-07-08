from nullain.history import SUMMARY_PREFIX, trim_history


def _system_message() -> dict[str, str]:
    return {"role": "system", "content": "Você é o NULLAIN."}


def _user_message(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def _assistant_message(content: str) -> dict[str, str]:
    return {"role": "assistant", "content": content}


def _assistant_tool_call(assistant_id: str, tool_name: str, tool_id: str) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tool_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": "{}"},
            }
        ],
    }


def _tool_message(tool_id: str, content: str) -> dict[str, str]:
    return {"role": "tool", "tool_call_id": tool_id, "content": content}


def test_trim_history_preserves_system_message(monkeypatch):
    monkeypatch.setattr(
        "nullain.history.complete",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no summary")),
    )

    messages = [_system_message(), _user_message("oi"), _assistant_message("olá")]
    for index in range(25):
        messages.extend(
            [
                _user_message(f"pergunta {index}"),
                _assistant_message(f"resposta {index}"),
            ]
        )

    trimmed = trim_history(messages, max_turns=3)

    assert trimmed[0] == _system_message()
    assert len(trimmed) < len(messages)
    assert len(trimmed) == 4
    assert trimmed[-1]["role"] == "assistant"
    assert trimmed[-1]["content"] == "resposta 24"


def test_trim_history_keeps_tool_call_group_at_window_edge(monkeypatch):
    monkeypatch.setattr(
        "nullain.history.complete",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no summary")),
    )

    tool_id = "call_tool_edge"
    messages = [
        _system_message(),
        _user_message("primeira"),
        _assistant_message("resposta antiga"),
        _user_message("use a ferramenta"),
        _assistant_tool_call("asst_edge", "read_file", tool_id),
        _tool_message(tool_id, "conteúdo do arquivo"),
    ]

    trimmed = trim_history(messages, max_turns=1)

    assert trimmed[0] == _system_message()
    assert len(trimmed) == 3
    assert trimmed[1]["role"] == "assistant"
    assert trimmed[1]["tool_calls"][0]["id"] == tool_id
    assert trimmed[2]["role"] == "tool"
    assert trimmed[2]["tool_call_id"] == tool_id


def test_trim_history_keeps_tool_call_groups_atomic(monkeypatch):
    def fake_complete(*args, **kwargs):
        class _Message:
            content = "resumo curto"

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        return _Response()

    monkeypatch.setattr("nullain.history.complete", fake_complete)

    tool_id = "call_tool_1"
    messages = [
        _system_message(),
        _user_message("primeira"),
        _assistant_message("resposta antiga"),
        _user_message("use a ferramenta"),
        _assistant_tool_call("asst_1", "read_file", tool_id),
        _tool_message(tool_id, "conteúdo do arquivo"),
        _user_message("última pergunta"),
        _assistant_message("resposta final"),
    ]

    trimmed = trim_history(messages, max_turns=2)

    roles = [message["role"] for message in trimmed]
    assert roles[0] == "system"
    assert roles.count("assistant") >= 1
    assert "tool" not in roles or (
        "assistant" in roles
        and any(message.get("tool_calls") for message in trimmed if message["role"] == "assistant")
    )

    tool_messages = [message for message in trimmed if message["role"] == "tool"]
    if tool_messages:
        assistant_with_tools = next(
            message for message in trimmed if message.get("tool_calls")
        )
        tool_ids = {tool_call["id"] for tool_call in assistant_with_tools["tool_calls"]}
        assert all(message["tool_call_id"] in tool_ids for message in tool_messages)


def test_trim_history_summary_failure_does_not_propagate(monkeypatch):
    calls = {"count": 0}

    def failing_complete(*args, **kwargs):
        calls["count"] += 1
        raise RuntimeError("falha de sumarização")

    monkeypatch.setattr("nullain.history.complete", failing_complete)

    messages = [_system_message()]
    for index in range(25):
        messages.extend(
            [
                _user_message(f"pergunta {index}"),
                _assistant_message(f"resposta {index}"),
            ]
        )

    trimmed = trim_history(messages, max_turns=2)

    assert calls["count"] == 1
    assert trimmed[0] == _system_message()
    assert not any(
        (message.get("content") or "").startswith(SUMMARY_PREFIX) for message in trimmed
    )
    assert trimmed[-2]["role"] == "user"
    assert trimmed[-1]["role"] == "assistant"