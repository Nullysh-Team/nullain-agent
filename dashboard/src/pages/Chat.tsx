import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { NeuralGlobe, type GlobeState } from "../components/NeuralGlobe";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8420";
const WS_BASE = API_BASE.replace(/^http/, "ws");

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type PendingConfirmation = {
  requestId: string;
  preview: string;
};

type ServerEvent = {
  type: string;
  content?: string;
  message?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  result?: string;
  request_id?: string;
  preview?: string;
};

function nextId() {
  return crypto.randomUUID();
}

export function ChatPage() {
  const [globeState, setGlobeState] = useState<GlobeState>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<PendingConfirmation | null>(null);
  const [status, setStatus] = useState("Conectando...");
  const [isRecording, setIsRecording] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true);
  const socketRef = useRef<WebSocket | null>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const idleTimerRef = useRef<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  function scheduleIdle() {
    if (idleTimerRef.current) {
      window.clearTimeout(idleTimerRef.current);
    }
    idleTimerRef.current = window.setTimeout(() => {
      setGlobeState("idle");
    }, 2200);
  }

  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE}/ws/chat`);
    socketRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
      setStatus("Conectado.");
    };

    socket.onclose = () => {
      setConnected(false);
      setStatus("Desconectado.");
      setGlobeState("idle");
    };

    socket.onerror = () => {
      setStatus("Erro na conexão WebSocket.");
    };

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as ServerEvent;

      switch (payload.type) {
        case "thinking":
          setGlobeState("thinking");
          break;
        case "tool_call":
          setGlobeState("tool_call");
          break;
        case "tool_result":
          setGlobeState("thinking");
          break;
        case "confirmation_request":
          setPendingConfirmation({
            requestId: payload.request_id ?? "",
            preview: payload.preview ?? "",
          });
          break;
        case "answer":
          setGlobeState("answer");
          if (payload.content) {
            setMessages((current) => [
              ...current,
              { id: nextId(), role: "assistant", content: payload.content ?? "" },
            ]);
            if (speakReplies) {
              api
                .speakText(payload.content)
                .then((blob) => {
                  const url = URL.createObjectURL(blob);
                  const audio = new Audio(url);
                  audio.onended = () => URL.revokeObjectURL(url);
                  void audio.play();
                })
                .catch(() => {
                  setStatus("TTS indisponível.");
                });
            }
          }
          scheduleIdle();
          break;
        case "error":
          setStatus(payload.message ?? "Erro desconhecido.");
          scheduleIdle();
          break;
        default:
          break;
      }
    };

    return () => {
      socket.close();
      if (idleTimerRef.current) {
        window.clearTimeout(idleTimerRef.current);
      }
    };
  }, [speakReplies]);

  useEffect(() => {
    historyRef.current?.scrollTo({
      top: historyRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  function sendContent(content: string) {
    const trimmed = content.trim();
    if (!trimmed || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    setMessages((current) => [
      ...current,
      { id: nextId(), role: "user", content: trimmed },
    ]);
    socketRef.current.send(JSON.stringify({ type: "message", content: trimmed }));
    setInput("");
    setGlobeState("thinking");
    setStatus("NULLAIN pensando...");
  }

  function sendMessage() {
    sendContent(input);
  }

  async function toggleRecording() {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      setStatus("Transcrevendo...");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });

        try {
          const result = await api.transcribeAudio(blob);
          if (result.text.trim()) {
            sendContent(result.text);
          } else {
            setStatus("Não entendi o áudio.");
          }
        } catch (error) {
          setStatus(error instanceof Error ? error.message : "Erro ao transcrever.");
        }
      };

      recorder.start();
      setIsRecording(true);
      setStatus("Gravando...");
    } catch {
      setStatus("Microfone indisponível.");
    }
  }

  function respondConfirmation(approved: boolean) {
    if (!pendingConfirmation || !socketRef.current) return;

    socketRef.current.send(
      JSON.stringify({
        type: "confirmation_response",
        request_id: pendingConfirmation.requestId,
        approved,
      }),
    );
    setPendingConfirmation(null);
    setGlobeState(approved ? "tool_call" : "thinking");
  }

  return (
    <div className="flex h-[calc(100vh-0px)] flex-col">
      <header className="mb-4 flex items-center justify-between border-b border-[#222] pb-4">
        <div>
          <h1 className="text-2xl font-light tracking-wide">NULLAIN</h1>
          <p className="mt-1 text-sm text-[#666]">Interface de comunicação</p>
        </div>
        <p className="font-mono text-xs text-[#999]">
          {connected ? "online" : "offline"} · {status}
        </p>
      </header>

      <div className="relative min-h-[360px] flex-1 overflow-hidden border border-[#222] bg-black/40">
        <NeuralGlobe state={globeState} />
        <div className="pointer-events-none absolute inset-x-0 bottom-4 text-center">
          <p className="font-mono text-xs tracking-[0.35em] text-[#666] uppercase">
            {globeState}
          </p>
        </div>
      </div>

      <div
        ref={historyRef}
        className="mt-4 max-h-56 space-y-3 overflow-y-auto border border-[#222] p-4"
      >
        {messages.length === 0 ? (
          <p className="text-sm text-[#666]">
            Envie uma mensagem para iniciar a conversa com o NULLAIN.
          </p>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={[
                "border px-4 py-3 text-sm",
                message.role === "user"
                  ? "border-[#444] text-[#ccc]"
                  : "border-white/30 bg-white/5 text-white shadow-[0_0_20px_rgba(255,255,255,0.04)]",
              ].join(" ")}
            >
              <p className="mb-2 font-mono text-[10px] tracking-[0.25em] text-[#666] uppercase">
                {message.role === "user" ? "Netty" : "NULLAIN"}
              </p>
              <p className="whitespace-pre-wrap font-mono leading-relaxed">{message.content}</p>
            </article>
          ))
        )}
      </div>

      <div className="mt-3 flex items-center gap-3 text-xs text-[#666]">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={speakReplies}
            onChange={(event) => setSpeakReplies(event.target.checked)}
          />
          Falar respostas (Piper)
        </label>
      </div>

      <form
        className="mt-3 flex gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          sendMessage();
        }}
      >
        <button
          type="button"
          onClick={toggleRecording}
          disabled={!connected}
          className={[
            "border px-4 py-3 text-xs tracking-wide uppercase transition",
            isRecording
              ? "border-white bg-white text-black"
              : "border-[#666] hover:border-white",
            "disabled:border-[#444] disabled:text-[#666]",
          ].join(" ")}
        >
          {isRecording ? "Parar" : "Mic"}
        </button>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Fale com o NULLAIN..."
          disabled={!connected}
          className="flex-1 border border-[#444] bg-black px-4 py-3 font-mono text-sm outline-none transition focus:border-white disabled:opacity-40"
        />
        <button
          type="submit"
          disabled={!connected || !input.trim()}
          className="border border-white px-5 py-3 text-xs tracking-wide uppercase transition hover:bg-white hover:text-black disabled:border-[#444] disabled:text-[#666] disabled:hover:bg-transparent disabled:hover:text-[#666]"
        >
          Enviar
        </button>
      </form>

      {pendingConfirmation ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6">
          <div className="w-full max-w-xl border border-white/30 bg-black p-6 shadow-[0_0_40px_rgba(255,255,255,0.08)]">
            <h2 className="text-sm tracking-[0.2em] text-[#999] uppercase">
              Confirmação necessária
            </h2>
            <pre className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap border border-[#222] p-4 font-mono text-xs leading-relaxed text-[#ccc]">
              {pendingConfirmation.preview}
            </pre>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => respondConfirmation(false)}
                className="border border-[#666] px-4 py-2 text-xs uppercase"
              >
                Negar
              </button>
              <button
                type="button"
                onClick={() => respondConfirmation(true)}
                className="border border-white px-4 py-2 text-xs uppercase hover:bg-white hover:text-black"
              >
                Aprovar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}