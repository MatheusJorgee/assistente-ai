# Plano de evolução da Quinta-Feira: mais esperta, mais bonita, mais tecnológica

Gerado em 2026-09-20. Base: pesquisa de 9 agentes (UI/UX, memória, Jarvis open-source, autodidatismo/controle do PC, voz, GitHub, fóruns, MCP/agentes 24/7, companions/avatares).
A **auditoria do código real** e a pesquisa de life OS/agentic OS já foram incorporadas. Os achados da auditoria estão marcados **[AUDITORIA]** com arquivo:linha; os críticos (bind 0.0.0.0, WS sem auth, bridge de eventos desligado, `shell=True`) eu conferi diretamente no código.

> ### Status de execução (2026-09-20): "mais inteligente e mais barata"
> Feito e verificado ao vivo (smoke test: 32 → 56 checks, todos passando):
> - **Ledger de custo** (`core/telemetry/token_ledger.py`, `GET /custo`): tokens e US$ estimados por função, taxa de cache. Cobre 2.12 e a base do 2.16.
> - **Política por função** (`core/llm_policy.py`): tarefas de fundo sem raciocínio (o aviso proativo gastava 980 tokens de raciocínio para 33 de fala), classificadores no `gemini-2.5-flash-lite`, extrações com teto. Chave: `LLM_POLICY_ENABLED`.
> - **Cascata**: modo agente usa `gemini-2.5-pro`; pergunta complexa raciocina com teto de 4096 (antes sem teto). Chaves: `STRONG_MODEL_ENABLED`, `COMPLEX_THINKING_BUDGET`.
> - **Prefixo estável p/ cache**: contexto variável foi do system prompt para o fim da mensagem do usuário. Chave: `CONTEXT_IN_USER_TURN`.
> - **Saudação pura sem ferramentas** (~9,4k → ~3,6k tokens) e **saída de tool com teto** (2.13, versão simples: `TOOL_OUTPUT_MAX_CHARS`).
> - **Lição → memória** (`core/learning/lessons_store.py`, `GET/DELETE /licoes`): correção vira regra de comportamento que vale nas próximas sessões. É a primeira metade do 2.22; a segunda (promover a *guarda de código* quando reincidir) continua pendente.
> Pendente desta frente: roteamento de ferramentas por pedido (o schema das 30 tools pesa ~6,3k tokens), cache explícito, streaming (2.1), heartbeat com portão em Python (2.3).
> Nenhuma instância do backend estava escutando ao final desta etapa, então as mudanças valem no próximo início.
>
> ### Fase 0, primeira leva (feita e verificada contra o `app` real, sem rodar o startup)
> - **0.2 (parcial) Rede fechada:** `scripts/start_quinta.ps1` subia com `--host 0.0.0.0` explícito e `config.py` tinha o mesmo padrão; ambos agora em `127.0.0.1`. Novo `core/api/local_guard.py` (ASGI, HTTP e WebSocket) barra `Origin` de sites de terceiros (CSRF e WebSocket hijacking, que o CORS não cobre) e `Host` estranho (DNS rebinding). Chaves: `LOCAL_GUARD_ENABLED`, `EXTRA_ALLOWED_ORIGINS`, `EXTRA_ALLOWED_HOSTS`. **Ainda falta o token por sessão:** outro programa da mesma máquina continua alcançando o backend.
> - **0.13 Injeção de comando:** `abrir_programa` deixou de usar `shell=True` (agora `os.startfile` + recusa de nomes com `"&|<>^%;`); `controlar_energia` força `delay` inteiro entre 0 e 3600 (vinha do LLM direto em `os.system`). `backend/automation_power_method.py` tem o mesmo padrão, mas é código morto e não foi tocado.
> - **0.14 Timeout no WebSocket:** `wait_for` de 120 s em volta do `brain.ask` (`WS_BRAIN_TIMEOUT_SECONDS`); o tratador de `TimeoutError` já existia, mas nada o disparava.
> - **0.10 Detector de loop:** a 3ª chamada idêntica (mesma tool + mesmos argumentos) em sequência é barrada.
> - **Bug achado no caminho:** `MessageEnvelope.request_id` é `str`, mas as fábricas passavam `uuid4()`; com pydantic 2.13 isso estourava em toda mensagem de servidor sem `request_id` (inclusive dentro do tratador de erro). Corrigido no envelope.
> - **Ainda aberto, achado no teste:** o handler do chat chama `receive_json()` fora do `try`, então texto que não é JSON derruba a conexão (o frontend não faz isso).

