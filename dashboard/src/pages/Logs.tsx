import { useEffect, useState } from "react";
import { api, type ToolLog } from "../api";
import { Panel } from "../components/Panel";

export function LogsPage() {
  const [logs, setLogs] = useState<ToolLog[]>([]);
  const [status, setStatus] = useState("");

  useEffect(() => {
    api
      .getLogs()
      .then(setLogs)
      .catch((error: Error) => setStatus(error.message));
  }, []);

  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-light tracking-wide">Logs</h1>
        <p className="mt-2 text-sm text-[#666]">
          Últimas execuções de tools registradas pelo núcleo.
        </p>
      </header>

      <Panel title="Tool calls recentes">
        {logs.length === 0 ? (
          <p className="text-sm text-[#666]">Nenhum log registrado ainda.</p>
        ) : (
          <div className="space-y-4">
            {logs.map((log) => (
              <article key={log.id} className="border border-[#222] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-mono text-sm">{log.tool_name}</p>
                  <p className="font-mono text-xs text-[#666]">
                    {log.created_at.slice(0, 19)}
                  </p>
                </div>
                <pre className="mt-3 overflow-x-auto border border-[#111] bg-black p-3 font-mono text-xs leading-relaxed text-[#999]">
                  {JSON.stringify(log.arguments, null, 2)}
                </pre>
                <pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#ccc]">
                  {log.result}
                </pre>
              </article>
            ))}
          </div>
        )}
      </Panel>

      {status ? <p className="text-sm text-[#999]">{status}</p> : null}
    </div>
  );
}