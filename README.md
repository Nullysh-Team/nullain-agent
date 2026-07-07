# NULLAIN Agent Jarvis

Assistente pessoal de Netty — CLI em Python com LiteLLM.

## Requisitos

- Python 3.12+ (gerenciado pelo `uv`)
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
cp .env.example .env
# Edite .env com NULLAIN_MODEL e chaves de API do provider escolhido
uv sync
```

## Uso

```bash
uv run nullain chat
```

Comandos no chat:

- `/sair` — encerra a sessão

## Fase atual

**Fase 9** — voz local 100% offline (faster-whisper + Piper).

```bash
uv pip install -e .
uv run nullain voice-setup
uv run nullain voice
# ou: uv run nullain chat --voice
```

API: `POST /voice/transcribe`, `POST /voice/speak`. Dashboard: botão Mic + "Falar respostas".