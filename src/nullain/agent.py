from typing import Any

from rich.console import Console

from nullain.core_agent import Agent, ConfirmFn, EventFn, ToolCall
from nullain.tools import TOOL_REGISTRY, default_registry, execute_tool, get_tool_schemas, parse_tool_arguments

MAX_ITERATIONS = 10


def run_agent(
    messages: list[dict[str, Any]],
    confirm: ConfirmFn,
    model: str | None = None,
    console: Console | None = None,
    on_event: EventFn | None = None,
    session_id: str | None = None,
) -> str:
    agent = Agent(
        default_registry(),
        confirm,
        model=model,
        max_iterations=MAX_ITERATIONS,
        on_event=on_event,
        console=console,
        session_id=session_id,
    )
    return agent.run(messages)


__all__ = [
    "Agent",
    "ConfirmFn",
    "EventFn",
    "MAX_ITERATIONS",
    "TOOL_REGISTRY",
    "ToolCall",
    "execute_tool",
    "get_tool_schemas",
    "parse_tool_arguments",
    "run_agent",
]