from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nullain import memory
from nullain.persona import get_facts_message, get_system_message
from nullain.ui.spinner import status


def confirm_action(console: Console, preview: str) -> bool:
    console.print(
        Panel(
            preview,
            title="Confirmação necessária",
            border_style="yellow",
        )
    )
    try:
        with status(console, "confirmation"):
            answer = console.input("Continuar? [s/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Operação cancelada.[/dim]")
        return False
    return answer in ("s", "sim", "y", "yes")


def _last_user_query(messages: list[dict[str, str]]) -> str | None:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = (message.get("content") or "").strip()
        if content:
            return content
    return None


def _is_facts_message(message: dict[str, str]) -> bool:
    if message.get("role") != "system":
        return False
    content = message.get("content") or ""
    return isinstance(content, str) and content.startswith("Fatos conhecidos")


def refresh_system_message(messages: list[dict[str, str]]) -> None:
    """Atualiza apenas o bloco de fatos — system prompt permanece estável para cache."""
    query = _last_user_query(messages)
    facts = get_facts_message(query=query)

    for index, message in enumerate(messages):
        if _is_facts_message(message):
            if facts is not None:
                messages[index] = facts
            else:
                messages.pop(index)
            return

    if facts is not None:
        if messages and messages[0]["role"] == "system":
            messages.insert(1, facts)
        else:
            messages.insert(0, get_system_message())
            messages.insert(1, facts)


def print_facts(console: Console) -> None:
    facts = memory.list_facts()
    if not facts:
        console.print("[dim]Nenhum fato gravado.[/dim]")
        return

    table = Table(title="Fatos", show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=6)
    table.add_column("Fato")
    table.add_column("Gravado em", style="dim")

    for fact in facts:
        table.add_row(str(fact.id), fact.value, fact.created_at[:19])

    console.print(table)


def handle_memory_command(
    console: Console,
    user_input: str,
    messages: list[dict[str, str]],
) -> bool:
    stripped = user_input.strip()
    lower = stripped.lower()

    if lower.startswith("/lembra "):
        fact_text = stripped[8:].strip()
        if not fact_text:
            console.print("[red]Uso:[/red] /lembra <fato>")
            return True

        fact = memory.add_fact(fact_text)
        refresh_system_message(messages)
        console.print(f"[green]Fato #{fact.id} gravado.[/green]")
        return True

    if lower == "/fatos":
        print_facts(console)
        return True

    if lower.startswith("/esquece "):
        raw_id = stripped[9:].strip()
        if not raw_id.isdigit():
            console.print("[red]Uso:[/red] /esquece <id>")
            return True

        fact_id = int(raw_id)
        if memory.delete_fact(fact_id):
            refresh_system_message(messages)
            console.print(f"[green]Fato #{fact_id} removido.[/green]")
        else:
            console.print(f"[red]Fato #{fact_id} não encontrado.[/red]")
        return True

    return False