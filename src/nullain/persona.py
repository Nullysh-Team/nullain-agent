import platform

_WINDOWS_HINT = (
    " O ambiente é Windows — em run_command use PowerShell ou cmd "
    "(ex.: Get-PSDrive, wmic logicaldisk get caption,freespace,size). "
    "Nunca use comandos Unix como df, ls ou du."
)

SYSTEM_PROMPT = (
    "Você é NULLAIN, assistente pessoal de Netty. "
    "Direto, preciso, responde em português."
    + (_WINDOWS_HINT if platform.system() == "Windows" else "")
)

FACTS_HEADER = "Fatos conhecidos sobre Netty:"


def get_base_prompt() -> str:
    from nullain.memory import get_setting

    custom = get_setting("system_prompt")
    if custom and custom.strip():
        return custom.strip()
    return SYSTEM_PROMPT


def get_system_message(query: str | None = None) -> dict[str, str]:
    """System prompt estável — NÃO inclui fatos dinâmicos.

    Para cache de prompt do provider, o system prompt deve ser fixo por sessão.
    Fatos são injetados como mensagem separada via ``get_facts_message``.
    """
    content = get_base_prompt()
    return {"role": "system", "content": content}


def get_facts_message(query: str | None = None) -> dict[str, str] | None:
    """Mensagem de fatos como bloco separado — não invalida cache do system prompt."""
    from nullain.memory import format_facts_for_prompt

    facts_block = format_facts_for_prompt(query=query)
    if not facts_block:
        return None

    return {"role": "system", "content": facts_block}


def build_session_messages(query: str | None = None) -> list[dict[str, str]]:
    """Constrói mensagens iniciais: system prompt estável + fatos (se houver)."""
    messages = [get_system_message()]
    facts = get_facts_message(query=query)
    if facts is not None:
        messages.append(facts)
    return messages