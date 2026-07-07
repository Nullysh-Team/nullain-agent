import asyncio
import json
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from nullain.agent import run_agent
from nullain.brain import Brain
from nullain import env_tokens, memory
from nullain.mcp_config_store import add_server, delete_server, list_servers
from nullain.persona import get_base_prompt, get_system_message
from nullain.runtime import get_active_model
from nullain.tools import TOOL_REGISTRY

ALLOWED_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}

app = FastAPI(title="NULLAIN API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)
brain = Brain()


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
    def __init__(self) -> None:
        self._events: dict[str, threading.Event] = {}
        self._responses: dict[str, bool] = {}

    def request(self, preview: str, send_event) -> bool:
        request_id = uuid.uuid4().hex
        event = threading.Event()
        self._events[request_id] = event
        send_event(
            {
                "type": "confirmation_request",
                "request_id": request_id,
                "preview": preview,
            }
        )
        event.wait(timeout=300)
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


@app.on_event("startup")
def on_startup() -> None:
    brain.startup()


@app.on_event("shutdown")
def on_shutdown() -> None:
    brain.shutdown()


@app.get("/config")
def get_config() -> dict[str, Any]:
    runtime = memory.get_runtime_config()
    return {
        "model": runtime.get("model") or get_active_model(),
        "temperature": runtime.get("temperature"),
        "system_prompt": runtime.get("system_prompt") or get_base_prompt(),
    }


@app.put("/config")
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


@app.get("/tokens")
def get_tokens() -> list[dict[str, str]]:
    return env_tokens.list_tokens()


@app.post("/tokens")
def post_token(payload: TokenCreate) -> dict[str, str]:
    try:
        return env_tokens.set_token(payload.key, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/tokens/{key}")
def remove_token(key: str) -> dict[str, bool]:
    try:
        deleted = env_tokens.delete_token(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted}


@app.get("/memory/facts")
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


@app.post("/memory/facts")
def post_fact(payload: FactCreate) -> dict[str, Any]:
    fact = memory.add_fact(payload.value)
    return {
        "id": fact.id,
        "key": fact.key,
        "value": fact.value,
        "created_at": fact.created_at,
    }


@app.delete("/memory/facts/{fact_id}")
def remove_fact(fact_id: int) -> dict[str, bool]:
    return {"deleted": memory.delete_fact(fact_id)}


@app.get("/tools")
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


@app.get("/mcp/servers")
def get_mcp_servers() -> list[dict[str, Any]]:
    return list_servers()


@app.post("/mcp/servers")
def post_mcp_server(payload: McpServerCreate) -> dict[str, Any]:
    server = payload.model_dump(exclude_none=True)
    try:
        created = add_server(server)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    brain.reload_mcp()
    return created


@app.delete("/mcp/servers/{name}")
def remove_mcp_server(name: str) -> dict[str, bool]:
    deleted = delete_server(name)
    if deleted:
        brain.reload_mcp()
    return {"deleted": deleted}


@app.get("/logs")
def get_logs(limit: int = 50) -> list[dict[str, Any]]:
    return memory.get_tool_logs(limit=limit)


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)) -> dict[str, str]:
    from nullain.voice.stt import transcribe_file

    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    temp_path = tempfile.mktemp(suffix=suffix)

    try:
        content = await file.read()
        Path(temp_path).write_bytes(content)
        text = transcribe_file(temp_path)
        return {"text": text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        Path(temp_path).unlink(missing_ok=True)


@app.post("/voice/speak")
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

    await websocket.accept()

    session_id = str(uuid.uuid4())
    messages: list[dict[str, Any]] = [get_system_message()]
    broker = ConfirmationBroker()
    outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    async def sender() -> None:
        while True:
            event = await outbound.get()
            await websocket.send_json(event)

    sender_task = asyncio.create_task(sender())

    def send_event(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(outbound.put_nowait, event)

    def confirm(preview: str) -> bool:
        return broker.request(preview, send_event)

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