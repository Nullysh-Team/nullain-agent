import { useCallback, useEffect, useRef, useState } from "react";
import { api, type MetricPercentile, wsChatUrl } from "../api";
import { NeuralGlobe, type GlobeState } from "../components/NeuralGlobe";

const DEFAULT_CONFIRM_TIMEOUT = 120;

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  toolCalls?: ToolCallEntry[];
};

type ToolCallEntry = {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
  durationMs?: number;
  collapsed: boolean;
};

type PendingConfirmation = {
  requestId: string;
  preview: string;
  timeoutSeconds: number;
  expiresAt: number;
};

type ServerEvent = {
  type: string;
  content?: string;
  message?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  result?: string;
  duration_ms?: number;
  request_id?: string;
  preview?: string;
  timeout_seconds?: number;
  session_id?: string;
  message_count?: number;
};

function nextId() {
  return crypto.randomUUID();
}

export function ChatPage() {
  const [globeState, setGlobeState] = useState<GlobeState>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<PendingConfirmation | null>(null);
  const [confirmSecondsLeft, setConfirmSecondsLeft] = useState<number | null>(null);
  const [status, setStatus] = useState("Conectando...");
  const [isRecording, setIsRecording] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true);
  const [ttftMs, setTtftMs] = useState<number | null>(null);
  const [latencyP50, setLatencyP50] = useState<number | null>(null);
  const [sessions, setSessions] = useState<{ session_id: string; last_at: string }[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const idleTimerRef = useRef<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamingMessageRef = useRef<string | null>(null);
  const streamingContentRef = useRef<string>("");
  const toolCallsRef = useRef<ToolCallEntry[]>([]);
  const confirmTimerRef = useRef<number | null>(null);

  const scheduleIdle = useCallback(() => {
    if (idleTimerRef.current) {
      window.clearTimeout(idleTimerRef.current);
    }
    idleTimerRef.current = window.setTimeout(() => {
      setGlobeState("idle");
    }, 2200);
  }, []);

  const fetchLatency = useCallback(async () => {
    try {
      const data = await api.getMetrics(100);
      const ttftPct = data.percentiles.ttft_ms as MetricPercentile;
      setLatencyP50(ttftPct.p50);
    } catch {
      // silent
    }
  }, []);

  const resumeSession = useCallback((sid: string) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    socketRef.current.send(JSON.stringify({ type: "resume_session", session_id: sid }));
    setStatus(`Retomando sessão ${sid.slice(0, 8)}...`);
  }, []);

  useEffect(() => {
    const socket = new WebSocket(wsChatUrl());
    socketRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
      setStatus("Conectado.");
      fetchLatency();
    };

    socket.onclose = () => {
      setConnected(false);
      setStatus("Desconectado. Tentando reconectar...");
      setGlobeState("idle");
      setTimeout(() => {
        if (socketRef.current?.readyState !== WebSocket.OPEN) {
          window.location.reload();
        }
      }, 3000);
    };

    socket.onerror = () => {
      setStatus("Erro na conexão WebSocket.");
      setGlobeState("degraded");
    };

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as ServerEvent;

      switch (payload.type) {
        case "session_id":
          setSessionId(payload.session_id ?? null);
          break;
        case "session_resumed":
          setSessionId(payload.session_id ?? null);
          setStatus(`Sessão retomada (${payload.message_count ?? 0} mensagens).`);
          break;
        case "thinking":
          setGlobeState("thinking");
          streamingContentRef.current = "";
          streamingMessageRef.current = null;
          toolCallsRef.current = [];
          break;
        case "answer_chunk":
          if (payload.content) {
            streamingContentRef.current += payload.content;
            const chunkContent = streamingContentRef.current;
            setMessages((current) => {
              const existing = current.find((m) => m.streaming);
              if (existing) {
                return current.map((m) =>
                  m.streaming ? { ...m, content: chunkContent } : m,
                );
              }
              return [
                ...current,
                {
                  id: nextId(),
                  role: "assistant",
                  content: chunkContent,
                  streaming: true,
                  toolCalls: toolCallsRef.current.length > 0 ? [...toolCallsRef.current] : undefined,
                },
              ];
            });
          }
          break;
        case "tool_call":
          setGlobeState("tool_call");
          if (payload.name) {
            const entry: ToolCallEntry = {
              id: nextId(),
              name: payload.name,
              arguments: payload.arguments ?? {},
              collapsed: true,
            };
            toolCallsRef.current = [...toolCallsRef.current, entry];
            setMessages((current) => {
              const existing = current.find((m) => m.streaming);
              if (existing) {
                return current.map((m) =>
                  m.streaming
                    ? { ...m, toolCalls: [...toolCallsRef.current] }
                    : m,
                );
              }
              return current;
            });
          }
          break;
        case "tool_result":
          setGlobeState("thinking");
          if (payload.name) {
            toolCallsRef.current = toolCallsRef.current.map((tc) =>
              tc.name === payload.name && !tc.result
                ? {
                    ...tc,
                    result: payload.result,
                    durationMs: payload.duration_ms,
                  }
                : tc,
            );
            setMessages((current) =>
              current.map((m) =>
                m.streaming
                  ? { ...m, toolCalls: [...toolCallsRef.current] }
                  : m,
              ),
            );
          }
          break;
        case "confirmation_request": {
          const timeoutSeconds =
            typeof payload.timeout_seconds === "number" && payload.timeout_seconds > 0
              ? payload.timeout_seconds
              : DEFAULT_CONFIRM_TIMEOUT;
          setGlobeState("waiting_confirmation");
          setPendingConfirmation({
            requestId: payload.request_id ?? "",
            preview: payload.preview ?? "",
            timeoutSeconds,
            expiresAt: Date.now() + timeoutSeconds * 1000,
          });
          setConfirmSecondsLeft(Math.ceil(timeoutSeconds));
          break;
        }
        case "answer":
          setGlobeState("answer");
          setTtftMs(null);
          if (payload.content) {
            const finalContent = payload.content;
            const finalToolCalls = [...toolCallsRef.current];
            setMessages((current) => {
              const existing = current.find((m) => m.streaming);
              if (existing) {
                return current.map((m) =>
                  m.streaming
                    ? { ...m, content: finalContent, streaming: false, toolCalls: finalToolCalls.length > 0 ? finalToolCalls : undefined }
                    : m,
                );
              }
              return [
                ...current,
                {
                  id: nextId(),
                  role: "assistant",
                  content: finalContent,
                  toolCalls: finalToolCalls.length > 0 ? finalToolCalls : undefined,
                },
              ];
            });
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
          streamingContentRef.current = "";
          streamingMessageRef.current = null;
          toolCallsRef.current = [];
          fetchLatency();
          scheduleIdle();
          break;
        case "error":
          setStatus(payload.message ?? "Erro desconhecido.");
          setGlobeState("degraded");
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
      if (confirmTimerRef.current) {
        window.clearInterval(confirmTimerRef.current);
      }
    };
  }, [speakReplies, scheduleIdle, fetchLatency]);

  useEffect(() => {
    historyRef.current?.scrollTo({
      top: historyRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  useEffect(() => {
    api.getSessions(10).then(setSessions).catch(() => {});
  }, [messages]);

  useEffect(() => {
    if (confirmTimerRef.current) {
      window.clearInterval(confirmTimerRef.current);
      confirmTimerRef.current = null;
    }

    if (!pendingConfirmation) {
      setConfirmSecondsLeft(null);
      return;
    }

    const tick = () => {
      const leftMs = pendingConfirmation.expiresAt - Date.now();
      const left = Math.max(0, Math.ceil(leftMs / 1000));
      setConfirmSecondsLeft(left);
      if (left <= 0) {
        if (confirmTimerRef.current) {
          window.clearInterval(confirmTimerRef.current);
          confirmTimerRef.current = null;
        }
        if (socketRef.current?.readyState === WebSocket.OPEN) {
          socketRef.current.send(
            JSON.stringify({
              type: "confirmation_response",
              request_id: pendingConfirmation.requestId,
              approved: false,
            }),
          );
        }
        setPendingConfirmation(null);
        setGlobeState("thinking");
        setStatus("Confirmação expirou (negado automaticamente).");
      }
    };

    tick();
    confirmTimerRef.current = window.setInterval(tick, 250);

    return () => {
      if (confirmTimerRef.current) {
        window.clearInterval(confirmTimerRef.current);
        confirmTimerRef.current = null;
      }
    };
  }, [pendingConfirmation]);

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

    if (confirmTimerRef.current) {
      window.clearInterval(confirmTimerRef.current);
      confirmTimerRef.current = null;
    }

    socketRef.current.send(
      JSON.stringify({
        type: "confirmation_response",
        request_id: pendingConfirmation.requestId,
        approved,
      }),
    );
    setPendingConfirmation(null);
    setConfirmSecondsLeft(null);
    setGlobeState(approved ? "tool_call" : "thinking");
  }

  function toggleToolCallCollapse(messageId: string, toolCallId: string) {
    setMessages((current) =>
      current.map((m) =>
        m.id === messageId && m.toolCalls
          ? {
              ...m,
              toolCalls: m.toolCalls.map((tc) =>
                tc.id === toolCallId ? { ...tc, collapsed: !tc.collapsed } : tc,
              ),
            }
          : m,
      ),
    );
  }

  return (
    <div className="flex h-[calc(100vh-0px)] flex-col">
      <header className="mb-4 flex items-center justify-between border-b border-[#222] pb-4">
        <div>
          <h1 className="text-2xl font-light tracking-wide">NULLAIN</h1>
          <p className="mt-1 text-sm text-[#666]">Interface de comunicação</p>
        </div>
        <div className="flex items-center gap-4">
          {latencyP50 !== null && (
            <span className="font-mono text-xs text-[#666]">
              TTFT p50: {latencyP50.toFixed(0)}ms
            </span>
          )}
          {ttftMs !== null && (
            <span className="font-mono text-xs text-[#999]">
              turno: {ttftMs.toFixed(0)}ms
            </span>
          )}
          <button
            type="button"
            onClick={() => setShowSessions(!showSessions)}
            className="font-mono text-xs text-[#666] hover:text-white"
          >
            {showSessions ? "Ocultar sessões" : "Sessões"}
          </button>
          <p className="font-mono text-xs text-[#999]">
            {connected ? "online" : "offline"} · {status}
          </p>
        </div>
      </header>

      {showSessions && sessions.length > 0 && (
        <div className="mb-4 border border-[#222] bg-black/40 p-3">
          <p className="mb-2 font-mono text-[10px] tracking-[0.25em] text-[#666] uppercase">
            Sessões recentes
          </p>
          <div className="flex flex-wrap gap-2">
            {sessions.map((s) => (
              <button
                key={s.session_id}
                type="button"
                onClick={() => resumeSession(s.session_id)}
                className={[
                  "border px-3 py-1 font-mono text-xs transition",
                  s.session_id === sessionId
                    ? "border-white bg-white text-black"
                    : "border-[#444] text-[#999] hover:border-white hover:text-white",
                ].join(" ")}
              >
                {s.session_id.slice(0, 8)} · {s.last_at.slice(0, 19)}
              </button>
            ))}
          </div>
        </div>
      )}

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
              <p className="whitespace-pre-wrap font-mono leading-relaxed">
                {message.content}
                {message.streaming ? (
                  <span className="ml-1 inline-block animate-pulse">▋</span>
                ) : null}
              </p>
              {message.toolCalls && message.toolCalls.length > 0 && (
                <div className="mt-3 space-y-1 border-t border-[#222] pt-3">
                  <p className="font-mono text-[10px] tracking-[0.2em] text-[#666] uppercase">
                    Tool calls ({message.toolCalls.length})
                  </p>
                  {message.toolCalls.map((tc) => (
                    <div key={tc.id} className="border border-[#222]">
                      <button
                        type="button"
                        onClick={() => toggleToolCallCollapse(message.id, tc.id)}
                        className="flex w-full items-center justify-between px-3 py-1.5 font-mono text-xs text-[#999] hover:text-white"
                      >
                        <span>
                          {tc.collapsed ? "▸" : "▾"} {tc.name}
                          {tc.durationMs !== undefined && (
                            <span className="ml-2 text-[#666]">{tc.durationMs.toFixed(0)}ms</span>
                          )}
                        </span>
                      </button>
                      {!tc.collapsed && (
                        <div className="border-t border-[#222] px-3 py-2 font-mono text-xs text-[#999]">
                          <p className="text-[#666]">Args:</p>
                          <pre className="mt-1 whitespace-pre-wrap">
                            {JSON.stringify(tc.arguments, null, 2)}
                          </pre>
                          {tc.result && (
                            <>
                              <p className="mt-2 text-[#666]">Result:</p>
                              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap">
                                {tc.result.slice(0, 500)}
                              </pre>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
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
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-sm tracking-[0.2em] text-[#999] uppercase">
                Confirmação necessária
              </h2>
              <p
                className={[
                  "font-mono text-sm tabular-nums",
                  confirmSecondsLeft !== null && confirmSecondsLeft <= 15
                    ? "text-white"
                    : "text-[#666]",
                ].join(" ")}
              >
                {confirmSecondsLeft !== null
                  ? `${confirmSecondsLeft}s`
                  : `${pendingConfirmation.timeoutSeconds}s`}
              </p>
            </div>
            <div className="mt-3 h-1 w-full overflow-hidden border border-[#222] bg-black">
              <div
                className="h-full bg-white transition-[width] duration-200 ease-linear"
                style={{
                  width: `${
                    confirmSecondsLeft !== null && pendingConfirmation.timeoutSeconds > 0
                      ? Math.max(
                          0,
                          (confirmSecondsLeft / pendingConfirmation.timeoutSeconds) * 100,
                        )
                      : 100
                  }%`,
                }}
              />
            </div>
            <pre className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap border border-[#222] p-4 font-mono text-xs leading-relaxed text-[#ccc]">
              {pendingConfirmation.preview}
            </pre>
            <p className="mt-3 font-mono text-[10px] tracking-wide text-[#666] uppercase">
              Sem resposta → negado automaticamente
            </p>
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