> ### Fase 0.3 + 1.8 (2026-09-24): aprovação por risco, com cartão na tela
> Feito e verificado ponta a ponta (smoke test: 76 → 108 checks; WebSocket real com brain falso; navegador real dirigido por Playwright):
> - **Classificação de risco** (`core/policy/tool_risk.py`): leitura / escrita / **crítica**, por ferramenta *e por ação* (WhatsApp `enviar_mensagem` é crítica, `triagem` é leitura; ação desconhecida cai no lado cauteloso). O smoke test **falha se uma ferramenta registrada não estiver classificada**.
> - **Gate único** em `ToolRegistry.execute`: cobre o LLM, os passos de macro e comandos agendados. Falha **fechada** (erro no controle = não executa).
> - **Broker** (`core/policy/approvals.py`): pergunta na tela e **nega** por recusa, por tempo (60 s) ou por não haver tela aberta. Origem `telegram` (dono) é liberada; loop autônomo tem ação crítica **negada sem perguntar**; comando agendado pergunta na tela. Toda decisão vai para `.runtime/audit/tool_risk.jsonl` (`GET /auditoria/acoes`).
> - **Modos de autonomia:** `perguntar_sempre` / `so_perigoso` (padrão) / `autonoma` (`GET/POST /autonomia`, persistido). Escudo no dock alterna; ir para `autonoma` pede confirmação.
> - **WebSocket em fila:** o loop de recepção não fica mais preso dentro do `brain.ask` (senão a resposta da aprovação nunca seria lida = deadlock). Pedidos abertos são reenviados quando a tela reconecta.
> - **`ApprovalCard`:** foco abre em **Negar**, `Esc` nega, mostra o texto/comando exato, barra de tempo, funciona no celular e respeita `prefers-reduced-motion`.
> - **Pendente:** aprovar por voz/Telegram (decisão de segurança à parte), "sempre permitir" só para risco baixo, e o dock fica largo demais em telas de ~390px (item 1.11, já existia).
> - **Origem do conteúdo (0.4): FEITO em 2026-09-24** (smoke test 108 → 136). `core/policy/content_origin.py`: (1) saída de tool com conteúdo de terceiros (WhatsApp lido, web, documento, agenda, terminal, tela) chega ao LLM em envelope "não confiável", com marcas de fechamento falsificadas neutralizadas; (2) ler isso **contamina o turno atual e o seguinte** (o texto fica no histórico), por `contextvar`, sem vazar entre sessões; (3) sob contaminação o gate **pergunta sempre** para ação crítica (ignora modo autônomo e a confiança do Telegram) e sobe para crítica o que cria persistência/vazamento (`agendar_acao`, criar `macro`, `memorizar_informacao`, `pessoas salvar`, `clipboard_inject`, imagem por URL no visor); (4) o cartão avisa "pedido depois de ler mensagens do WhatsApp". Regra também no system prompt (defesa em profundidade).
> - **Evidência empírica (honesta):** em dois experimentos com Gemini real (ordem escondida em página web: 0/4 vs 0/4; engenharia social por WhatsApp com modo autônomo + Telegram: 0/5 vs 0/5) o modelo **não caiu em nenhum ataque, com ou sem as defesas**. Amostras pequenas: não prova robustez geral. As defesas são seguro verificado por teste, não uma melhoria medida em vitórias.
> - **Limites conhecidos do 0.4:** a contaminação é por turno (não por conteúdo); envenenamento por texto que o usuário cola no chat não é coberto; o filtro de PII/scan de memória (0.5) segue pendente.
>
> ### Fase 0.6 + 0.7 + 1.7 + 1.2 (2026-09-24): progresso em tempo real, PARAR e a faixa "Agora"
> Feito e verificado (smoke test 136 → 147; 7 cenários ponta a ponta pelo WebSocket; navegador real via Playwright):
> - **0.6 Eventos de progresso** (`core/runtime_progress.py`): o brain emite `tool_call_start` / `tool_call_result` sem conhecer o WebSocket (callback por contexto de tarefa). Só vai o **nome e um rótulo humano** ("lendo suas mensagens do WhatsApp"), nunca os argumentos. `tools_used` e `execution_time_ms` da resposta agora vêm preenchidos (eram sempre `[]` e `0`).
> - **0.7 PARAR:** mensagem `stop` cancela a execução atual **e descarta a fila**; se há aprovação pendente, o cartão fecha (`cancelado`) e a ação não executa. A conexão e o trabalhador seguem vivos. Limite honesto: uma ferramenta que **já começou** num thread (ex.: um envio de WhatsApp em andamento) não é desfeita; o que para é tudo que viria depois.
> - **1.7 Faixa "Agora"** (`NowStrip`): "pesquisando na web… 3s", "pensando…" ou "aguardando a sua aprovação". **1.2 Botão de parar + Esc:** o Esc para tudo; com um cartão de aprovação aberto o Esc **nega** o cartão (o segundo Esc para). O `ChatOverlay` já tinha chips de `tools_used`, que agora ganham dados de verdade.
> - **Lint:** os arquivos novos/alterados de UI estão limpos; restam 10 avisos **anteriores** (`any` no tratamento antigo do WS, dois efeitos de `localStorage`, um import sem uso).
> - **Pendente:** streaming da resposta (2.1), painel de custo/lições/auditoria na UI, token por sessão (0.2), scan de memória (0.5).
>
> ### Item 2.1 (2026-09-24): streaming da resposta, texto e voz frase a frase
> Feito e verificado (smoke test 147 → 161; 14 testes `node --test` da lógica pura de frases; navegador real via Playwright):
> - **Backend:** `GeminiAdapter.generate_stream` (com ferramentas) entrega `text_delta` conforme o modelo escreve; se a volta termina numa ferramenta manda `text_reset` (o texto era preâmbulo); se o streaming falha, o brain volta ao `generate()` sem o usuário perceber. Só ativa para quem escuta o progresso (chat pelo WebSocket); Telegram, loop autônomo e agendados seguem no modo antigo. Mesmo ledger de custo e mesma política de modelo. Chaves: `STREAM_RESPONSES`, `STREAM_TIMEOUT_SECONDS`.
> - **Frontend:** o balão cresce com cursor; cada **frase completa** (só fecha com pontuação + espaço, então "R$ 5,40" não é cortado) vai para o TTS na hora, com o áudio da próxima já sendo buscado; ao chegar o texto final só falta falar o resto, sem repetir; `Esc` corta a fila de voz. O preâmbulo falado antes de uma ferramenta ("deixa eu ver…") é mantido, como uma pessoa faria.
> - **Medido com o Gemini real (mediana de 3 perguntas):** 1º texto 1,56 s → 1,18 s; resposta inteira 1,56 s → 1,63 s (sem custo de velocidade); **até a voz começar ~5,15 s → ~3,27 s (−37%, estimado = texto + TTS)**.
> - **Novo gargalo, medido:** o **TTS (edge-tts) leva ~1,8 s por frase** (3,6 s para 300 caracteres). É agora o maior pedaço da espera. Candidatos: reaproveitar a conexão do edge-tts, TTS local (Piper pt-BR, do relatório de voz) ou Gemini Live (4.4).
> - **Limite honesto:** o ganho de voz é uma estimativa (soma das partes medidas no backend), não uma medição ponta a ponta no navegador com o TTS real.
>
> ### Pesquisa ampliada (2026-09-24): ver `docs/PESQUISA_CONCORRENTES.md`
> 5 agentes leram o código de 15 projetos (Fatih, OpenClaw, Hermes, nanobot, QwenPaw, gcocenza/jarvis, Open-LLM-VTuber, Sutando, OpenJarvis e outros), fóruns e criadores. O documento traz a matriz de funcionalidades, licenças (o que dá para adaptar como código e o que é só ideia) e um backlog em 3 ondas. **Onda A recomendada primeiro** (ataca o TTS de ~1,8 s por frase, custo do proativo, cota do Gemini e memória).
>
> ### Referência externa: FatihMakes "Mark LIV" (2026-09-24)
> Lido só o **README** dos repositórios públicos (github.com/FatihMakes; Mark-LIV 1.4k estrelas); **não li o código-fonte** e não assisti aos vídeos do Instagram (exige login). Números abaixo são afirmações dele. **Licença CC BY-NC 4.0** (uso pessoal/não comercial, com atribuição): ideias sim, cópia de código não.
> - É um app **desktop nativo** (PyQt6 + PortAudio) em cima da **Gemini Live API** (áudio nativo, sessão retomável, wake word local `openwakeword`); a Quinta é web + Web Speech. Essa diferença explica boa parte da vantagem dele em voz.
> - **Onde ele está à frente:** voz full-duplex; rosto holográfico com lip-sync (modelo de face do MediaPipe, Apache 2.0; renderização em software, sem GPU); pilha de **desfazer**; plugins de arquivo único com auto-descoberta e isolamento de falha; empacotamento multi-SO.
> - **Onde a Quinta está à frente (pelo que o README mostra):** proatividade (monitor, briefings, lembretes, modo foco), aprendizado contínuo (reflexão, curiosidade, lições, estilo), integrações (WhatsApp, Telegram, agenda, finanças, CRM), classificação de risco com defesa contra injeção, ledger de custo. O README dele não descreve defesa contra prompt injection (não significa que não exista).
> - **Ideias a absorver:** (1) **desfazer** para arquivos: em vez de apagar de vez, mover para quarentena + diário de ações reversíveis, encaixa com a aprovação; (2) **memória: núcleo minúsculo no prompt + índice das chaves + tool `recall_memory`** (971 caracteres para 62 fatos, segundo ele), reforça o item 2.8; (3) **autoconhecimento montado em runtime** (ferramentas reais + limites declarados: "vejo a tela só sob demanda"), evita alucinar capacidades; (4) **reconhecimento instantâneo** ("deixa eu ver…") quando uma tarefa longa começa, natural com o streaming; (5) **lip-sync a partir do áudio** (análise espectral do que está tocando, no navegador via `AnalyserNode`), alternativa barata ao avatar 3D para a Fase 5; (6) Gemini Live + wake word local valida a opção A do relatório de voz (4.4); (7) o token de confirmação **emitido pela UI, que o modelo não consegue forjar**: já é como o nosso gate funciona (o modelo não tem parâmetro para se autoaprovar).
>
> ### Achado urgente de segurança (confirmado no código)
> O backend sobe em `0.0.0.0` por padrão (`core/config.py:180`) e o WebSocket `/ws/quinta` aceita qualquer conexão sem token nem checagem de origem (`core/api/brain_router.py:155`). Qualquer dispositivo da sua rede local pode conversar com a Quinta, e ela tem tool de terminal (PowerShell), envio de WhatsApp e acesso a arquivos. Na prática isso é **execução remota de comandos na LAN**. Corrigir é o item 0.2 e deve ser a primeira coisa a fazer.
Projetos que a pesquisa apontou como mortos ou hype, para não perder tempo: Bytebot, executive-ai-assistant (arquivados), SuperAGI, Limitless/Rewind e Bee (absorvidos), OpenManus/AgenticSeek (pouca profundidade).
Limite da pesquisa de fóruns: o Reddit estava bloqueado para o agente, então as evidências de comunidade vêm de Hacker News, dev.to e blogs.

> **Aviso de confiabilidade.** Os dados de estrelas, versões e preços vêm dos agentes de pesquisa (APIs do GitHub, PyPI, docs oficiais) e não foram reverificados por mim. Nomes de arquivos abaixo vêm da memória do projeto (96 dias) e devem ser conferidos contra a auditoria antes de codar. Estimativas de latência e esforço são minhas.

---

## 0. Princípios (o que a pesquisa inteira ensinou)

