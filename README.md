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

git clone https://github.com/Nullysh-Team/nullain-agent.git
cd nullain-agent
cp .env.example .env      # defina o modelo + a chave do provider
uv sync
uv run nullain chat       # núcleo no terminal
uv run nullain serve      # API + dashboard de controle


## ◻ Roadmap

- [x] Núcleo agêntico (loop de tool-calling + memória)
- [x] System tools com confirmação
- [x] Integrações via MCP
- [x] Dashboard de controle (config, tokens, memória, logs)
- [x] Voz local offline
- [ ] Loop Engineering — auto-iteração controlada
- [ ] NULLAIN-CODING — harness de engenharia
- [ ] NULLAIN-SQUADS — orquestração multi-agente
- [ ] NULLAIN-SKILLS — registro extensível de capacidades

---

<div align="center">

**NULLAIN** · *null by name, everywhere by design.*
[Nullysh-Team](https://github.com/Nullysh-Team) ⬛⬜

</div>
