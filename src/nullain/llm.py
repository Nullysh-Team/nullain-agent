from typing import Any

import litellm

from nullain.runtime import get_active_model, get_active_temperature


def complete(
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
) -> Any:
    active_model = model or get_active_model()
    active_temperature = temperature if temperature is not None else get_active_temperature()

    kwargs: dict[str, Any] = {
        "model": active_model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    if active_temperature is not None:
        kwargs["temperature"] = active_temperature

    return litellm.completion(**kwargs)


def chat(messages: list[dict[str, Any]], model: str | None = None) -> str:
    response = complete(messages, model=model)
    content = response.choices[0].message.content

    if not content:
        raise RuntimeError("O modelo retornou uma resposta vazia.")

    return content