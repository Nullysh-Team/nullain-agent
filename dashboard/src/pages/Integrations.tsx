import { useEffect, useMemo, useState } from "react";
import { api, type McpServer, type ToolInfo } from "../api";
import { Field } from "../components/Field";
import { Panel } from "../components/Panel";

const emptyServer: McpServer = {
  name: "",
  transport: "stdio",
  command: "python",
  args: [],
  env: {},
};

export function IntegrationsPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [draft, setDraft] = useState<McpServer>(emptyServer);
  const [argsText, setArgsText] = useState("");
  const [status, setStatus] = useState("");

  async function loadData() {
    const [serverData, toolData] = await Promise.all([
      api.getMcpServers(),
      api.getTools(),
    ]);
    setServers(serverData);
    setTools(toolData);
  }

  useEffect(() => {
    loadData().catch((error: Error) => setStatus(error.message));
  }, []);

  const toolsByServer = useMemo(() => {
    const map = new Map<string, ToolInfo[]>();
    for (const tool of tools) {
      if (tool.source !== "mcp") continue;
      const [serverName] = tool.name.split("__");
      const current = map.get(serverName) ?? [];
      current.push(tool);
      map.set(serverName, current);
    }
    return map;
  }, [tools]);

  async function handleAdd() {
    if (!draft.name.trim()) {
      setStatus("Informe o nome do servidor.");
      return;
    }

    const payload: McpServer = {
      ...draft,
      name: draft.name.trim(),
      args: argsText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    };

    try {
      await api.addMcpServer(payload);
      setDraft(emptyServer);
      setArgsText("");
      await loadData();
      setStatus("Servidor MCP adicionado.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao adicionar servidor.");
    }
  }

  async function handleDelete(name: string) {
    try {
      await api.deleteMcpServer(name);
      await loadData();
      setStatus(`Servidor ${name} removido.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao remover servidor.");
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-light tracking-wide">Integrações</h1>
        <p className="mt-2 text-sm text-[#666]">
          Servidores MCP configurados e tools expostas por servidor.
        </p>
      </header>

      <Panel title="Adicionar servidor">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Nome">
            <input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
            />
          </Field>

          <Field label="Transporte">
            <select
              value={draft.transport}
              onChange={(event) =>
                setDraft({ ...draft, transport: event.target.value })
              }
              className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
            >
              <option value="stdio">stdio</option>
              <option value="sse">sse</option>
              <option value="streamable-http">streamable-http</option>
            </select>
          </Field>

          {draft.transport === "stdio" ? (
            <>
              <Field label="Comando">
                <input
                  value={draft.command ?? ""}
                  onChange={(event) =>
                    setDraft({ ...draft, command: event.target.value })
                  }
                  className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
                />
              </Field>
              <Field label="Args" hint="Separados por vírgula">
                <input
                  value={argsText}
                  onChange={(event) => setArgsText(event.target.value)}
                  className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
                />
              </Field>
            </>
          ) : (
            <Field label="URL">
              <input
                value={draft.url ?? ""}
                onChange={(event) => setDraft({ ...draft, url: event.target.value })}
                className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
              />
            </Field>
          )}
        </div>

        <button
          type="button"
          onClick={handleAdd}
          className="mt-4 border border-white px-4 py-2 text-xs tracking-wide uppercase transition hover:bg-white hover:text-black"
        >
          Adicionar servidor
        </button>
      </Panel>

      <Panel title="Servidores ativos">
        {servers.length === 0 ? (
          <p className="text-sm text-[#666]">Nenhum servidor MCP configurado.</p>
        ) : (
          <div className="space-y-4">
            {servers.map((server) => {
              const exposed = toolsByServer.get(server.name) ?? [];
              const connected = exposed.length > 0;

              return (
                <div key={server.name} className="border border-[#222] p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-mono text-sm">{server.name}</p>
                      <p className="mt-1 text-xs text-[#999]">
                        {server.transport}
                        {server.command ? ` · ${server.command}` : ""}
                        {server.url ? ` · ${server.url}` : ""}
                      </p>
                      <p className="mt-2 text-xs uppercase tracking-wide text-[#666]">
                        Status: {connected ? "conectado" : "sem tools carregadas"}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDelete(server.name)}
                      className="border border-[#666] px-3 py-1 text-xs uppercase transition hover:border-white"
                    >
                      Remover
                    </button>
                  </div>

                  {exposed.length > 0 ? (
                    <ul className="mt-4 space-y-2 border-t border-[#222] pt-4">
                      {exposed.map((tool) => (
                        <li key={tool.name} className="font-mono text-xs text-[#999]">
                          {tool.name}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      {status ? <p className="text-sm text-[#999]">{status}</p> : null}
    </div>
  );
}