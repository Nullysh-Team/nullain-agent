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


def get_base_prompt() -> str:
    from nullain.memory import get_setting

    custom = get_setting("system_prompt")
    if custom and custom.strip():
        return custom.strip()
    return SYSTEM_PROMPT


def get_system_message() -> dict[str, str]:
    from nullain.memory import format_facts_for_prompt

    content = get_base_prompt()
    facts_block = format_facts_for_prompt()
    if facts_block:
        content = f"{content}\n\n{facts_block}"

    return {"role": "system", "content": content}