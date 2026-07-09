import { useEffect, useState } from "react";
import { api } from "../api";
import { Panel } from "../components/Panel";

type SkillInfo = {
  name: string;
  description: string;
  needs_confirmation: boolean;
  tools: string[];
  has_handler: boolean;
  path: string;
};

type RoleInfo = {
  name: string;
  description: string;
  tools: string[];
  confirm_all: boolean;
};

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [status, setStatus] = useState("");
  const [squadGoal, setSquadGoal] = useState("");
  const [squadResult, setSquadResult] = useState<string>("");
  const [running, setRunning] = useState(false);

  async function load() {
    const [skillData, roleData] = await Promise.all([
      api.getSkills(),
      api.getSquadRoles(),
    ]);
    setSkills(skillData);
    setRoles(roleData);
  }

  useEffect(() => {
    load().catch((error: Error) => setStatus(error.message));
  }, []);

  async function handleReloadSkills() {
    try {
      const result = await api.reloadSkills();
      await load();
      setStatus(`Skills recarregadas: ${result.skills} · tools: ${result.tools}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao recarregar skills.");
    }
  }

  async function handleRunSquad() {
    if (!squadGoal.trim()) {
      setStatus("Informe o objetivo do squad.");
      return;
    }
    setRunning(true);
    setSquadResult("");
    try {
      const result = await api.runSquad(squadGoal.trim());
      setSquadResult(JSON.stringify(result, null, 2));
      setStatus("Squad concluído.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao rodar squad.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-light tracking-wide">Skills & Squads</h1>
          <p className="mt-2 text-sm text-[#666]">
            Capacidades plugáveis (SKILL.md) e orquestração multi-agente.
          </p>
        </div>
        <button
          type="button"
          onClick={handleReloadSkills}
          className="border border-white px-4 py-2 text-xs tracking-wide uppercase transition hover:bg-white hover:text-black"
        >
          Reload skills
        </button>
      </header>

      <Panel title={`Skills (${skills.length})`}>
        {skills.length === 0 ? (
          <p className="text-sm text-[#666]">
            Nenhuma skill. Crie pastas em <code className="text-[#999]">skills/*/SKILL.md</code>.
          </p>
        ) : (
          <ul className="space-y-3">
            {skills.map((skill) => (
              <li key={skill.name} className="border border-[#222] p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-mono text-sm text-white">{skill.name}</p>
                  <p className="font-mono text-[10px] tracking-wide text-[#666] uppercase">
                    {skill.has_handler ? "handler" : "instruções"}
                    {skill.needs_confirmation ? " · confirm" : ""}
                  </p>
                </div>
                <p className="mt-2 text-sm text-[#999]">{skill.description}</p>
                {skill.tools.length > 0 && (
                  <p className="mt-2 font-mono text-xs text-[#666]">
                    tools: {skill.tools.join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title={`Papéis SQUADS (${roles.length})`}>
        <div className="grid gap-3 md:grid-cols-3">
          {roles.map((role) => (
            <div key={role.name} className="border border-[#222] p-3">
              <p className="font-mono text-sm">{role.name}</p>
              <p className="mt-2 text-xs text-[#999]">{role.description}</p>
              <p className="mt-2 font-mono text-[10px] text-[#666]">
                {role.tools.join(", ")}
                {role.confirm_all ? " · confirm_all" : ""}
              </p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Rodar squad">
        <textarea
          value={squadGoal}
          onChange={(event) => setSquadGoal(event.target.value)}
          rows={3}
          placeholder="Ex.: pesquise a estrutura do projeto e proponha um fix no README"
          className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
        />
        <button
          type="button"
          disabled={running}
          onClick={handleRunSquad}
          className="mt-3 border border-white px-4 py-2 text-xs tracking-wide uppercase transition hover:bg-white hover:text-black disabled:border-[#444] disabled:text-[#666]"
        >
          {running ? "Executando..." : "Executar squad"}
        </button>
        {squadResult ? (
          <pre className="mt-4 max-h-80 overflow-auto border border-[#222] p-3 font-mono text-xs text-[#999]">
            {squadResult}
          </pre>
        ) : null}
      </Panel>

      {status ? <p className="text-sm text-[#999]">{status}</p> : null}
    </div>
  );
}
