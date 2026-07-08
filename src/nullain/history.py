from __future__ import annotations

from typing import Any

from nullain.llm import complete

SUMMARY_PREFIX = "Resumo da conversa anterior:"
_MAX_SUMMARY_WORDS = 150


def _is_summary_message(message: dict[str, Any]) -> bool:
    if message.get("role") != "system":
        return False
    content = message.get("content") or ""
    return isinstance(content, str) and content.startswith(SUMMARY_PREFIX)


def _parse_groups(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    index = 0

    while index < len(messages):
        message = messages[index]
        role = message.get("role")

        if role == "assistant" and message.get("tool_calls"):
            group = [message]
            tool_call_ids = {
                tool_call.get("id")
                for tool_call in message["tool_calls"]
                if tool_call.get("id")
            }
            index += 1
            while index < len(messages) and messages[index].get("role") == "tool":
                tool_message = messages[index]
                if tool_message.get("tool_call_id") in tool_call_ids:
                    group.append(tool_message)
                index += 1
            groups.append(group)
            continue

        groups.append([message])
        index += 1

    return groups


def _flatten_groups(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for group in groups:
        flattened.extend(group)
    return flattened


def _format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.get("role", "unknown")
        content = message.get("content") or ""
        if role == "assistant" and message.get("tool_calls"):
            tool_names = [
                tool_call.get("function", {}).get("name", "tool")
                for tool_call in message["tool_calls"]
            ]
            lines.append(f"assistant: [tool_calls: {', '.join(tool_names)}]")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _summarize_discarded(
    discarded: list[dict[str, Any]],
    model: str | None,
) -> str | None:
    if not discarded:
        return None

    try:
        transcript = _format_messages_for_summary(discarded)
        response = complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Você resume conversas de forma concisa. "
                        f"Use no máximo {_MAX_SUMMARY_WORDS} palavras."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Resuma apenas o trecho abaixo, preservando fatos, decisões "
                        "e contexto útil para continuar a conversa:\n\n"
                        f"{transcript}"
                    ),
                },
            ],
            model=model,
            tools=None,
        )
        summary = (response.choices[0].message.content or "").strip()
        return summary or None
    except Exception:
        return None


def trim_history(
    messages: list[dict[str, Any]],
    max_turns: int = 20,
    model: str | None = None,
) -> list[dict[str, Any]]:
    if not messages:
        return messages

    protected = messages[0]
    rest = [message for message in messages[1:] if not _is_summary_message(message)]
    groups = _parse_groups(rest)

    if len(groups) <= max_turns:
        return messages

    kept_groups = groups[-max_turns:]
    discarded_groups = groups[:-max_turns]
    discarded = _flatten_groups(discarded_groups)

    result = [protected]
    summary = _summarize_discarded(discarded, model=model)
    if summary:
        result.append({"role": "system", "content": f"{SUMMARY_PREFIX} {summary}"})

    result.extend(_flatten_groups(kept_groups))
    return result