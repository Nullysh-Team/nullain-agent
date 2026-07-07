import uuid

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from nullain.agent import run_agent
from nullain.brain import Brain
from nullain.cli_helpers import confirm_action, handle_memory_command
from nullain.persona import get_system_message
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
    messages: list[dict[str, str]] = [get_system_message()]

    core = Brain()
    total_tools, mcp_tool_count = core.startup()

    status_lines = [
        f"Modelo ativo: [bold]{get_active_model()}[/bold]",
        f"Tools disponíveis: {total_tools} ({mcp_tool_count} MCP)",
        "Comandos: /lembra /fatos /esquece /sair",
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


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8420) -> None:
    """Inicia a API local do NULLAIN."""
    import uvicorn

    console.print(
        Panel(
            f"API em [bold]http://{host}:{port}[/bold]\n"
            f"Docs: [bold]http://{host}:{port}/docs[/bold]",
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