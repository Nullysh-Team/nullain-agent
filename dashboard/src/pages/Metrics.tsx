import { useEffect, useState } from "react";
import { api, type MetricsResponse } from "../api";

export function MetricsPage() {
  const [data, setData] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const poll = () => {
      api
        .getMetrics(100)
        .then((d) => {
          if (active) {
            setData(d);
            setLoading(false);
          }
        })
        .catch((e) => {
          if (active) {
            setError(e instanceof Error ? e.message : "Erro");
            setLoading(false);
          }
        });
    };
    poll();
    const interval = setInterval(poll, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  if (loading) return <p className="text-sm text-[#666]">Carregando métricas...</p>;
  if (error) return <p className="text-sm text-red-400">{error}</p>;
  if (!data) return null;

  const { turns, percentiles } = data;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-light tracking-wide">Métricas</h1>
        <p className="mt-1 text-sm text-[#666]">
          Latência e throughput dos últimos turnos
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <PercentileCard title="TTFT" data={percentiles.ttft_ms} unit="ms" />
        <PercentileCard title="Turno total" data={percentiles.total_ms} unit="ms" />
        <PercentileCard title="Tools total" data={percentiles.tool_total_ms} unit="ms" />
      </div>

      <div>
        <h2 className="mb-3 text-sm tracking-[0.2em] text-[#999] uppercase">
          Turnos recentes ({turns.length})
        </h2>
        <div className="overflow-x-auto border border-[#222]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#222] text-left text-[10px] tracking-[0.2em] text-[#666] uppercase">
                <th className="px-3 py-2">Turno</th>
                <th className="px-3 py-2">TTFT</th>
                <th className="px-3 py-2">Total</th>
                <th className="px-3 py-2">Iter</th>
                <th className="px-3 py-2">Tokens in</th>
                <th className="px-3 py-2">Tokens out</th>
                <th className="px-3 py-2">Tools</th>
                <th className="px-3 py-2">Modelo</th>
              </tr>
            </thead>
            <tbody>
              {turns.map((t) => (
                <tr key={t.id} className="border-b border-[#222] font-mono text-xs">
                  <td className="px-3 py-2 text-[#666]">{t.turn_index}</td>
                  <td className="px-3 py-2">
                    {t.ttft_ms !== null ? `${t.ttft_ms.toFixed(0)}ms` : "—"}
                  </td>
                  <td className="px-3 py-2">{t.total_ms.toFixed(0)}ms</td>
                  <td className="px-3 py-2 text-[#666]">{t.iterations}</td>
                  <td className="px-3 py-2 text-[#666]">{t.tokens_in ?? "—"}</td>
                  <td className="px-3 py-2 text-[#666]">{t.tokens_out ?? "—"}</td>
                  <td className="px-3 py-2 text-[#666]">{t.tool_count}</td>
                  <td className="px-3 py-2 text-[#666]">{t.model ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function PercentileCard({
  title,
  data,
  unit,
}: {
  title: string;
  data: { p50: number | null; p90: number | null; p95: number | null; p99: number | null; count: number };
  unit: string;
}) {
  return (
    <div className="border border-[#222] p-4">
      <p className="mb-3 font-mono text-[10px] tracking-[0.2em] text-[#666] uppercase">
        {title} ({data.count} amostras)
      </p>
      <div className="grid grid-cols-4 gap-2">
        <Stat label="p50" value={data.p50} unit={unit} />
        <Stat label="p90" value={data.p90} unit={unit} />
        <Stat label="p95" value={data.p95} unit={unit} />
        <Stat label="p99" value={data.p99} unit={unit} />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null;
  unit: string;
}) {
  return (
    <div>
      <p className="font-mono text-[10px] text-[#666] uppercase">{label}</p>
      <p className="font-mono text-sm text-white">
        {value !== null ? `${value.toFixed(0)}${unit}` : "—"}
      </p>
    </div>
  );
}