1. **Evoluir por incrementos, nunca reescrever.** Leon 2.0 e Open Interpreter reescreveram e ficaram sem docs e com uso quebrado.
2. **Um único sistema de risco por tool + aprovação na UI.** Foi a recomendação de 4 dos 5 relatórios (OpenClaw, QwenPaw, Claude Code, ChatGPT agent).
3. **Skills só locais, escritas por ela e aprovadas por você.** Marketplace foi o maior desastre de segurança do setor (341 skills maliciosas achadas pela Snyk no ClawHub).
4. **Conteúdo de terceiros é dado, nunca comando.** Mensagem de WhatsApp, página web ou e-mail não pode disparar tool de risco nem criar skill.
5. **Copiar ideias, não adotar frameworks inteiros** (Mem0, Graphiti, Letta, CopilotKit, Pipecat).
6. **Medir antes e depois:** golden set de memória, latência p50, tokens por resposta.
7. **Guardrails ficam no código, nunca só no prompt.** Caso real: uma pesquisadora da Meta mandou o agente "sugerir e esperar aprovação"; o contexto estourou, a compactação descartou a instrução e o agente apagou centenas de e-mails (TechCrunch, 2026-02-23). Aprovação e limites têm que ser impostos pelo backend.

---

## Visão geral das fases

| Fase | Objetivo | Depende de | Esforço |
|---|---|---|---|
| 0 | Fundação: segurança, risco, protocolo de eventos | nada | M |
| 1 | UI nova (bonita e transparente) | Fase 0 (protocolo de eventos) | M-G |
| 2 | Mais esperta: velocidade, proatividade barata, memória v2 | Fase 0 | M-G |
| 3 | Autodidata: skills, MCP, controle do PC | Fases 0 e 1 (aprovação na UI) | G |
| 4 | Voz nível Jarvis: voiceprint, streaming, modo conversa | Fase 0 | G |
| 5 | Presença e persona (orbe evoluído ou avatar) | Fase 1 **[PENDENTE: relatório de companions]** | M |

Fases 1, 2 e 4 podem andar em paralelo depois da Fase 0. A Fase 3 é a última porque é a mais arriscada e usa tudo o que vem antes.

---

## FASE 0: Fundação (fazer primeiro)

Sem isto, tudo o resto (UI de aprovação, skills, voz) fica sem chão.

| # | Tarefa | Detalhe | Critério de pronto |
|---|---|---|---|
| 0.1 | Backup | Copiar `backend/data/*.db`, `.runtime/`, `.env` para uma pasta datada fora do projeto | Backup restaurável testado |
| 0.2 | **Rede fechada (URGENTE)** | **[AUDITORIA, confirmado]** Trocar o padrão de `BACKEND_HOST` para `127.0.0.1` (`core/config.py:180`) e conferir `.env` e os scripts de start (`start_quinta*.ps1/.vbs`, `painel-controle.ps1`), que podem passar `--host 0.0.0.0`. Token simples no WS e nos endpoints HTTP, mais checagem de `Origin` no `accept()` (CORS não protege WebSocket). Fechar também `/api/logs` e `/tts` | Acesso por outro IP da LAN recusado; frontend local continua funcionando |
| 0.3 | Classes de risco por tool | **[AUDITORIA]** Hoje `SecurityLevel.MEDIUM/CRITICAL` (`core/tools/base.py:56-60`) é só metadado, sem enforcement. O `PolicyEngine` (`core/policy/policy_engine.py`) só protege 3 tools v2 (OSCommand, ProcessControl, FileOps) e apenas bloqueia/libera, sem aprovação. O `TerminalTool` (`core/tools/terminal_tool.py:61-119`) **executa direto o nível `PROMPT`** sem confirmar. Fazer: `leitura` (livre), `escrita` (confirma), `destrutivo/envio/financeiro` (sempre confirma); a mais estrita vence; sem UI ativa o padrão é **negar**. Transformar o `SecurityLevel` em política aplicada no `ToolRegistry.execute` (ponto único) e usar o campo `interactive` do DTO (`dtos.py:47`, hoje sem uso) | Toda tool das ~29 classificada; WhatsApp enviar, terminal e file_ops sempre pedem aprovação |
| 0.13 | Corrigir injeção de comando | **[AUDITORIA, `shell=True` confirmado]** `AbrirProgramaTool` monta `start "" "{nome}"` com f-string e `shell=True` (`core/tools/abrir_programa_tool.py:119`): o nome vem do LLM. Trocar por `os.startfile` ou `subprocess` com lista de argumentos. Revisar também `os.system` de shutdown/reboot em `automation.py:1067-1079` | Nome com `"&calc&"` não executa nada extra |
| 0.4 | Origem do conteúdo | Marcar cada texto como `usuario` ou `externo` (WhatsApp, web, e-mail, OCR de tela). `externo` nunca dispara tool de risco ≥ escrita nem criação de skill | Teste: mensagem de WhatsApp com "apague meus arquivos" não executa nada |
| 0.5 | Scan de memória | Antes de gravar fato vindo de conteúdo externo, filtrar padrões de injection/exfiltração (padrão do Hermes) | Fato malicioso de teste é recusado |
| 0.6 | Protocolo de eventos no WS | Vocabulário inspirado no AG-UI, sem a lib: `run_started`, `step`, `tool_call_start`, `tool_call_result`, `approval_requested`, `approval_response`, `state_delta`, `run_finished`. **[AUDITORIA, confirmado]** O `WebSocketEventBridge` (`gateway_manager.py:396`) está desligado: `init_ws_bridge` (`ws_router.py:90`) nunca é chamado, e o handler `runtime_event` do front (`useQuintaFeira.ts:341-368`) é código morto. Hoje `/ws/quinta` só envia `intermediate_status` (o "processing" é enviado *depois* do `ask()`, então engana), `brain_response` com `tools_used: []` e `execution_time_ms: 0` sempre vazios (`brain_router.py:~285`), `error` e `pong`. **Caminho mais curto:** emitir os eventos direto do `_process_with_tool_calls` para o socket da sessão, sem depender do bridge legado | Frontend recebe eventos de tool em tempo real; `tools_used` e tempo preenchidos de verdade |
| 0.14 | Timeout no WS | `brain.ask` em `/ws/quinta` não tem timeout (o WS legado tem 30 s). Adicionar timeout e mensagem de erro clara | Pedido travado devolve erro em vez de ficar pendurado |
| 0.7 | Parada de emergência | `POST /stop` cancela a task do brain e a fala em curso; UI liga isso ao Esc e a um botão | Esc interrompe uma cadeia de tools no meio |
| 0.8 | Log de auditoria | Toda ação de risco registra: o que, origem, decisão, quando (reaproveitar `core/telemetry/audit_logger.py`) | Linha por ação no log |
| 0.10 | Detector de loop | Interromper após 3 chamadas idênticas seguidas da mesma tool (padrão de um agente 24/7 relatado no Hacker News) | Teste com tool em loop é cortada na 3ª |
| 0.11 | Leases e teto de destrutivas | Autorização de controle com **expiração**; teto de ações destrutivas por execução (acima de 3 pergunta de novo mesmo com "sempre permitir"). Padrões vistos em `eduardo02138/JARVIS` (mesma stack Gemini+FastAPI) e Vavis | Lease expira sozinho; 4ª destrutiva sempre pergunta |
| 0.12 | Segredos e PII | Chaves fora do prompt (o modelo pede a ação, o backend usa a chave); DPAPI ou credential store do Windows para segredos; redação de PII antes de ir para o contexto/diário (padrão `isair/jarvis`) | Nenhuma chave aparece em prompt/log |
| 0.9 | Smoke test v2 | Estender `diagnostics/smoke_test.py` (32 checks) com: classificação de risco completa, bloqueio de conteúdo externo, protocolo de eventos | Roda com exit 0 |

---

## FASE 1: UI nova (mais bonita e transparente)

Direção: manter a identidade atual (vidro escuro, ciano, orbe central) e torná-la **viva e legível**. Uma superfície de estado (orbe + faixa "Agora") é mais barata que vários efeitos.

**Execução:** usar as skills `impeccable` (direção e polish), `frontend-design` (identidade), `image-to-code` (mock antes de codar) e `web-design-guidelines` (revisão final de acessibilidade).

