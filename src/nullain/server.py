import asyncio
import os
import secrets
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from nullain.agent import run_agent
from nullain.brain import Brain
from nullain import env_tokens, memory
from nullain.config import get_settings
from nullain.core_agent import CONFIRM_TIMEOUT_SECONDS
from nullain.mcp_config_store import add_server, delete_server
from nullain.cli_helpers import refresh_system_message
from nullain.persona import build_session_messages, get_base_prompt
from nullain.runtime import get_active_model
from nullain.tools import TOOL_REGISTRY

ALLOWED_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}

brain = Brain()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    brain.startup()
    try:
        yield
    finally:
        brain.shutdown()


app = FastAPI(title="NULLAIN API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _expected_api_token() -> str:
    return (get_settings().nullain_api_token or "").strip()


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _tokens_match(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def require_api_token(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    """Quando NULLAIN_API_TOKEN está definido, exige Bearer ou ?token=."""
    expected = _expected_api_token()
    if not expected:
        return
    provided = _extract_bearer(authorization) or (token.strip() if token else None)
    if not _tokens_match(provided, expected):
        raise HTTPException(status_code=401, detail="Não autorizado. Envie Authorization: Bearer <NULLAIN_API_TOKEN>.")


def _confirm_timeout_seconds() -> float:
    settings = get_settings()
    configured = getattr(settings, "nullain_confirm_timeout_seconds", None)
    if configured is not None and configured > 0:
        return float(configured)
    return float(CONFIRM_TIMEOUT_SECONDS)


class RuntimeConfigUpdate(BaseModel):
    model: str | None = None
    temperature: float | None = None
    system_prompt: str | None = None


class FactCreate(BaseModel):
    value: str


class TokenCreate(BaseModel):
    key: str
    value: str


class McpServerCreate(BaseModel):
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class VoiceSpeakRequest(BaseModel):
    text: str


class ConfirmationBroker:
    """Serializa confirmações: no máximo um modal pendente por vez."""

    def __init__(self, timeout_seconds: float | None = None) -> None:
        self._events: dict[str, threading.Event] = {}
        self._responses: dict[str, bool] = {}
        self._gate = threading.Lock()
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else _confirm_timeout_seconds()
        )

    def request(self, preview: str, send_event) -> bool:
        with self._gate:
            request_id = uuid.uuid4().hex
            event = threading.Event()
            self._events[request_id] = event
            send_event(
                {
                    "type": "confirmation_request",
                    "request_id": request_id,
                    "preview": preview,
                    "timeout_seconds": self._timeout_seconds,
                }
            )
            event.wait(timeout=self._timeout_seconds)
            approved = self._responses.pop(request_id, False)
            self._events.pop(request_id, None)
            return approved

    def respond(self, request_id: str, approved: bool) -> bool:
        event = self._events.get(request_id)
        if event is None:
            return False
        self._responses[request_id] = approved
        event.set()
        return True


@app.get("/health")
def health() -> dict[str, Any]:
    """Health público (sem auth) para doctor e probes."""
    from nullain.workspace import get_workspace_root

    return {
        "status": "ok",
        "auth_required": bool(_expected_api_token()),
        "workspace": str(get_workspace_root()),
    }


@app.get("/config", dependencies=[Depends(require_api_token)])
def get_config() -> dict[str, Any]:
    runtime = memory.get_runtime_config()
    return {
        "model": runtime.get("model") or get_active_model(),
        "temperature": runtime.get("temperature"),
        "system_prompt": runtime.get("system_prompt") or get_base_prompt(),
    }


@app.put("/config", dependencies=[Depends(require_api_token)])
def put_config(payload: RuntimeConfigUpdate) -> dict[str, Any]:
    updated = memory.update_runtime_config(
        model=payload.model,
        temperature=payload.temperature,
        system_prompt=payload.system_prompt,
    )
    return {
        "model": updated.get("model") or get_active_model(),
        "temperature": updated.get("temperature"),
        "system_prompt": updated.get("system_prompt") or get_base_prompt(),
    }


@app.get("/tokens", dependencies=[Depends(require_api_token)])
def get_tokens() -> list[dict[str, str]]:
    return env_tokens.list_tokens()


@app.post("/tokens", dependencies=[Depends(require_api_token)])
def post_token(payload: TokenCreate) -> dict[str, str]:
    try:
        return env_tokens.set_token(payload.key, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/tokens/{key}", dependencies=[Depends(require_api_token)])
def remove_token(key: str) -> dict[str, bool]:
    try:
        deleted = env_tokens.delete_token(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted}


@app.get("/memory/facts", dependencies=[Depends(require_api_token)])
def get_facts() -> list[dict[str, Any]]:
    return [
        {
            "id": fact.id,
            "key": fact.key,
            "value": fact.value,
            "created_at": fact.created_at,
        }
        for fact in memory.list_facts()
    ]


@app.post("/memory/facts", dependencies=[Depends(require_api_token)])
def post_fact(payload: FactCreate) -> dict[str, Any]:
    fact = memory.add_fact(payload.value)
    return {
        "id": fact.id,
        "key": fact.key,
        "value": fact.value,
        "created_at": fact.created_at,
    }


@app.delete("/memory/facts/{fact_id}", dependencies=[Depends(require_api_token)])
def remove_fact(fact_id: int) -> dict[str, bool]:
    return {"deleted": memory.delete_fact(fact_id)}


@app.get("/tools", dependencies=[Depends(require_api_token)])
def get_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, entry in TOOL_REGISTRY.items():
        schema = entry["schema"]["function"]
        tools.append(
            {
                "name": name,
                "description": schema.get("description", ""),
                "source": entry.get("source", "native"),
                "needs_confirmation": entry.get("needs_confirmation", False),
            }
        )
    return tools


@app.get("/mcp/servers", dependencies=[Depends(require_api_token)])
def get_mcp_servers() -> list[dict[str, Any]]:
    from nullain.mcp_config_store import list_servers as _list_raw

    servers = _list_raw()
    status_map = {s["name"]: s for s in brain.mcp_server_status}
    for server in servers:
        name = server.get("name", "")
        if name in status_map:
            server["status"] = status_map[name]
    return servers


@app.post("/mcp/servers", dependencies=[Depends(require_api_token)])
def post_mcp_server(payload: McpServerCreate) -> dict[str, Any]:
    server = payload.model_dump(exclude_none=True)
    try:
        created = add_server(server)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    brain.add_mcp_server(created)
    return created


@app.delete("/mcp/servers/{name}", dependencies=[Depends(require_api_token)])
def remove_mcp_server(name: str) -> dict[str, bool]:
    deleted = delete_server(name)
    if deleted:
        brain.remove_mcp_server(name)
    return {"deleted": deleted}


@app.get("/logs", dependencies=[Depends(require_api_token)])
def get_logs(limit: int = 50) -> list[dict[str, Any]]:
    return memory.get_tool_logs(limit=limit)


@app.get("/metrics", dependencies=[Depends(require_api_token)])
def get_metrics(limit: int = 50) -> dict[str, Any]:
    return {
        "turns": memory.get_metrics(limit=limit),
        "percentiles": {
            "ttft_ms": memory.get_metric_percentiles("ttft_ms", limit=limit),
            "total_ms": memory.get_metric_percentiles("total_ms", limit=limit),
            "tool_total_ms": memory.get_metric_percentiles("tool_total_ms", limit=limit),
        },
    }


@app.get("/sessions", dependencies=[Depends(require_api_token)])
def get_sessions(limit: int = 20) -> list[dict[str, Any]]:
    return memory.list_sessions(limit=limit)


@app.get("/sessions/{session_id}", dependencies=[Depends(require_api_token)])
def get_session_messages_route(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return memory.get_session_messages(session_id, limit=limit)


@app.post("/voice/transcribe", dependencies=[Depends(require_api_token)])
async def voice_transcribe(file: UploadFile = File(...)) -> dict[str, str]:
    from nullain.voice.stt import transcribe_file

    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        content = await file.read()
        Path(temp_path).write_bytes(content)
        text = transcribe_file(temp_path)
        return {"text": text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        Path(temp_path).unlink(missing_ok=True)


@app.post("/voice/speak", dependencies=[Depends(require_api_token)])
def voice_speak(payload: VoiceSpeakRequest) -> Response:
    from nullain.voice.tts import synthesize_wav_bytes

    try:
        wav = synthesize_wav_bytes(payload.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(content=wav, media_type="audio/wav")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    expected = _expected_api_token()
    if expected:
        query_token = websocket.query_params.get("token")
        header_auth = websocket.headers.get("authorization")
        provided = _extract_bearer(header_auth) or (query_token.strip() if query_token else None)
        if not _tokens_match(provided, expected):
            await websocket.close(code=1008)
            return

    await websocket.accept()

    session_id = str(uuid.uuid4())
    messages: list[dict[str, Any]] = build_session_messages()
    broker = ConfirmationBroker(timeout_seconds=_confirm_timeout_seconds())
    outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    async def sender() -> None:
        try:
            while True:
                event = await outbound.get()
                await websocket.send_json(event)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    sender_task = asyncio.create_task(sender())

    def send_event(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(outbound.put_nowait, event)

    def confirm(preview: str) -> bool:
        return broker.request(preview, send_event)

    await websocket.send_json({"type": "session_id", "session_id": session_id})

    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")

            if event_type == "confirmation_response":
                broker.respond(
                    payload.get("request_id", ""),
                    bool(payload.get("approved")),
                )
                continue

            if event_type == "resume_session":
                resume_id = str(payload.get("session_id", "")).strip()
                if resume_id:
                    existing = memory.get_session_messages(resume_id, limit=200)
                    if existing:
                        session_id = resume_id
                        messages = build_session_messages()
                        for msg in existing:
                            messages.append({
                                "role": msg["role"],
                                "content": msg["content"],
                            })
                        await websocket.send_json({
                            "type": "session_resumed",
                            "session_id": session_id,
                            "message_count": len(existing),
                        })
                continue

            if event_type != "message":
                await websocket.send_json(
                    {"type": "error", "message": f"Evento desconhecido: {event_type}"}
                )
                continue

            content = str(payload.get("content", "")).strip()
            if not content:
                continue

            messages.append({"role": "user", "content": content})
            memory.add_message(session_id, "user", content)
            refresh_system_message(messages)

            def on_event(event: dict[str, Any]) -> None:
                send_event(event)

            try:
                await asyncio.to_thread(
                    run_agent,
                    messages,
                    confirm,
                    None,
                    None,
                    on_event,
                    session_id,
                )
                assistant = messages[-1]
                if assistant.get("role") == "assistant":
                    memory.add_message(session_id, "assistant", assistant["content"])
            except Exception as exc:
                messages.pop()
                await websocket.send_json({"type": "error", "message": str(exc)})

    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass