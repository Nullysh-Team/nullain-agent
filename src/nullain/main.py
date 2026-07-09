import uuid

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from nullain.agent import run_agent
from nullain.brain import Brain
from nullain.cli_helpers import confirm_action, handle_memory_command, refresh_system_message
from nullain.doctor import run_checks, score_summary, status_mark
from nullain.persona import build_session_messages
from nullain.runtime import get_active_model
from nullain import memory
from nullain.voice_session import run_voice_session

app = typer.Typer(
    name="nullain",
    help="NULLAIN — assistente pessoal de Netty.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """NULLAIN — assistente pessoal de Netty."""


@app.command("chat")
def chat(
    voice: bool = typer.Option(
        False,
        "--voice",
        help="Ativa modo voz local (Whisper + Piper).",
    ),
) -> None:
    """Inicia o REPL de chat com NULLAIN."""
    if voice:
        run_voice_session(console)
        return

    session_id = str(uuid.uuid4())
    messages: list[dict[str, str]] = build_session_messages()

    core = Brain()
    total_tools, mcp_tool_count = core.startup()

    status_lines = [
        f"Modelo ativo: [bold]{get_active_model()}[/bold]",
        f"Tools: {total_tools} ({mcp_tool_count} MCP) · Skills: {core.skill_count}",
        "Comandos: /lembra /fatos /esquece /sair",
        "Skills · Squads · Loop · Coding (tools run_*)",
        "Use --voice para modo voz local.",
        "Digite /sair para encerrar.",
    ]

    console.print(
        Panel(
            "\n".join(status_lines),
            title="NULLAIN",
            border_style="white",
        )
    )

    for error in core.mcp_errors:
        console.print(f"[yellow]MCP:[/yellow] {error}")

    try:
        _chat_loop(session_id, messages)
    finally:
        core.shutdown()


@app.command("voice")
def voice() -> None:
    """Inicia chat por voz local (faster-whisper + Piper)."""
    run_voice_session(console)


@app.command("voice-setup")
def voice_setup() -> None:
    """Baixa a voz Piper padrão em português."""
    import subprocess
    import sys

    from nullain.config import get_settings

    settings = get_settings()
    console.print(
        Panel(
            f"Baixando voz Piper: [bold]{settings.nullain_piper_voice}[/bold]",
            title="NULLAIN Voice Setup",
            border_style="white",
        )
    )
    subprocess.run(
        [sys.executable, "-m", "piper.download_voices", settings.nullain_piper_voice],
        check=True,
    )
    console.print("[green]Voz Piper pronta.[/green]")


@app.command("doctor")
def doctor() -> None:
    """Diagnostica o ambiente local do NULLAIN."""
    results = run_checks()

    table = Table(title="NULLAIN Doctor", show_header=True, header_style="bold")
    table.add_column("", width=3)
    table.add_column("Check")
    table.add_column("Detalhe")
    table.add_column("Dica", style="dim")

    for result in results:
        table.add_row(
            status_mark(result),
            result.name,
            result.detail,
            result.hint,
        )

    console.print(table)
    ok_count, total = score_summary(results)
    console.print(f"{ok_count}/{total} checks OK")


@app.command("skills")
def skills_cmd(
    reload: bool = typer.Option(False, "--reload", help="Recarrega skills do disco."),
) -> None:
    """Lista skills plugáveis (NULLAIN-SKILLS)."""
    from nullain.skills import get_skill_registry, init_skills, reload_skills

    if reload:
        count = reload_skills()
        console.print(f"[green]{count} skill(s) recarregada(s).[/green]")
    else:
        init_skills()

    registry = get_skill_registry()
    table = Table(title="NULLAIN Skills", show_header=True, header_style="bold")
    table.add_column("Nome")
    table.add_column("Handler")
    table.add_column("Confirm")
    table.add_column("Descrição")

    for skill in registry.list():
        table.add_row(
            skill.name,
            "sim" if skill.handler else "não",
            "sim" if skill.needs_confirmation else "não",
            skill.description,
        )

    if not registry.names():
        console.print("[dim]Nenhuma skill em ./skills/*/SKILL.md[/dim]")
    else:
        console.print(table)


@app.command("squad")
def squad_cmd(
    goal: str = typer.Argument(..., help="Objetivo do squad multi-agente."),
    no_llm_plan: bool = typer.Option(
        False,
        "--no-llm-plan",
        help="Usa só roteamento heurístico (sem LLM no planner).",
    ),
) -> None:
    """Executa NULLAIN-SQUADS para um objetivo complexo."""
    from nullain.config import get_settings
    from nullain.squads import SquadBudget, SquadOrchestrator

    core = Brain()
    total_tools, mcp_tool_count = core.startup()
    settings = get_settings()

    console.print(
        Panel(
            f"Objetivo: [bold]{goal}[/bold]\n"
            f"Tools: {total_tools} ({mcp_tool_count} MCP) · Skills: {core.skill_count}",
            title="NULLAIN Squad",
            border_style="white",
        )
    )

    budget = SquadBudget(
        max_roles=settings.nullain_squad_max_roles,
        max_iterations_per_agent=settings.nullain_squad_max_iterations,
        max_wall_seconds=settings.nullain_squad_max_wall_seconds,
    )
    orchestrator = SquadOrchestrator(
        budget=budget,
        use_llm_planner=not no_llm_plan,
    )

    def on_event(event: dict) -> None:
        etype = event.get("type")
        if etype == "squad_plan":
            console.print(f"[dim]Plano: {event.get('plan')}[/dim]")
        elif etype == "squad_role_start":
            console.print(
                f"[bold]▶ {event.get('role')}[/bold]: {event.get('subtask')}"
            )
        elif etype == "squad_role_end":
            mark = "✓" if event.get("ok") else "✗"
            console.print(
                f"[dim]{mark} {event.get('role')} "
                f"({event.get('duration_ms', 0):.0f}ms)[/dim]"
            )

    try:
        result = orchestrator.run(
            goal,
            confirm=lambda preview: confirm_action(console, preview),
            on_event=on_event,
        )
    finally:
        core.shutdown()

    console.print(
        Panel(
            Markdown(result.summary),
            title=f"Squad · {result.duration_ms:.0f}ms",
            border_style="white",
        )
    )


@app.command("loop")
def loop_cmd(
    goal: str = typer.Argument(..., help="Objetivo do Loop Engineering."),
    max_cycles: int = typer.Option(5, "--max-cycles", help="Máximo de ciclos."),
    checkpoint: bool = typer.Option(
        False,
        "--checkpoint",
        help="Pede confirmação humana entre ciclos.",
    ),
) -> None:
    """Loop Engineering: plan → act → evaluate → replan."""
    from nullain.config import get_settings
    from nullain.loop import EngineeringLoop, LoopBudget

    core = Brain()
    core.startup()
    settings = get_settings()

    console.print(
        Panel(
            f"Objetivo: [bold]{goal}[/bold]\n"
            f"Máx. ciclos: {max_cycles} · checkpoint={'sim' if checkpoint else 'não'}",
            title="NULLAIN Loop Engineering",
            border_style="white",
        )
    )

    budget = LoopBudget(
        max_cycles=max_cycles,
        max_iterations_per_cycle=settings.nullain_loop_max_iterations,
        max_wall_seconds=settings.nullain_loop_max_wall_seconds,
        require_checkpoint=checkpoint or settings.nullain_loop_require_checkpoint,
    )
    engine = EngineeringLoop(budget=budget)

    def on_event(event: dict) -> None:
        etype = event.get("type")
        if etype == "loop_cycle_start":
            console.print(f"[bold]▶ Ciclo {event.get('cycle')}[/bold]")
        elif etype == "loop_plan":
            console.print(f"[dim]Plano:\n{event.get('plan', '')[:500]}[/dim]")
        elif etype == "loop_cycle_end":
            mark = "✓" if event.get("done") else "…"
            console.print(
                f"[dim]{mark} ciclo {event.get('cycle')} "
                f"score={event.get('score')} "
                f"({event.get('duration_ms', 0):.0f}ms)[/dim]"
            )

    try:
        result = engine.run(
            goal,
            confirm=lambda preview: confirm_action(console, preview),
            on_event=on_event,
        )
    finally:
        core.shutdown()

    console.print(
        Panel(
            Markdown(result.final_output or result.stop_reason),
            title=(
                f"Loop · converged={result.converged} · "
                f"{result.stop_reason} · {result.duration_ms:.0f}ms"
            ),
            border_style="white",
        )
    )


@app.command("code")
def code_cmd(
    goal: str = typer.Argument(..., help="Tarefa de engenharia de software."),
    context: str = typer.Option("", "--context", help="Contexto adicional."),
) -> None:
    """NULLAIN-CODING — harness de engenharia de alto desempenho."""
    from nullain.coding import CodingBudget, CodingHarness
    from nullain.config import get_settings

    core = Brain()
    core.startup()
    settings = get_settings()

    console.print(
        Panel(
            f"Tarefa: [bold]{goal}[/bold]",
            title="NULLAIN-CODING",
            border_style="white",
        )
    )

    harness = CodingHarness(
        budget=CodingBudget(
            max_iterations=settings.nullain_coding_max_iterations,
            max_wall_seconds=settings.nullain_coding_max_wall_seconds,
        ),
        tool_names=[
            "list_files",
            "read_file",
            "write_file",
            "run_command",
            "list_skills",
            "run_skill",
        ],
    )

    try:
        result = harness.run(
            goal,
            confirm=lambda preview: confirm_action(console, preview),
            context=context,
        )
    finally:
        core.shutdown()

    body = result.output if result.ok else f"Erro: {result.error}"
    console.print(
        Panel(
            Markdown(body),
            title=f"Coding · ok={result.ok} · {result.duration_ms:.0f}ms",
            border_style="white",
        )
    )


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8420) -> None:
    """Inicia a API local do NULLAIN."""
    import uvicorn

    from nullain.config import get_settings

    token = (get_settings().nullain_api_token or "").strip()
    auth_line = (
        "Auth: [bold green]Bearer token ativo[/bold green] (NULLAIN_API_TOKEN)"
        if token
        else "Auth: [bold yellow]desligada[/bold yellow] — defina NULLAIN_API_TOKEN no .env"
    )

    console.print(
        Panel(
            f"API em [bold]http://{host}:{port}[/bold]\n"
            f"Docs: [bold]http://{host}:{port}/docs[/bold]\n"
            f"Health: [bold]http://{host}:{port}/health[/bold]\n"
            f"{auth_line}",
            title="NULLAIN serve",
            border_style="white",
        )
    )
    uvicorn.run("nullain.server:app", host=host, port=port, reload=False)


def _chat_loop(session_id: str, messages: list[dict[str, str]]) -> None:
    while True:
        try:
            user_input = console.input("[bold]Você:[/bold] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nAté logo.")
            break

        command = user_input.strip().lower()
        if command in ("/sair", "/exit", "/quit"):
            console.print("Até logo.")
            break

        if not user_input.strip():
            continue

        if handle_memory_command(console, user_input, messages):
            continue

        messages.append({"role": "user", "content": user_input})
        memory.add_message(session_id, "user", user_input)
        refresh_system_message(messages)

        try:
            response = run_agent(
                messages,
                confirm=lambda preview: confirm_action(console, preview),
                console=console,
                session_id=session_id,
            )
        except KeyboardInterrupt:
            console.print("\n[dim]Interrompido.[/dim]")
            messages.pop()
            continue
        except Exception as exc:
            console.print(f"[red]Erro:[/red] {exc}")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": response})
        memory.add_message(session_id, "assistant", response)
        console.print(
            Panel(
                Markdown(response),
                title="NULLAIN",
                border_style="white",
            )
        )