### 1.0 Pré-requisitos vindos da auditoria **[AUDITORIA]**
| # | Item | Detalhe |
|---|---|---|
| 1.15 | **Endpoints de dados que faltam** | Nenhum endpoint HTTP expõe lembretes, watchlist, foco, ideias, pessoas, macros, agendados, agenda ou o estado interno (humor/energia): só existem como tools, com stores em `core/{proactive/reminders_store, finance/watchlist_store, focus/focus_store, inbox/ideas_store, people/people_store, macros, scheduler}` e `internal_state.py`. Sem esses `GET`, os painéis 1.10 e 1.12 não têm o que mostrar |
| 1.16 | **Design system mínimo** | Hoje só 2 CSS vars (`globals.css:4-5`), ~119 cores rgba/hex inline nos componentes, `components/ui` não existe, e `font-family: "Segoe UI"` (`globals.css:10`) anula a Geist carregada em `layout.tsx`. Criar tokens (`@theme` do Tailwind 4) para cor, espaço, tipografia e raio **antes** de mexer nos componentes, senão cada painel novo herda a bagunça |
| 1.17 | **Correções de acessibilidade e robustez** | `maximumScale: 1` bloqueia zoom (`layout.tsx:22`); zero `prefers-reduced-motion` apesar de 5 blobs `blur-3xl` animados (`page.tsx:82-128`); só 6 `aria-*` no projeto e nenhum `aria-live`/`role="dialog"`; `focus:outline-none` sem substituto (`VoiceOrb.tsx:261`); texto `10-11px` com contraste baixo; reconexão do WS **desiste após 5 tentativas** sem botão (`useQuintaFeira.ts:169,409`); fila offline sem limite; `speak` corta em 300 caracteres (`:311`) |
| 1.18 | **Limpar órfãos e estado global** | `QuintaTerminal`, `VoiceControl`, `StatusIndicator`, `page-with-websocket.tsx` e `FRONTEND_WEBSOCKET_GUIDE.tsx` não são usados. Estado global de módulo em `useQuintaFeira.ts:42-59` (`currentAudio`, `speakingListeners`...) causa acoplamento, e `QuintaTerminal` abriria uma 2ª conexão WS. URL do WS está hardcoded em `useQuintaFeira.ts:167` e ignora `NEXT_PUBLIC_WS_HOST` |
| 1.19 | **Isolar o `useSpeechRecognition`** | 807 linhas, ~15 refs e vários timers: é a peça mais frágil do front. Só mexer nele junto com a Fase 4 (áudio cru), não antes |

### 1A. Ganhos rápidos (esforço P)
| # | Item | Componente |
|---|---|---|
| 1.1 | **Orbe com estados**: repouso, ouvindo, pensando, falando, agindo. Hoje só pulsa ao falar | `VoiceOrb` |
| 1.2 | **Botão de parada + Esc** | `ControlDeck` (usa 0.7) |
| 1.3 | **Seletor de autonomia** em 3 posições: perguntar sempre / só o perigoso / autônoma | `ControlDeck` (usa 0.3) |
| 1.4 | **Modo economia**: com jogo em tela cheia, orbe cai para 30 fps ou congela (o backend já sabe do jogo) | `VoiceOrb` + `useSystemContext` |
| 1.5 | **Notificações discretas**: aviso proativo vira brilho na borda do orbe, com toast só para críticos | `page.tsx` + `/proactive` |
| 1.6 | `prefers-reduced-motion`, botão de pausar animações, foco visível, `aria-live` no chat | global |

### 1B. Núcleo da transparência (esforço M)
| # | Item | Componente |
|---|---|---|
| 1.7 | **Faixa "Agora"**: verbo + tool ativa ("lendo agenda…"), some sozinha | novo `NowStrip` (usa 0.6) |
| 1.8 | **Cartão de aprovação inline**: o que vai acontecer, Permitir/Negar, timeout que nega, "sempre permitir este tipo" só para risco baixo | novo `ApprovalCard` |
| 1.9 | **Chips de tool com máquina de estados** (`rodando`, `aprovação`, `ok`, `erro`, `negado`), no padrão do AI SDK | `ChatOverlay` |
| 1.10 | **Tela de Saúde**: grade verde/amarelo/vermelho do `/diagnostico` | novo `HealthPanel` |
| 1.11 | **HUD responsivo**: no celular vira pílulas + gaveta inferior (hoje some em `<md`) | `SystemHUD` |

### 1C. Maiores (esforço M-G)
| # | Item | Componente |
|---|---|---|
| 1.12 | **Painel de tarefas e plano ao vivo** (pendente/rodando/feito/erro, "desfazer" onde der). Une lembretes, foco/pomodoro, ideias, agendados | novo `TaskPanel` |
| 1.13 | **Linha do tempo de ações com replay** (reabre o resultado no Visor) | `MemoryPanel` |
| 1.14 | **Visor generativo com tipos fechados**: backend manda `{type: card\|chart\|table\|plan, props}` e a UI mapeia para componentes conhecidos. HTML livre só em iframe sandbox | `Visor` |

**Bibliotecas:** `motion` com `LazyMotion` para painéis e gavetas (compatível com React 19/Next 16 segundo a pesquisa, confirmar ao instalar). **Não adicionar:** r3f/Three.js só por estética (jogo aberto no notebook), pós-processamento pesado, CopilotKit, HTML do modelo sem sandbox.
Se o orbe atual já é leve, não trocar por shader. A decisão de avatar fica na Fase 5.

---

## FASE 2: Mais esperta

### 2A. Velocidade e custo
| # | Item | Ganho esperado |
|---|---|---|
| 2.1 | **Streaming do Gemini + fala frase a frase** (edge-tts por sentença) | Cortar os ~3 s de espera percebida (estimativa: ~1,2-2 s) |
| 2.2 | **Ampliar rotas determinísticas** (script gate): música, mídia, lembrete, foco, cotação por regra, sem chamar o LLM. Você já tem parte disso | Menos latência e tokens |
| 2.3 | **Heartbeat barato** no `ProactiveMonitor`: contexto mínimo, modelo leve, resposta `NO_REPLY` quando não há nada, horário ativo. Checagens em Python decidem se acordam o LLM | Menos tokens, menos avisos vazios |

### 2B. Memória v2 (upgrade aditivo sobre o SQLite atual)
Ordem recomendada pelo relatório de memória. **Não adotar Mem0/Graphiti/Letta.**
| # | Item | Detalhe |
|---|---|---|
| 2.4 | **Schema aditivo** | Colunas em `semantic_memories`: `valid_from`, `valid_to`, `superseded_by`, `last_accessed`, `access_count`, `importance`, `kind`, `slot`, `pinned`. Backfill sem apagar nada |
| 2.5 | **Supersessão determinística** | LLM só extrai `(entidade, atributo, valor)`; Python decide o mais novo, fecha o antigo com `valid_to`, nunca faz DELETE. **Dry run** com lista para você aprovar antes de gravar |
| 2.6 | **Recuperação com score composto** | relevância (cosseno) + recência + importância, com multiplicador de uso. Decaimento só em `event/preference`, nunca em `pinned` (alergias, nomes, datas) |
| 2.7 | **Reflexão por importância acumulada** | Além do ciclo de 6 h. Mantém teto de ≤8 fatos |
| 2.8 | **Núcleo curto sempre injetado** (perfil + lições) com limite de tamanho que força consolidar; o resto fica em busca (padrão Hermes) | Menos tokens por resposta |
| 2.9 | **Estilo/procedural versionado** | As ≤8 diretrizes viram tabela com evidência; só mudam com correção repetida |
| 2.10 | **Golden set de avaliação** | 30-50 perguntas (atualização, temporal, abstenção). Roda antes/depois de cada mudança de memória e da consolidação diária |
| 2.11 | Consolidação diária ignora linhas com `valid_to` preenchido | Evita refundir fatos já substituídos |

**Riscos da migração:** falso positivo de supersessão (estado temporário virando "contradição"), backfill de `slot`/`importance` mal classificado (marcar `slot` nulo em vez de chutar), embeddings (não reembedar, manter Gemini 768d). Reversível: limpar `valid_to`/`superseded_by`.

