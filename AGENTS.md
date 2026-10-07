# AGENTS.md — Quinta-Feira

Referência operacional para qualquer agente (Claude Code, Codex, outro) trabalhando neste repositório.
Para o histórico completo de features e decisões, veja `docs/PLANO_EVOLUCAO.md`, `docs/PESQUISA_CONCORRENTES.md`
e `docs/PLANO_PROXIMOS_PASSOS.md`. Este arquivo é sobre **como trabalhar no código**, não um changelog.

## O que é

Assistente de IA pessoal do Matheus, rodando 100% local (sem servidor próprio, só APIs de terceiros: Gemini,
ElevenLabs/Edge-TTS, Nominatim/Overpass/Open-Meteo, Tavily/DDG). Fala em voz, vê a tela, controla mídia do
sistema, toca música, mexe em WhatsApp Web/Telegram/Discord, tem memória de longo prazo e iniciativa própria
(avisos proativos, briefing, lembretes, auto-revisão semanal).

- **Backend:** FastAPI + Uvicorn, Python 3.14, porta 8000. `backend/main.py` é o entrypoint.
- **Frontend:** Next.js 16 / React 19, porta 3000. `frontend/app/page.tsx` é a página principal.
- **LLM:** Gemini 2.5 (`backend/core/gemini_provider.py`), chamado via `brain/quinta_feira_brain.py`.
- **Banco:** SQLite (`backend/.runtime/quinta_feira.db` e bancos menores em `.runtime/`).

## Rodar e testar

```bash
# backend
cd backend && .venv\Scripts\python.exe main.py        # ou .venv\Scripts\python.exe -m uvicorn main:app --port 8000

# frontend
cd frontend && npm run dev

# ligar/desligar/reiniciar os dois de uma vez (Windows)
scripts\quinta_control.ps1 -Acao ligar|desligar|reiniciar|status
```

**Antes de qualquer PR/entrega, roda isto — e é zero custo de API:**

```bash
cd backend && PYTHONUTF8=1 .venv\Scripts\python.exe diagnostics\smoke_test.py   # ~680 checks, deve terminar "0 falhou"
cd frontend && npx tsc --noEmit && npx eslint . && node --test lib/*.test.mts
```

**Regra inegociável deste projeto (feedback explícito do usuário):** toda feature nova que chama LLM/TTS/web
precisa de um teste no smoke que prova que o caminho feliz E os de erro **não disparam chamada real** (mock do
provider/http, contagem de chamadas). `core/llm_policy.py` também exige que todo call site de LLM tenha uma
política registrada — um teste estático no smoke falha se faltar.

## Arquitetura: por que tanta coisa é determinística (regex) em vez de "deixa o LLM decidir"

`brain/quinta_feira_brain.py::ask()` tem ~9 roteadores determinísticos (`_is_music_request`,
`_detect_media_command`, `_is_day_summary_request`, `_is_screen_request`, `_is_agent_request`,
`_is_correction`, `_is_complex_question`, `_is_news_query`, `_pedido_musical_vago`) que interceptam a mensagem
**antes** de ela virar uma chamada ao modelo com tool-calling. Isso existe por três motivos: custo (zero
chamadas de API nesses casos — testável no smoke), latência (resposta instantânea pra "pausa a música") e
previsibilidade ("manda mensagem" nunca pode abrir o YouTube).

O preço é que esses caminhos não "raciocinam": eles executam o texto literal. Quando o pedido tem uma
referência que precisa ser resolvida no mundo real (ex.: "o novo álbum de X" — qual é o mais recente?), o
roteador precisa **detectar a ambiguidade e devolver a mensagem pro LLM com tools** em vez de executar o
texto cru. `_pedido_musical_vago` + `core/media/escolha_video.py` são o primeiro caso feito assim.

**Auditoria (2026-10-07):** dos ~9 roteadores determinísticos, só o de música tinha esse problema — os outros
dois que executam ANTES do LLM (`_is_day_summary_request`, `_detect_media_command`) não recebem parâmetro
ambíguo: um não tem parâmetro, o outro mapeia pra uma ação canônica (pausar/retomar/pular), não pra texto
livre. Os demais (`_is_correction`, `_is_agent_request`, `_is_complex_question`, `_is_screen_request`)
só anotam o prompt/modo e o pedido continua pro LLM com tool-calling normal — não têm o bug da música pra
generalizar. Em vez de duplicar código por roteador, a generalização que fez sentido foi uma regra única no
system prompt ("RESOLVA A REFERÊNCIA ANTES DE EXECUTAR", perto de `ENCADEIE FERRAMENTAS`) cobrindo qualquer
chamada de ferramenta que o LLM decida fazer — não só os 2 caminhos que pulam o LLM. É instrução de prompt,
não código determinístico: ajuda, mas não garante — o LLM pode ainda assim passar um valor não resolvido.

## Tools (ferramentas)

~34 registradas em `core/tools/__init__.py` (ver `aliases=[...]` de cada uma). Toda tool nova:
1. Herda de `MotorTool` (`core/tools/base.py`), define `ToolMetadata` com `security_level`.
2. É classificada em `core/policy/tool_risk.py` (`RISCO_POR_ACAO`) — leitura/escrita/critica. Sem classificar,
   o smoke falha (`esta_classificada`).
3. Se devolve texto vindo de fora (web, WhatsApp, documento, resultado de outro agente), passa por
   `core/policy/content_origin.py` — vira "conteúdo externo não confiável" e contamina o turno (não pode ser
   tratado como instrução).
4. Ganha um teste no smoke que não bate em rede/API real.

MCP (`core/mcp/`) e ferramentas propostas por ela mesma (`core/plugins/`, `propor_ferramenta`) são sempre
classificadas como críticas e tratadas como conteúdo externo, mesmo que pareçam inócuas.

## Memória

`backend/core/memory/memory_manager.py` + `qualidade.py`. Autoridade por fonte (usuário > tool > reflexão >
curiosidade): uma fonte de menos autoridade nunca sobrescreve silenciosamente uma de mais autoridade — vira
"conflito" (`/memoria/conflitos`, aba Aprovações do painel). Perfil essencial (`perfil_essencial`) é pontuado
por categoria×confiança×uso, não "os N mais recentes". Ver `core/memory/qualidade.py` para as regras exatas.

## Convenções

- Nomes de domínio, comentários e strings voltadas ao usuário: **português** (é um produto em PT-BR). Nomes
  genéricos/de infraestrutura podem ficar em inglês quando já é o padrão do arquivo.
- Comentário explica o **porquê** (o bug que existia, a decisão tomada), não o que a linha já diz sozinha —
  é o estilo predominante no repo; mantenha.
- Preferir recusar com um erro claro (`[ERRO ...]`, `[BLOQUEADO ...]`) a inventar/chutar um resultado.
- Arquivos grandes existentes (`brain/quinta_feira_brain.py` ~2500 linhas, `automation.py` ~1400,
  `main.py` ~1800) são dívida conhecida, não o padrão a seguir em código novo.

## Não fazer sem aprovação explícita do usuário

- `git` config/worktree (há um worktree fantasma que quebra `git status`; só leitura é segura).
- Reiniciar o backend/frontend que o usuário já tem rodando, sem ele saber.
- Ler ou imprimir segredos do `.env` (usar `python -m core.host.segredos` para isso).
- Construir qualquer ferramenta de OSINT/agregação de identidade apontada a terceiros sem consentimento claro
  — mesmo em um assistente pessoal, isso é vigilância, não automação.
- Apertar qualquer controle de segurança (aprovação, risco, taint) sem decisão explícita — frouxar é sempre
  decisão do usuário.
