<div align="center">

<img width="1376" height="768" alt="BANNER2-README" src="https://github.com/user-attachments/assets/ca6479bd-da31-4d7b-8e4d-9c4ca8b25496" />


# ◼ NULLAIN-AGENT

### Runtime agêntico local-first. Um núcleo, qualquer LLM, qualquer ferramenta.

Agente autônomo que roda na sua máquina: interpreta objetivos, planeja passos e
executa ações reais no sistema via um loop de tool-calling. Núcleo em Python,
model-agnostic por design, integrações padronizadas por MCP e um dashboard de
controle em tempo real.

<br>

![License](https://img.shields.io/badge/license-MIT-000000?style=for-the-badge&labelColor=000000)
![Python](https://img.shields.io/badge/python-3.13+-000000?style=for-the-badge&logo=python&logoColor=white&labelColor=000000)
![LiteLLM](https://img.shields.io/badge/LLM-provider--agnostic-000000?style=for-the-badge&labelColor=000000)
![MCP](https://img.shields.io/badge/MCP-native-000000?style=for-the-badge&labelColor=000000)
![Local First](https://img.shields.io/badge/architecture-local--first-000000?style=for-the-badge&labelColor=000000)

![Status](https://img.shields.io/badge/status-active_development-000000?style=flat-square&labelColor=000000)
![UI](https://img.shields.io/badge/UI-React_+_Vite-000000?style=flat-square&labelColor=000000)
![Voice](https://img.shields.io/badge/voice-offline_STT_/_TTS-000000?style=flat-square&labelColor=000000)
![Style](https://img.shields.io/badge/aesthetic-1--bit_B%26W-000000?style=flat-square&labelColor=000000)

</div>

---

> **NULLAIN não é um chatbot — é um runtime de execução.**
> Onde assistentes retornam texto, a NULLAIN retorna *ações*: leitura e escrita
> de arquivos, execução de comandos com confirmação, chamadas a integrações
> externas e memória persistente entre sessões.

## ◻ Arquitetura

| Camada | Stack | Papel |
| --- | --- | --- |
| ⚫ **Núcleo** | Python 3.13 + loop de tool-calling | Orquestração, planejamento, ciclo agêntico |
| ⚫ **Gateway de LLM** | LiteLLM | Troca de provider sem alterar código (cloud ou local) |
| ⚫ **Integrações** | Model Context Protocol (MCP) | Conexão padronizada a ferramentas externas |
| ⚫ **Persistência** | SQLite | Memória, config runtime e histórico de execução |
| ⚫ **Interface** | React + Vite + Tailwind | Dashboard de controle black & white em tempo real |
| ⚫ **Voz** | STT + TTS offline | Entrada e saída de áudio 100% local |

Provider-agnostic: alterne entre modelos de nuvem (pagos ou free-tier) e
modelos locais sem tocar no código. **Você controla o cérebro, as chaves e os
dados.**

<img width="737" height="114" alt="Nullain-Skills" src="https://github.com/user-attachments/assets/a5099f3c-5268-4708-ae3e-2d16ca93d1f9" />

## ▪ NULLAIN-SKILLS — camada de capacidades

Sistema modular de habilidades plugáveis. Cada skill é uma unidade de
capacidade que o núcleo registra, descreve para o modelo e invoca em runtime:

- ▫ **System tools** — shell, filesystem e automações, sempre com gate de confirmação humana.
- ▫ **Guard-rails** — nenhuma ação sensível executa sem aprovação explícita.
- ▫ **Skills extensíveis** — novas capacidades entram no registro sem reescrever o núcleo.
- ▫ **Percepção** — visão computacional (OCR, captura de tela), acesso e coleta na web.
- ▫ **Voz offline** — transcrição e síntese locais, sem tráfego externo de áudio.

<img width="2752" height="692" alt="banner - Copia" src="https://github.com/user-attachments/assets/73deb5af-ae63-4f3b-b23a-730bae991ef8" />


## ▪ NULLAIN-SQUADS — orquestração multi-agente

Camada de coordenação que decompõe objetivos complexos e distribui o trabalho
entre sub-agentes especializados, executando em paralelo sob o núcleo:

| Sub-agente | Domínio |
| --- | --- |
| ◼ **Security** | pentest, OSINT, red teaming, análise defensiva |
| ◼ **Growth** | campanhas, ads multi-plataforma, métricas |
| ◼ **Design** | identidade visual e geração de assets |
| ◼ **Research** | pesquisa, análise e síntese de dados |
| ◼ **Engineering** | escrita, revisão e execução de código |
| ◼ **Ops** | agendamento, automações e cronogramas |

## ◻ Em desenvolvimento

**⚫ Loop Engineering** — capacidade de auto-iteração controlada: a NULLAIN
planeja, executa, avalia o resultado e refina em ciclos sucessivos até
convergir num objetivo, com limites explícitos e checkpoints para evitar
execução divergente.

**⚫ NULLAIN-CODING** — harness de engenharia de alto desempenho acoplável ao
núcleo, dedicado a maximizar as capacidades agênticas em codificação,
criptografia e tarefas técnicas complexas. Pensado como um arnês de execução
que amplifica o loop agêntico em fluxos de engenharia de ponta a ponta.

> Ambos são módulos de amplificação de capacidade. Detalhes de implementação
> internos são mantidos privados durante o desenvolvimento.

## ◻ Quick start

Requisitos: **Python 3.13+**, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com/) (recomendado para dev local).

```bash
# 1. Dependências
uv sync --group dev
cp .env.example .env

# 2. Modelo local (Ollama)
ollama pull llama3.2
ollama pull nomic-embed-text   # busca semântica de fatos (opcional)

# 3. Chat no terminal
uv run nullain chat

# 4. Diagnóstico do ambiente
uv run nullain doctor

# 5. API + dashboard
uv run nullain serve                 # http://127.0.0.1:8420
cd dashboard && npm install && npm run dev   # http://localhost:5173
```

### Auth local (recomendado)

No `.env` do backend:

```env
NULLAIN_API_TOKEN=troque-por-um-segredo-longo
```

No dashboard (`dashboard/.env` ou `.env.local`):

```env
VITE_NULLAIN_API_TOKEN=troque-por-um-segredo-longo
VITE_API_URL=http://127.0.0.1:8420
```

Sem token, a API aceita qualquer processo em `127.0.0.1` (ok só em dev isolado). Com token, REST usa `Authorization: Bearer …` e o WebSocket `?token=…`.

### Voz offline (opcional)

```bash
uv run nullain voice-setup    # baixa voz Piper pt_BR
uv run nullain chat --voice   # ou: uv run nullain voice
```

Transcrição no browser (webm) pode exigir **ffmpeg** no PATH.

### MCP

```bash
cp mcp.config.example.json mcp.config.json
# edite servidores; tokens via ${VAR} no env
```

Tools MCP com nome ambíguo **exigem confirmação por padrão** (fail-closed). Só nomes claramente de leitura (`list`, `get`, `search`, …) passam sem modal.

### Workspace e retenção

```env
NULLAIN_WORKSPACE=D:\caminho\do\projeto   # jail de arquivos + cwd do shell
NULLAIN_TOOL_RESULT_MAX_CHARS=8000        # compacta tool results no contexto do LLM
NULLAIN_LOG_MAX_ROWS=5000                 # purge de tool_logs no startup
NULLAIN_METRICS_MAX_ROWS=5000
```

### Skills & Squads

```bash
# Skills em ./skills/*/SKILL.md (+ handler.py opcional)
uv run nullain skills
uv run nullain skills --reload

# Squad multi-agente (research / engineering / ops)
uv run nullain squad "pesquise o projeto e proponha um fix no README"
```

No chat: tools `list_skills`, `run_skill`, `list_squad_roles`, `run_squad`.  
Dashboard: página **Skills** e **Reload MCP** em Integrações.

## ◻ Roadmap

- [x] Núcleo agêntico (loop de tool-calling + memória)
- [x] System tools com confirmação
- [x] Integrações via MCP
- [x] Dashboard de controle (config, tokens, memória, logs)
- [x] Voz local offline
- [x] NULLAIN-SQUADS — orquestração multi-agente (v0)
- [x] NULLAIN-SKILLS — registro extensível de capacidades (v0)
- [ ] Loop Engineering — auto-iteração controlada
- [ ] NULLAIN-CODING — harness de engenharia

---

<div align="center">

**NULLAIN** · *null by name, everywhere by design.*
[Nullysh-Team](https://github.com/Nullysh-Team) ⬛⬜

</div>
