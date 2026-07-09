const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8420";
/** Token local da API (mesmo valor de NULLAIN_API_TOKEN no backend). */
export const API_TOKEN = (import.meta.env.VITE_NULLAIN_API_TOKEN as string | undefined) ?? "";

function authHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    ...(extra as Record<string, string> | undefined),
  };
  if (API_TOKEN) {
    headers.Authorization = `Bearer ${API_TOKEN}`;
  }
  return headers;
}

export function wsChatUrl(): string {
  const wsBase = API_BASE.replace(/^http/, "ws");
  if (!API_TOKEN) {
    return `${wsBase}/ws/chat`;
  }
  const params = new URLSearchParams({ token: API_TOKEN });
  return `${wsBase}/ws/chat?${params.toString()}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Erro ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export type RuntimeConfig = {
  model: string;
  temperature: number | null;
  system_prompt: string;
};

export type TokenEntry = {
  key: string;
  masked: string;
};

export type Fact = {
  id: number;
  key: string;
  value: string;
  created_at: string;
};

export type ToolInfo = {
  name: string;
  description: string;
  source: string;
  needs_confirmation: boolean;
};

export type McpServer = {
  name: string;
  transport: string;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
};

export type ToolLog = {
  id: number;
  tool_name: string;
  arguments: Record<string, unknown>;
  result: string;
  session_id: string | null;
  created_at: string;
};

export type MetricTurn = {
  id: number;
  session_id: string | null;
  turn_index: number;
  ttft_ms: number | null;
  total_ms: number;
  iterations: number;
  tokens_in: number | null;
  tokens_out: number | null;
  tool_count: number;
  tool_total_ms: number;
  model: string | null;
  created_at: string;
};

export type MetricPercentile = {
  p50: number | null;
  p90: number | null;
  p95: number | null;
  p99: number | null;
  count: number;
};

export type MetricsResponse = {
  turns: MetricTurn[];
  percentiles: {
    ttft_ms: MetricPercentile;
    total_ms: MetricPercentile;
    tool_total_ms: MetricPercentile;
  };
};

export type SessionInfo = {
  session_id: string;
  first_at: string;
  last_at: string;
  message_count: number;
  user_count: number;
};

export type SessionMessage = {
  id: number;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
};

export type McpServerStatus = {
  name: string;
  state: string;
  last_error: string;
  tool_count: number;
  reconnect_attempts: number;
};

export type McpServerWithStatus = McpServer & {
  status?: McpServerStatus;
};

export const api = {
  getConfig: () => request<RuntimeConfig>("/config"),
  putConfig: (payload: Partial<RuntimeConfig>) =>
    request<RuntimeConfig>("/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getTokens: () => request<TokenEntry[]>("/tokens"),
  addToken: (key: string, value: string) =>
    request<TokenEntry>("/tokens", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),
  deleteToken: (key: string) =>
    request<{ deleted: boolean }>(`/tokens/${key}`, { method: "DELETE" }),
  getFacts: () => request<Fact[]>("/memory/facts"),
  addFact: (value: string) =>
    request<Fact>("/memory/facts", {
      method: "POST",
      body: JSON.stringify({ value }),
    }),
  deleteFact: (id: number) =>
    request<{ deleted: boolean }>(`/memory/facts/${id}`, { method: "DELETE" }),
  getTools: () => request<ToolInfo[]>("/tools"),
  getMcpServers: () => request<McpServerWithStatus[]>("/mcp/servers"),
  addMcpServer: (server: McpServer) =>
    request<McpServer>("/mcp/servers", {
      method: "POST",
      body: JSON.stringify(server),
    }),
  deleteMcpServer: (name: string) =>
    request<{ deleted: boolean }>(`/mcp/servers/${name}`, { method: "DELETE" }),
  getLogs: (limit = 50) => request<ToolLog[]>(`/logs?limit=${limit}`),
  getMetrics: (limit = 50) =>
    request<MetricsResponse>(`/metrics?limit=${limit}`),
  getSessions: (limit = 20) =>
    request<SessionInfo[]>(`/sessions?limit=${limit}`),
  getSessionMessages: (sessionId: string, limit = 100) =>
    request<SessionMessage[]>(`/sessions/${sessionId}?limit=${limit}`),
  transcribeAudio: async (blob: Blob) => {
    const form = new FormData();
    form.append("file", blob, "audio.webm");
    const response = await fetch(`${API_BASE}/voice/transcribe`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json() as Promise<{ text: string }>;
  },
  speakText: async (text: string) => {
    const response = await fetch(`${API_BASE}/voice/speak`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.blob();
  },
};

export const MODEL_OPTIONS = [
  "ollama/glm-5.2:cloud",
  "ollama/llama3.2",
  "groq/llama-3.3-70b-versatile",
  "anthropic/claude-sonnet-4-20250514",
  "openai/gpt-4o",
  "xai/grok-2-latest",
];

export const TOKEN_OPTIONS = [
  "ANTHROPIC_API_KEY",
  "OPENAI_API_KEY",
  "XAI_API_KEY",
  "GROQ_API_KEY",
  "GEMINI_API_KEY",
  "OPENROUTER_API_KEY",
];