### 2A-bis. Custo e tarefas longas (vindo de GitHub e fóruns)
| # | Item | Detalhe |
|---|---|---|
| 2.12 | **Medir o custo do monitor proativo** | Ver se cada tick chama o LLM. Um caso relatado gastou ~US$20 em 25 checagens com 120k tokens de contexto; outro caiu de US$7 para US$0,97/dia trocando cron LLM por fluxo determinístico. Fonte de blog, tratar como ordem de grandeza |
| 2.13 | **Compressão de saída de tools** antes de ir ao LLM | Ideia do OpenHuman (TokenJuice, até ~80% segundo o README). Aplicar primeiro em WhatsApp triagem, busca de arquivos, notícias |
| 2.14 | **Tarefas longas em background** | Padrão fila `tasks/` → `results/` (Sutando) ou fila assíncrona injetada no histórico (justaniceguy): a voz/chat responde rápido e um executor pesado trabalha e avisa. Resultados são **anexados ao histórico**, não alteram o system prompt (preserva cache) |
| 2.15 | **Thinking desligado no caminho de voz** | Já feito para mensagem simples; garantir também no fluxo de voz (um caso relatou TTS lendo minutos de raciocínio) |

### 2D. Qualidade e observabilidade (vindo de GitHub e fóruns)
| # | Item | Detalhe |
|---|---|---|
| 2.16 | **Traces de cada tool call** | Persistir entrada, saída, tempo, erro. Base para eval, para a reflexão aprender e para o "replay" da UI 1.13 (OpenJarvis) |
| 2.17 | **Suíte de evals com juiz de intenção** | Vai além do smoke test de 32 checks. `isair/jarvis` publica 340/354 testes de comportamento (autorrelatado). Começar com ~50 casos: roteamento, recusa de risco, memória, "falando comigo?" |
| 2.18 | **Fila de aprovação de memórias novas** | Você confirma o que vira fato (Bestie, WUPHF). Lição dos fóruns: "lixo entra, lixo sai", um erro gravado é citado depois e se compõe. Agentes se avaliam de forma otimista demais, então a curadoria é humana |
| 2.19 | **Espelho Markdown da memória** | SQLite continua sendo a fonte. Gerar um espelho legível/editável (usar o Obsidian que você já tem) para você ver e corrigir o que ela sabe. Alternativa mais radical (memória só em Markdown, como OpenHuman) fica descartada por ora por risco de migração |
| 2.20 | **Lorebook com gatilho** | Fatos sobre você entram no prompt só quando o assunto aparece, com `sticky`, `cooldown` e teto de tokens (padrão SillyTavern). Reduz o contexto por resposta |
| 2.21 | **Explicabilidade** | O MemoryPanel mostra qual memória alimentou cada resposta (padrão do `jarvis-claude-code`) |

### 2E. Aprender com você (vindo de life OS / chief of staff)
| # | Item | Detalhe |
|---|---|---|
| 2.22 | **Lição → guarda** (maior custo-benefício do relatório) | Toda correção sua ("não faz X") vira regra em `lessons.md`; se **reincidir**, vira checagem de código antes da tool, e não só texto no prompt. Você já tem `_is_correction`; falta a segunda metade (promover a guarda) |
| 2.23 | **Orçamento de proatividade + dedupe** | Limite diário de avisos e deduplicação contra fadiga de alerta; avisos de foco falados usando a voz que já existe (padrão Omi / ai-chief-of-staff) |
| 2.24 | **Lint de memória** | Detectar contradições, entradas órfãs e lacunas (padrão llm-wiki-agent), somando à deduplicação atual e ao dry run de 2.5 |
| 2.25 | **Objetivos explícitos** (`goals`) | Arquivo de metas do Matheus como referência do briefing: "isso ajuda seus objetivos?" (TELOS do LifeOS). Incluir nota de satisfação por interação como sinal de aprendizado |
| 2.26 | **Rotinas propostas e aprovadas** | Ela observa um padrão, propõe uma rotina, você aprova e ela roda (OpenHuman). Depende da UI de aprovação (1.8) e das macros/agendados que já existem. Esforço médio-alto |
| 2.27 | **Aprender com o que você reescreve** | Quando você edita um rascunho dela (`rascunhar`), guardar a diferença como sinal de estilo (padrão do executive-ai-assistant, hoje arquivado; só a ideia vale) |

### 2C. Organização do código **[AUDITORIA]**
`brain/quinta_feira_brain.py` tem 2061 linhas e 8 papéis. Extrair, um por vez e rodando o smoke test entre cada passo (sem reescrita):

| Extração | Onde está hoje (linhas do brain) |
|---|---|
| `PromptBuilder` (system prompt + injeções) | `:268-437` e `:521-602`; o `ask()` sozinho tem 260 linhas e ~10 injeções (`:443-703`) |
| `IntentRouter` (regex de música, mídia, tela, correção...) | `:1756-1980` (vira base do "script gate" 2.2) |
| `ToolLoop` / `ToolExecutor` | `:779-935` (aqui entram risco, timeout por tool, eventos, detector de loop) |
| `BriefingService` | `:1352-1750` |
| `AddressingClassifier` ("falando comigo?") | `:1583-1665` |
| Montagem do visor | `:1985` |

Também: `main.py` (1400 linhas) diz ser "só roteador", mas o `/ambient` (`:917-988`) e ~15 serviços de startup (`:156-450`) moram lá.

**Bugs achados no caminho (corrigir junto):** alias `"agenda"` duplicado entre ReminderTool e CalendarTool, e o segundo sobrescreve (`core/tools/__init__.py:200` e `:224`); `_aliases_resolve` chamado e inexistente (`brain:908`, mascarado por `hasattr`); `tocar_youtube_invisivel` hardcoded no brain e fora do registry (`:738`, `:855`); erro de tool vira string `[ERRO...]` sem retry nem timeout (`:935`); `GeminiAdapter.stream` existe (`gemini_provider.py:150`) mas ninguém chama (é a base do 2.1).

**Código morto provável (fazer backup, não apagar às cegas; podem existir imports dinâmicos):** `backend/tools/` inteiro (usa outro `Tool`), `core/tool_registry.py` e `tool_registry_clean.py` (só `diagnose_system.py` usa), `whatsapp_tools.py`, `automation_power_method.py`, `core/brain_optimization_guide.py`, `core/sliding_window_context.py` (duplicado de `core/memory/`), `core/database.py` (duplicado de `services/database.py`), e WebSockets legados `/ws/{session_id}` e `/ws/chat/{id}` (`main.py:1088`, `:1334`).

---

## FASE 3: Autodidata (o coração do "faz qualquer coisa")

Só começa com Fases 0 e 1 prontas: depende de risco por tool e de aprovação na UI.

### 3.0 Pré-requisito: registro dinâmico de tools **[AUDITORIA]**
Hoje adicionar uma tool exige editar **à mão** `core/tools/__init__.py` em dois blocos de import (`:8-75`), chamar `registry.register(Tool(), aliases=[...])` em `inicializar_ferramentas` (`:87-275`) e atualizar `__all__` (`:279`). Existem ainda dois registries legados coexistindo. Antes de qualquer skill autodidata: (a) descoberta automática (varrer `skills/` e `core/tools/` e registrar sozinho), (b) um único registry, (c) corrigir o alias duplicado `"agenda"`. O schema chega ao Gemini por `MotorTool.get_parameters()` (`base.py:253-307`) → `Brain._get_tools_for_llm` (`brain:705-736`) → `GeminiAdapter._convert_tools` (`gemini_provider.py:269-284`); uma skill nova só precisa produzir um `ToolMetadata` válido.

### 3A. Skills escritas por ela
Formato: pasta `skills/<nome>/` com `SKILL.md` (nome ≤64 caracteres em minúsculas e hífens; descrição ≤1024; risco declarado), `scripts/` e `tests/` (padrão aberto Agent Skills).

