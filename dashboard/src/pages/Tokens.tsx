import { useEffect, useState } from "react";
import { api, TOKEN_OPTIONS } from "../api";
import { Field } from "../components/Field";
import { Panel } from "../components/Panel";

export function TokensPage() {
  const [tokens, setTokens] = useState<{ key: string; masked: string }[]>([]);
  const [selectedKey, setSelectedKey] = useState(TOKEN_OPTIONS[0]);
  const [value, setValue] = useState("");
  const [status, setStatus] = useState("");

  async function loadTokens() {
    const data = await api.getTokens();
    setTokens(data);
  }

  useEffect(() => {
    loadTokens().catch((error: Error) => setStatus(error.message));
  }, []);

  async function handleAdd() {
    if (!value.trim()) {
      setStatus("Informe o valor da chave.");
      return;
    }

    try {
      await api.addToken(selectedKey, value.trim());
      setValue("");
      await loadTokens();
      setStatus("Token salvo.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao salvar token.");
    }
  }

  async function handleDelete(key: string) {
    try {
      await api.deleteToken(key);
      await loadTokens();
      setStatus(`Token ${key} removido.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao remover token.");
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-light tracking-wide">Tokens</h1>
        <p className="mt-2 text-sm text-[#666]">
          Chaves de provider gravadas no `.env`, exibidas mascaradas.
        </p>
      </header>

      <Panel title="Adicionar token">
        <div className="grid gap-4 md:grid-cols-[1fr_1fr_auto]">
          <Field label="Provider">
            <select
              value={selectedKey}
              onChange={(event) => setSelectedKey(event.target.value)}
              className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
            >
              {TOKEN_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Valor">
            <input
              type="password"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
            />
          </Field>

          <div className="flex items-end">
            <button
              type="button"
              onClick={handleAdd}
              className="w-full border border-white px-4 py-2 text-xs tracking-wide uppercase transition hover:bg-white hover:text-black"
            >
              Adicionar
            </button>
          </div>
        </div>
      </Panel>

      <Panel title="Tokens cadastrados">
        {tokens.length === 0 ? (
          <p className="text-sm text-[#666]">Nenhum token cadastrado.</p>
        ) : (
          <div className="space-y-3">
            {tokens.map((token) => (
              <div
                key={token.key}
                className="flex items-center justify-between border border-[#222] px-4 py-3"
              >
                <div>
                  <p className="font-mono text-sm">{token.key}</p>
                  <p className="mt-1 font-mono text-xs text-[#999]">{token.masked}</p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDelete(token.key)}
                  className="border border-[#666] px-3 py-1 text-xs uppercase transition hover:border-white"
                >
                  Remover
                </button>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {status ? <p className="text-sm text-[#999]">{status}</p> : null}
    </div>
  );
}