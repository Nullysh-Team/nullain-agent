import { useEffect, useMemo, useState } from "react";
import { api, MODEL_OPTIONS } from "../api";
import { Field } from "../components/Field";
import { Panel } from "../components/Panel";

export function BrainPage() {
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState("0.7");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getConfig()
      .then((config) => {
        setModel(config.model);
        setTemperature(
          config.temperature !== null ? String(config.temperature) : "0.7",
        );
        setSystemPrompt(config.system_prompt);
      })
      .catch((error: Error) => setStatus(error.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setStatus("Salvando...");
    try {
      const saved = await api.putConfig({
        model,
        temperature: Number(temperature),
        system_prompt: systemPrompt,
      });
      setModel(saved.model);
      setTemperature(
        saved.temperature !== null ? String(saved.temperature) : temperature,
      );
      setSystemPrompt(saved.system_prompt);
      setStatus("Configuração salva.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao salvar.");
    }
  }

  const modelOptions = useMemo(() => {
    if (model && !MODEL_OPTIONS.includes(model)) {
      return [model, ...MODEL_OPTIONS];
    }
    return MODEL_OPTIONS;
  }, [model]);

  if (loading) {
    return <p className="text-[#999]">Carregando cérebro...</p>;
  }

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-light tracking-wide">Cérebro</h1>
        <p className="mt-2 text-sm text-[#666]">
          Modelo, temperatura e persona do NULLAIN.
        </p>
      </header>

      <Panel
        title="Configuração ativa"
        action={
          <button
            type="button"
            onClick={handleSave}
            className="border border-white px-4 py-2 text-xs tracking-wide uppercase transition hover:bg-white hover:text-black"
          >
            Salvar
          </button>
        }
      >
        <div className="space-y-5">
          <Field label="Modelo ativo">
            <select
              value={model}
              onChange={(event) => setModel(event.target.value)}
              className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
            >
              {modelOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Temperatura" hint="0 = preciso, 1 = criativo">
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={temperature}
              onChange={(event) => setTemperature(event.target.value)}
              className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
            />
          </Field>

          <Field label="System prompt">
            <textarea
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
              rows={10}
              className="w-full resize-y border border-[#444] bg-black px-3 py-2 font-mono text-sm leading-relaxed outline-none focus:border-white"
            />
          </Field>

          {status ? <p className="text-sm text-[#999]">{status}</p> : null}
        </div>
      </Panel>
    </div>
  );
}