Fluxo:
1. **Detectar lacuna**: tool `pedir_capacidade(objetivo)`, chamada pelo LLM ou disparada após 2 falhas / 16 iterações. Antes, busca por embedding nas skills existentes.
2. **Procurar pronto**: primeiro servidor MCP, depois lib pip, e só por último escrever do zero.
3. **Escrever**: modelo mais forte cria (ideia do LATM: criador caro, executor barato).
4. **Testar**: análise estática (AST + lista de imports, bloqueia `subprocess`, `socket`, `os.system` salvo declarado) → subprocesso sem rede, com timeout e pasta temporária → no máximo 3 ciclos de correção.
5. **Aprovar**: UI mostra código, permissões, saída dos testes e risco. **Só você aprova**, por um canal que não seja o texto do chat. Guarda o hash.
6. **Persistir**: repositório git **separado** só de `skills/` (rollback fácil, sem tocar no git do projeto), contagem de uso, curador que arquiva o que não é usado há 90 dias.
7. **Também propor sozinha** (padrão Hermes): depois de tarefa complexa ou correção sua, a reflexão coloca uma skill em fila `pendente` para você aprovar ou rejeitar.

Regras duras: skill nunca pode escrever em `skills/` fora do fluxo de aprovação; conteúdo externo nunca dispara criação de skill; nada de instalar skill de terceiros.
Sandbox: Windows Sandbox por CLI exige Windows 11, então no Win10 Pro é subprocesso isolado ou Docker. **Decisão sua:** você tem/quer Docker?

### 3B. MCP como fábrica de capacidades
**Arquitetura (recomendada pelo relatório MCP):**
- `~/.quinta/mcp.json` no formato `{"mcpServers": {nome: {command, args, env}}}`; skills em `~/.quinta/skills/`; plugins próprios em FastMCP.
- No `lifespan` do FastAPI, um `AsyncExitStack` abre `stdio_client` + `ClientSession` por servidor. Endpoints `/api/mcp/status` e `/api/mcp/reload` alimentam um painel na UI.
- **Caminho manual em vez do automático do `python-genai`** (que é experimental e só usa tools): `list_tools` → `FunctionDeclaration` com prefixo `servidor__tool`, `automatic_function_calling` desligado, e despacho por **nossa camada de política** (permitir/perguntar/negar, Fase 0.3) antes de `session.call_tool`.
- **Não injetar todas as tools em todo turno.** Carregar só os servidores relevantes ao pedido. Debate de 2026 no HN: um MCP do GitHub gastava ~50k tokens de schema, enquanto um `SKILL.md` que aponta para uma CLI gasta ~200. Consenso: **híbrido**, MCP onde há autenticação, skills+CLI no resto.
- Rodar cada servidor como subprocesso stdio separado (evita race condition, lição de um agente 24/7).
- **Armadilha do Windows:** `npx` falha com WinError 2 no `StdioServerParameters`; resolver com `shutil.which("npx")` ou `cmd /c npx`.
- Resultado de tool é **dado não confiável** (regra 0.4).

**Servidores a plugar, em ordem:**
1. **Playwright MCP** (Microsoft): `--cdp-endpoint` conecta ao Chrome/Edge existente. A doc avisa que não é fronteira de segurança.
2. **google_workspace_mcp**: Gmail, Calendar, Drive, Tasks (substitui o iCal de leitura por algo com escrita e aprovação).
3. **Obsidian Local REST API** (MCP embutido no plugin, com bearer token).
4. **Notion** pelo MCP remoto oficial (o repo local avisa que pode ser descontinuado).
5. **Filesystem** do repo oficial de servidores.
6. Spotify: prioridade baixa, você já controla mídia via SMTC.
7. **FastMCP** para expor as suas ~29 tools atuais e os plugins que a própria Quinta escrever (com aprovação).
8. **Não usar** `lharries/whatsapp-mcp` (parado há ~14 meses, exige CGO no Windows).

### 3D. Canal de WhatsApp mais estável (decisão sua abaixo)
Hoje: Playwright/CDP, que quebra quando o DOM muda (já aconteceu com busca e envio).
- **Cloud API oficial:** só template é entregue fora da janela de 24 h, e a Quinta é proativa, então encaixa mal. Os termos de 2026 também restringem chatbots de propósito geral (não confirmado para uso pessoal de um só usuário).
- **Sidecar `whatsmeow` (Go) ou Baileys (TypeScript)** por WebSocket, sem navegador: mais estável, **mas viola os termos do WhatsApp e há risco de banimento**. Mitigação: número secundário dedicado à Quinta, só conversa 1:1 com você, sem envio em massa nem mensagem fria. Ler grupos do seu número principal aumenta o risco.
- **Telegram como canal principal e proativo** (Bot API oficial, você já tem a ponte), com pareamento por código, allowlist de remetentes e **aprovação de tool pelo próprio chat** (padrão do Claude Code Channels).
- Playwright fica só como fallback de leitura.

### 3E. Padrões extras de autoaperfeiçoamento (só depois de 3A estável)
- **Constituição**: arquivo de identidade e limites (inspirado no `BIBLE.md` do Ouroboros) com superfícies protegidas que ela não pode editar.
- **Auto-modificação supervisionada ("self-heal com gate")**: observar → propor diff → um segundo agente cético avalia → **você aprova** → aplica em git → registra, com teste de reinício. Nunca direto. Adiar; é o item mais arriscado do plano. Skills e memória em repositório git próprio permitem reverter a autoedição (padrão Kortix/Suna).
- **Relatório de causa-raiz** quando uma tool falha repetidamente (padrão OpenHuman), em vez de só repetir o erro.
- Validar no Windows 10 o controle de app **sem roubar o foco** (Cua Driver) antes de depender dele.
- Separar **"pensador sem credenciais" de "executor com chaves"** (padrão `jarvis-assistant-vocal`).

### 3C. Controlar qualquer app do Windows
Hierarquia obrigatória: **1) API/tool dedicada → 2) UI Automation (Windows-MCP) → 3) visão por screenshot como último recurso.**
Você já tem o nível 3. O que falta é o nível 2, mais barato e preciso. Guardrails: allowlist de janelas e domínios, nada de operar no navegador logado em WhatsApp/banco sem aprovação explícita por ação, ações irreversíveis sempre confirmam.

---

## FASE 4: Voz nível Jarvis

Achado importante: o bloqueio do Python 3.14 (sem numpy/torch) parece **não valer mais**, pois o PyPI já lista wheels `cp314` para Windows de numpy, onnxruntime e sherpa-onnx (só metadados; nada foi instalado).

| # | Passo | Detalhe |
|---|---|---|
| 4.0 | **Validar o ambiente (~1 h)** | `pip install sherpa-onnx numpy onnxruntime` no venv e rodar o exemplo de speaker-id. Se falhar, o resto desta fase muda |
| 4.1 | **Captura de PCM cru** | AudioWorklet com `echoCancellation`, enviando por WS ao backend. Destrava tudo e tira a dependência do Web Speech (que o Brave bloqueia) |
| 4.2 | **Portão local** | VAD Silero via sherpa-onnx + **voiceprint do Matheus** (`SpeakerEmbeddingExtractor`; cadastro com 5-10 falas suas; calibrar limiar com suas gravações, pois os modelos são treinados em inglês/chinês). Integra ao `/ambient` |
| 4.3 | **STT local** | faster-whisper ou sherpa-onnx (Parakeet/fastconformer); comparar WER em PT-BR com suas gravações antes de escolher |
| 4.4 | **PoC do Gemini Live** como "modo conversa" | Áudio bidirecional, barge-in, function calling assíncrono, pt-BR, ~US$0,23 por 10 min segundo a pesquisa. **Cuidados:** modelos lançados há dias (confirmar nomes e limites na doc oficial), sessão de 15 min exige resumption, o áudio inteiro vai para o Google, voz é a do Google (não a Francisca). Só liga atrás do portão 4.2 para não pagar por escuta contínua |
| 4.5 | **TTS de fallback offline** | Piper pt_BR |
| 4.6 | **Wake word** | Manter o portão semântico atual. Porcupine acabou o free tier; openWakeWord só é treinado em inglês (testar "Quinta" e medir falso-aceite antes de adotar) |

---

## FASE 5: Presença e persona

Já existe: persona, humor do dia, energia por hora, estilo aprendido, voz neural. Falta rosto e uma vida interior mais visível.

