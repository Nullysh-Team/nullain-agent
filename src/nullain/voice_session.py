import os
import uuid

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from nullain.agent import run_agent
from nullain.brain import Brain
from nullain import memory
from nullain.cli_helpers import confirm_action, handle_memory_command, refresh_system_message
from nullain.persona import build_session_messages
from nullain.runtime import get_active_model
from nullain.voice.audio import play_wav_bytes, record_seconds
from nullain.voice.stt import transcribe_file
from nullain.ui.spinner import status
from nullain.voice.tts import resolve_piper_model_path, synthesize_wav_bytes


def run_voice_session(console: Console) -> None:
    session_id = str(uuid.uuid4())
    messages: list[dict[str, str]] = build_session_messages()

    core = Brain()
    total_tools, mcp_tool_count = core.startup()

    try:
        piper_path = resolve_piper_model_path()
        piper_info = str(piper_path)
    except FileNotFoundError as exc:
        piper_info = f"[red]{exc}[/red]"

    console.print(
        Panel(
            f"Modelo ativo: [bold]{get_active_model()}[/bold]\n"
            f"Tools disponíveis: {total_tools} ({mcp_tool_count} MCP)\n"
            f"Piper: {piper_info}\n"
            "Enter = gravar e falar · texto = digitar · /sair = encerrar",
            title="NULLAIN Voice",
            border_style="white",
        )
    )

    for error in core.mcp_errors:
        console.print(f"[yellow]MCP:[/yellow] {error}")

    try:
        _voice_loop(console, session_id, messages)
    finally:
        core.shutdown()


def _voice_loop(
    console: Console,
    session_id: str,
    messages: list[dict[str, str]],
) -> None:
    while True:
        try:
            user_input = console.input(
                "[bold]Você[/bold] (Enter=falar, texto=digitar): "
            )
        except (EOFError, KeyboardInterrupt):
            console.print("\nAté logo.")
            break

        command = user_input.strip().lower()
        if command in ("/sair", "/exit", "/quit"):
            console.print("Até logo.")
            break

        if user_input.strip() and handle_memory_command(console, user_input, messages):
            continue

        if not user_input.strip():
            try:
                with status(console, "thinking", text="[bold]Gravando...[/bold]"):
                    audio_path = record_seconds()
                with status(console, "thinking", text="[bold]Transcrevendo...[/bold]"):
                    user_text = transcribe_file(audio_path)
                os.remove(audio_path)
            except Exception as exc:
                console.print(f"[red]Erro de voz:[/red] {exc}")
                continue

            if not user_text:
                console.print("[dim]Não entendi. Tente novamente.[/dim]")
                continue

            console.print(f"[dim]Você disse:[/dim] {user_text}")
        else:
            user_text = user_input.strip()

        messages.append({"role": "user", "content": user_text})
        memory.add_message(session_id, "user", user_text)
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

        try:
            with status(console, "thinking", text="[bold]Falando...[/bold]"):
                wav = synthesize_wav_bytes(response)
                play_wav_bytes(wav)
        except Exception as exc:
            console.print(f"[yellow]TTS indisponível:[/yellow] {exc}")