import { useEffect, useMemo, useState } from "react";
import { api, type Fact } from "../api";
import { Field } from "../components/Field";
import { Panel } from "../components/Panel";

export function MemoryPage() {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [search, setSearch] = useState("");
  const [newFact, setNewFact] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [status, setStatus] = useState("");

  async function loadFacts() {
    const data = await api.getFacts();
    setFacts(data);
  }

  useEffect(() => {
    loadFacts().catch((error: Error) => setStatus(error.message));
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return facts;
    return facts.filter((fact) => fact.value.toLowerCase().includes(query));
  }, [facts, search]);

  async function handleAdd() {
    if (!newFact.trim()) return;
    try {
      await api.addFact(newFact.trim());
      setNewFact("");
      await loadFacts();
      setStatus("Fato adicionado.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao adicionar fato.");
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.deleteFact(id);
      await loadFacts();
      setStatus("Fato removido.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao remover fato.");
    }
  }

  async function handleSaveEdit() {
    if (editingId === null || !editingValue.trim()) return;
    try {
      await api.deleteFact(editingId);
      await api.addFact(editingValue.trim());
      setEditingId(null);
      setEditingValue("");
      await loadFacts();
      setStatus("Fato atualizado.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao editar fato.");
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-light tracking-wide">Memória</h1>
        <p className="mt-2 text-sm text-[#666]">
          Fatos persistentes injetados no system prompt do NULLAIN.
        </p>
      </header>

      <Panel title="Adicionar fato">
        <div className="flex flex-col gap-3 md:flex-row">
          <input
            value={newFact}
            onChange={(event) => setNewFact(event.target.value)}
            placeholder="Ex.: meu projeto principal é o LLM Soberano"
            className="flex-1 border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
          />
          <button
            type="button"
            onClick={handleAdd}
            className="border border-white px-4 py-2 text-xs tracking-wide uppercase transition hover:bg-white hover:text-black"
          >
            Adicionar
          </button>
        </div>
      </Panel>

      <Panel title="Fatos gravados">
        <Field label="Buscar">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full border border-[#444] bg-black px-3 py-2 font-mono text-sm outline-none focus:border-white"
          />
        </Field>

        <div className="mt-5 overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-[#333] text-xs tracking-wide text-[#999] uppercase">
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Fato</th>
                <th className="px-3 py-2">Gravado em</th>
                <th className="px-3 py-2">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((fact) => (
                <tr key={fact.id} className="border-b border-[#222]">
                  <td className="px-3 py-3 font-mono text-[#999]">{fact.id}</td>
                  <td className="px-3 py-3">
                    {editingId === fact.id ? (
                      <input
                        value={editingValue}
                        onChange={(event) => setEditingValue(event.target.value)}
                        className="w-full border border-[#444] bg-black px-2 py-1 font-mono text-sm outline-none focus:border-white"
                      />
                    ) : (
                      <span className="font-mono">{fact.value}</span>
                    )}
                  </td>
                  <td className="px-3 py-3 font-mono text-xs text-[#666]">
                    {fact.created_at.slice(0, 19)}
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex gap-2">
                      {editingId === fact.id ? (
                        <button
                          type="button"
                          onClick={handleSaveEdit}
                          className="border border-white px-2 py-1 text-xs uppercase"
                        >
                          Salvar
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(fact.id);
                            setEditingValue(fact.value);
                          }}
                          className="border border-[#666] px-2 py-1 text-xs uppercase"
                        >
                          Editar
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDelete(fact.id)}
                        className="border border-[#666] px-2 py-1 text-xs uppercase"
                      >
                        Apagar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filtered.length === 0 ? (
            <p className="mt-4 text-sm text-[#666]">Nenhum fato encontrado.</p>
          ) : null}
        </div>
      </Panel>

      {status ? <p className="text-sm text-[#999]">{status}</p> : null}
    </div>
  );
}