**Recomendação do relatório de companions: orbe evoluído primeiro, avatar depois e opcional.**

| # | Item | Detalhe |
|---|---|---|
| 5.1 | **Orbe com "rosto abstrato"** | Olhos/boca estilizados sobre o orbe; cor, ritmo de pulso e partículas ligados ao humor interno; boca pelo envelope de amplitude do áudio (RMS), sem visemes. Custo de GPU ~zero |
| 5.2 | **Tags de emoção no stream** | O LLM emite `[emo:x]` no texto, removidas antes do TTS e mapeadas para cor/forma do orbe (padrão ChatdollKit e Open-LLM-VTuber). Precisa do streaming 2.1 |
| 5.3 | **Pensamento interno não falado** | Aparece discreto no HUD, sem gastar voz (padrão Open-LLM-VTuber). Fala proativa continua com cooldown |
| 5.4 | **Estado emocional persistente com reflexão assíncrona** | Humor/energia/confiança em arquivo, atualizados por job de fundo, mais um **diário em 1ª pessoa** e perfil de relacionamento (Soul-of-Waifu, a referência mais próxima). Incremental sobre a reflexão que você já tem |
| 5.5 | **Gaming mode** | Com jogo em tela cheia: menos proatividade, menos animação, consolidação só na ociosidade (padrão do projeto Mana) |
| 5.6 | **Turn-taking natural** | TTS fatiado por pontuação com prefetch; barge-in que **sabe o que já foi falado** (padrão Amadeus / eadmin2). Junta com a Fase 4 |
| 5.7 | (Opcional) Avatar VRM ou Live2D em janela pequena | Só se aparecer vontade real. Custo medido em relatos: renderer Live2D a ~103% de CPU e GPU do Electron a ~47%; mitigar com 30 fps, pausa quando há jogo, janela pequena, texturas reduzidas. Lip-sync existente é sobretudo EN/JA; português não consta no TalkingHead |

**Riscos da persona:** dependência emocional (memória de relacionamento, ciúme, saudade simulados aumentam apego; regra: ela não finge sofrimento nem pressiona você a ficar; inferência, sem estudo verificado), uncanny valley (orbe com microexpressões evita), custo extra de tokens da reflexão de fundo, e projetos-referência instáveis (Amica parado, Meuxe pré-release): portar ideias, não depender do código.

---

## Hologramas (implementado)

Pedir "onde fica a Bahia?" abre um **globo 3D holográfico** com o contorno real do lugar; falar de uma **viagem** ("Lisboa, 4 dias") abre painéis: resumo, atrações, cronograma, hospedagem, clima e dicas do guia. Fecha com Esc, com o X ou por voz ("fecha o holograma").

- **Dados reais e gratuitos, sem chave:** Nominatim (lugar e contorno), Overpass (atrações e hotéis mapeados no OpenStreetMap), Wikipedia/Wikivoyage (resumo e guia), Open-Meteo (previsão até 15 dias; além disso, os mesmos dias do ano anterior, rotulado como "não é previsão").
- **Nada inventado:** não existe API gratuita com preço/disponibilidade de hotel. Hospedagem = locais do OSM + botões que abrem a busca no Booking, Google Hotéis e Airbnb, com o aviso fixo "sem preço ao vivo". O cronograma é agrupamento determinístico por proximidade (sem LLM), referenciando só locais reais.
- **Onde está:** backend `core/holo/*` + `core/tools/holograma_tool.py` (tool `mostrar_holograma`); frontend `components/holo/*`, `lib/holo.ts`, estado `activeHolo` (separado do Visor). Contrato do evento `holo_show`: `core/holo/schema.py` (validado no backend E na tela).
- **Segurança:** todo texto é de terceiros, então a saída da tool é conteúdo externo (envelope + contaminação do turno); a tela renderiza só strings React, links só https de hosts permitidos; a única saída de rede é `core/holo/http.py` (allowlist, UA identificável, 1 req/s no Nominatim, cache em `backend/data/holo_cache/`).
- **O que sai para a internet:** nome do lugar, coordenadas e datas da viagem. Desligue com `HOLO_ENABLED=false`; ponha seu contato em `HOLO_CONTACT` (política do Nominatim).
- **Teste com rede real:** `python diagnostics/holo_live.py "Lisboa" viagem 4 2026-10-05`. Testes automáticos: `smoke_test.py` (`test_holograma`) e `node --test lib/holo.test.mts`.
- **Fora da v1:** fotos, preços/reservas ao vivo, voos, vários hologramas ao mesmo tempo, horário de funcionamento, roteiro por LLM.

## A9: ambiente dos subprocessos (implementado)

Terminal, PowerShell e process_adapter não herdam mais o `os.environ` inteiro: `core/host/safe_env.py` usa allowlist e nunca repassa `*_KEY`, `*_TOKEN`, `*_SECRET`, `*PASSWORD*` (extras explícitos via `SAFE_ENV_EXTRA`).

## Onda A: concluída

- **A1** primeira frase curta (`lib/streamSpeech.ts`, `primeiroCorte`): a voz começa numa vírgula/pausa ou em ~48 caracteres.
- **A2** síntese em paralelo: já era o comportamento do cliente (cada frase dispara o `/tts` na hora e toca em ordem, com época para cancelar); não precisou de `seq` no servidor.
- **A3** frases de espera (`lib/filler.ts`): 8 frases pré-sintetizadas ao conectar; tocam quando uma ferramenta lenta dispara e ela ainda não falou, no máximo uma por turno.
- **A4** pré-gate do pulso de presença (`core/proactive/pregate.py`, `PREGATE_ENABLED`).
- **A5** avaliador de aviso fail-closed, sem custo de token (`aviso_vale`): descarta vazio, curto, longo e repetido; críticos, saudação e agendados passam direto.
- **A6** escada de modelos com cooldown de 429 (`core/model_ladder.py`).
- **A7** índice de categorias da memória no prompt ("também guardo fatos sobre: …").
- **A8** bloco "LIMITES REAIS" no prompt.
- **A9** ambiente mínimo nos subprocessos.
- **A10** microfone: erro claro para `audio-capture` (volta sozinho no `devicechange`) e reinício do reconhecimento depois de suspensão do Windows (salto de relógio > 20 s no watchdog).

Próximo: Onda B (`docs/PESQUISA_CONCORRENTES.md`).

## Onda B: feita (exceto voz local)

- **B1 desfazer + quarentena** (`core/host/undo.py`): escrever/sobrescrever/apagar empilha (10) só se souber o estado anterior; apagar move para `data/quarentena/` (30 dias); desfazer confere o hash e não pisa em arquivo que você mexeu depois. Ação `undo` em `v2_file_ops`.
- **B4 orbe reativo** (`--voz` no CSS, `medirNivel` no hook): o nível do áudio que toca move o orbe, sem re-render; não liga o analisador se o AudioContext estiver suspenso (evita voz muda).
- **B5 fala interrompida** (`spoken_report`): ao ser cortada, o histórico guarda só o que foi falado + `[interrompido]`.
- **B6/B7 skills de texto com aprovação** (`core/skills/`, tool `skills`): a Quinta só PROPÕE (fila em `.runtime/skills_pendentes/`); você aprova na aba "Aprovações" do painel de memória; scanner de achados críticos, hash, versões e reverter, arquivar em vez de apagar, turno contaminado não propõe, circuit-breaker. Sem LLM de fundo.
- **B8 guarda de shell** (`core/policy/shell_guard.py`): `$()`, crase de ofuscação, `-EncodedCommand`, `iex`, download, registro, tarefas etc. fazem o gate perguntar SEMPRE (inclusive no modo autônomo) e o cartão mostra o padrão. `$()` dentro de aspas simples é literal e não conta.
- **B9 aprovação amarrada ao alvo** (`core/policy/target_hash.py`): se o script citado no comando mudar entre o cartão e a execução, não roda.
- **B10 portão de origem na memória** (`core/memory/origem.py`): a reflexão não aprende com blocos de conteúdo externo; a faxina guarda pré-imagem, aborta se apagaria mais de 30% e nem chama o LLM se nada mudou.
- **B11 traces por etapa** (`core/telemetry/traces.py`, `GET /traces`, `diagnostics/voz_eval.py`): p50/p95 de recebido, 1ª ferramenta, 1º texto, resposta final e 1º áudio.
- **B12 memória editável** (`PUT/DELETE /memoria/fatos/{id}`) e "do seu diário" no briefing da manhã, sem chamada extra.
- **B13 lições viram guardas** (`core/learning/lesson_guards.py`): lição reforçada 3 vezes vira PROPOSTA de regra; aceita, o monitor deixa de entregar aquele tipo de aviso; rejeitada nunca volta.
- **Custo extra:** cache de disco para frases curtas de TTS (`core/audio/tts_cache.py`): 20 carregamentos da tela = 8 sínteses, o que importa se houver `ELEVENLABS_API_KEY`.
- **Adiados de propósito:** B2/B14 (Whisper local) exigem baixar modelos e instalar pacotes pesados na sua máquina; B3 (TTS local só na 1ª frase) trocaria a voz no meio da frase. Precisam da sua decisão.

