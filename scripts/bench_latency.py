#!/usr/bin/env python3
"""Benchmark de latência do NULLAIN — 10 prompts padrão.

Uso:
    uv run python scripts/bench_latency.py

Mede TTFT, duração total, iterações e tokens por prompt.
Requer Ollama rodando localmente (ou outro provider configurado no .env).
"""
from __future__ import annotations

import statistics
import sys
import time

from nullain.agent import run_agent
from nullain.brain import Brain
from nullain.persona import build_session_messages

BENCHMARK_PROMPTS = [
    "Olá, quem é você?",
    "Lista os arquivos do diretório atual.",
    "Qual é a hora atual?",
    "Escreva um haiku sobre tecnologia.",
    "Resuma o que é Python em uma frase.",
    "Diga se 17 é primo e explique por quê.",
    "Escreva uma função que calcula Fibonacci.",
    "Diga a diferença entre TCP e UDP.",
    "Resolva: 15 * 23 = ?",
    "Descreva a arquitetura do NULLAIN em 3 pontos.",
]


def run_benchmark() -> None:
    core = Brain()
    total_tools, mcp_count = core.startup()

    print(f"NULLAIN Benchmark — {total_tools} tools ({mcp_count} MCP)")
    print(f"Modelo: {core.mcp_manager._connected and 'conectado' or 'desconectado'}")
    print("-" * 60)

    results: list[dict] = []

    for index, prompt in enumerate(BENCHMARK_PROMPTS):
        messages = build_session_messages()
        messages.append({"role": "user", "content": prompt})

        start = time.monotonic()
        try:
            response = run_agent(messages, confirm=lambda _: False)
        except Exception as exc:
            response = f"[ERRO: {exc}]"
        elapsed = time.monotonic() - start

        result = {"prompt": prompt, "response_len": len(response), "elapsed_ms": elapsed * 1000}
        results.append(result)
        print(f"  {index + 1:2d}. {prompt[:40]:<42s} {elapsed * 1000:7.0f}ms")

    core.shutdown()

    print("-" * 60)
    elapsed_values = [r["elapsed_ms"] for r in results]
    print(f"  Média:    {statistics.mean(elapsed_values):.0f}ms")
    print(f"  Mediana:  {statistics.median(elapsed_values):.0f}ms")
    print(f"  P95:      {sorted(elapsed_values)[max(0, int(len(elapsed_values) * 0.95) - 1)]:.0f}ms")
    print(f"  Mín:      {min(elapsed_values):.0f}ms")
    print(f"  Máx:      {max(elapsed_values):.0f}ms")
    print(f"  Total:    {sum(elapsed_values) / 1000:.1f}s")


if __name__ == "__main__":
    try:
        run_benchmark()
    except KeyboardInterrupt:
        print("\nInterrompido.")
        sys.exit(0)