### Guardas de custo (rodam em todo `smoke_test.py`)
Qualquer chamada real ao Gemini durante o smoke é bloqueada e reprovada; 20 pulsos parados = no máximo 1 chamada; briefing = 1 chamada; faxina sem mudança = 0; toda chamada ao LLM no código precisa de política de custo (teste estático).

## Aprendizado das próprias falhas (implementado)

- **Registro de lacunas** (`core/learning/gaps.py`, `.runtime/lacunas.jsonl`): o `ToolRegistry` grava automaticamente ferramenta que falhou (por exceção ou por texto `[ERRO`), ferramenta inexistente e ação negada por falta de canal/permissão; o brain grava quando ela admite "não consigo/não tenho permissão" e quando você a corrige. Só campos de sistema (tipo, ferramenta, ação, causa normalizada): segredos e e-mails mascarados, nada do que você disse. Sua recusa no cartão NÃO conta como lacuna dela.
- **Revisão semanal** (`core/learning/self_review.py`): com pelo menos 5 lacunas, uma chamada de modelo leve por semana agrupa as falhas e propõe até 5 melhorias (`skill | regra | ferramenta | prompt | permissao`). Saída validada com esquema fechado; causas com cara de instrução ao modelo nem entram no prompt. Sem lacunas suficientes, ou na mesma semana, zero chamadas.
- **Você decide** na aba "Aprovações" do painel de memória (`GET /melhorias`, `POST /melhorias/{id}/aceitar|rejeitar`, `POST /melhorias/revisar`, `GET /lacunas`). Rejeitada nunca volta. Aceitar uma skill a coloca na fila de aprovação de skills; as demais ficam na sua lista. Ela nunca altera código, prompt ou permissões sozinha.
- **Casos de regressão das suas correções** (`core/learning/regressao.py`, `.runtime/casos.jsonl`): cada correção vira um caso (pergunta original, resposta ruim, sua correção, regra). A checagem automática é derivada da regra ("não use lista", "responda curto", "sem emoji", "sem markdown", "sem desculpas") e só vale se a resposta que você corrigiu FALHA nela. Camada grátis: aviso de regras que você ensinou mas não chegam ao prompt (só as 8 mais reforçadas cabem). Camada paga, só quando você pede e confirma o custo: refaz a pergunta de cada caso (1 chamada por caso, máx. 10) com o prompt real e marca regressões e melhorias contra a rodada anterior (`GET /evals`, `POST /evals/rodar`, `DELETE /evals/casos/{id}`).
- **MCP** (`core/mcp/`): cliente mínimo (JSON-RPC por stdio, sem dependência nova) para ferramentas de terceiros. Servidores só nascem do SEU `.runtime/mcp.json` (o modelo não adiciona). Cada ferramenta vira `mcp__<servidor>__<ferramenta>`: CRÍTICA (pede aprovação) salvo as que você listar em `"leitura"`; a saída é sempre conteúdo externo; o servidor roda com ambiente mínimo (sem suas chaves, só o `env` que você der a ele); prazo por chamada (servidor travado é derrubado e reiniciado, máx. 2x/hora); saída cortada em 20 mil caracteres. Exemplo de `mcp.json`: `{"servers": {"arquivos": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:\projetos"], "leitura": ["read_file", "list_directory"]}}}`. `MCP_ENABLED=false` desliga.
- **Ferramentas propostas por ela** (`core/plugins/`, tool `propor_ferramenta`): código + testes vão para quarentena (`.runtime/plugins_pendentes/`); scanner estático (allowlist de imports, sem subprocess/os/eval/open/escrita), testes só num subprocesso isolado quando VOCÊ pede, aprovação só se os testes passaram para aquele mesmo hash; grava em `plugins_agent/` com hash pinado no manifesto (conferido a cada boot), só carrega no próximo boot, é CRÍTICA a cada uso e a saída é conteúdo externo. Limite honesto: não é sandbox (Windows não limita recursos por processo); a proteção real é você ler o código antes.
- **Anti-repetição de avisos** (`core/proactive/atencao.py`): backoff por assunto (3 h, 9 h, até 24 h), teto de 4/hora e 10/dia, persistido; aviso comum sem LLM fica calado em vez de virar frase robótica.
- **`sistema` com dados reais** (`core/host/disk_usage.py`): discos, uso_de_disco, maiores_arquivos, processos, serviços (antes devolvia dados inventados).
- **Pendente:** modo `PC_ACCESS=total` (acesso ao disco inteiro, terminal sem `strict`, modo autônomo por padrão): aguarda sua decisão.

## Ordem de execução sugerida

1. **Hoje, antes de tudo:** 0.2 (fechar a rede: `127.0.0.1` + token + checagem de origem) e 0.13 (`shell=True` do `abrir_programa`). São correções pequenas e o risco é real.
2. Resto da **Fase 0** (base): 0.1, 0.3-0.12, 0.14.
3. Em paralelo: **1.0 (endpoints de dados + design tokens + acessibilidade)**, **1A (ganhos rápidos de UI)**, **2.1 (streaming)** e **4.0 (validar ambiente de voz)**.
4. **1B** (Agora + aprovação inline) e **2.2/2.3** (rotas e heartbeat).
5. **2B** (memória v2, com dry run), **2C** (extrações do brain) e **1C**.
6. **4.1-4.2** (áudio cru + voiceprint).
7. **Fase 3** (registro dinâmico 3.0, depois skills 3A, MCP 3B, UIA 3C), começando por risco baixo.
8. **4.4** (Gemini Live) e **Fase 5**.

## Métricas de sucesso

- Latência p50 de resposta simples < 2 s (hoje ~3 s).
- Tokens por resposta simples: medir antes e depois de 2.2/2.3/2.8.
- Golden set de memória: nota base registrada antes da 2.4 e nunca cair depois.
- 100% das tools de risco passando pela aprovação; 0 execuções vindas de conteúdo externo.
- Voiceprint: taxa de falso-aceite/falso-rejeite medida com suas gravações.
- Smoke test verde a cada fase.

## Fora do plano (de propósito)

Marketplace de skills de terceiros; `lharries/whatsapp-mcp`; Cloud API do WhatsApp para proatividade; frameworks inteiros de memória; enxame de subagentes para tarefa simples (custa 4-15x mais tokens segundo blogs); reescrita do brain; Three.js só por estética; Kyutai Unmute (exige GPU de 16 GB); "modo YOLO" com execução total para o Gemini; computer use no navegador logado sem aprovação.

## Decisões suas antes de começar

1. **Docker** disponível para sandbox de skills, ou só subprocesso isolado?
2. **Gemini Live** (áudio vai para o Google) é aceitável, ou voz 100% local?
3. **Autonomia padrão** ao ligar: "perguntar sempre" ou "só o perigoso"?
4. **Avatar** ou só orbe evoluído. Recomendação: orbe primeiro (5.1-5.6).
5. **WhatsApp:** aceita o risco de banimento de um sidecar `whatsmeow`/Baileys com número secundário, ou mantém Playwright e usa Telegram para o proativo?
6. **Aprovação de memórias novas (2.18):** quer confirmar cada fato novo, ou só os de categoria sensível (saúde, dinheiro, pessoas)?
