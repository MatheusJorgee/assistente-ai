# Mapa do site — Quinta-Feira (2026-10-07)

Inventário de páginas, API, WebSocket e ferramentas, para achar pontas soltas. Não é um scan de segurança
(para isso, ver a skill `security-review` ou pedir um pentest da superfície local). Gerado por leitura direta
do código, não por execução — revalidar antes de confiar em algo crítico.

## Frontend — páginas (`frontend/app/`)

| Rota | Arquivo | Uso |
|---|---|---|
| `/` | `app/page.tsx` (303 linhas) | página principal, monta todos os componentes |
| `/terminal` | `app/terminal/page.tsx` | console alternativo |
| `/diagnose` | `app/diagnose/page.tsx` | diagnóstico visual |
| `/api/chat` | `app/api/chat/` | rota Next (proxy?) |
| `/api/quinta-token` | `app/api/quinta-token/route.ts` | emite o token de sessão (`lib/quintaAuth.ts`) |

**Achado:** `app/page-with-websocket.tsx` (68 linhas) não é importado por nada (`grep` não achou
referência). É código morto — ou uma versão anterior de `page.tsx` que sobrou, ou um experimento abandonado.
Candidato a apagar (confirmar com o usuário antes).

**Achado:** `app/api/chat/` é um diretório **vazio** (sem `route.ts`) — não serve nada; só ocupa espaço no
mapa de rotas do Next. Candidato a remover.

## Backend — API HTTP (`backend/main.py`)

Agrupado por área; `GET/POST/PUT/DELETE` conforme o código.

- **Saúde/status:** `/health`, `/api/health`, `/status`, `/context`, `/diagnostico`, `/custo`, `/painel`, `/traces`
- **Chat:** `/chat`, `/api/chat`, `/profile`
- **Memória:** `/memoria/fatos/{id}` (PUT/DELETE), `/memoria/saude`, `/memoria/conflitos` (GET/POST
  `{hid}/{acao}`), `/memoria/esqueciveis`, `/reflect`, `/consolidar_memoria`
- **Conteúdo:** `/news`, `/curiosity`, `/tts`, `/proactive`
- **Autonomia/aprovação:** `/autonomia` (GET/POST), `/auditoria/acoes`, `/licoes` (GET/DELETE),
  `/evals` (GET/POST `/rodar`/DELETE `/casos/{cid}`), `/lacunas`, `/melhorias` (GET/POST `/revisar`/
  `{pid}/{decisao}`), `/pendencias` (GET/POST `{pid}/{estado}`), `/guardas/propostas` (GET/POST
  `{pid}/{decisao}`)
- **Backups:** `/backups` (GET/POST `/agora`/POST `/restaurar`)
- **Plugins/skills:** `/plugins` (GET/POST `{pid}/testar`/`{pid}/{decisao}`), `/skills` (GET/POST
  `pendentes/{pid}/{decisao}`/POST `{nome}/reverter`/DELETE `{nome}`)
- **Briefing/ambiente:** `/briefing_ritual`, `/ambient`
- **Logs:** `/api/logs`
- **WebSocket:** `/ws/{session_id}`, `/ws/chat/{session_id}`

**Achado (confirmado, não só suspeita):** o frontend em uso só fala com `/ws/{session_id}` (conecta em
`ws://127.0.0.1:8000/ws/quinta` — `"quinta"` é o `session_id`, um valor fixo, não uma rota própria) e com
endpoints HTTP comuns (`/tts`, `/profile`, `/memoria/*`, `/proactive`, etc. via `hooks/useQuintaFeiraUI.ts`
`HTTP_BASE`). Três rotas do backend não têm NENHUM chamador no frontend atual nem teste no smoke:
- `POST /chat` (fallback HTTP; docstring diz "quando WebSocket não entrega resposta", mas nada no frontend
  o chama hoje)
- `POST /api/chat` (docstring diz "usado por `frontend/app/page.tsx`"; isso está desatualizado — quem usava
  era `page-with-websocket.tsx`, o arquivo morto acima)
- `WS /ws/chat/{session_id}` (docstring: "alias... para compatibilidade com frontend"; nenhum frontend atual
  conecta nele)

Não apaguei nada — só confirmei que não há chamador vivo. Antes de remover, vale checar se algum cliente
externo (Telegram bridge? script de teste manual?) bate numa dessas rotas.

## WebSocket — tipos de mensagem (`frontend/hooks/useQuintaFeira.ts`)

Do servidor para o cliente: `intermediate_status`, `brain_response`, `error`, `pong`, `approval_requested`,
`approval_resolved`, `text_delta`, `text_reset`, `holo_show`, `holo_hide`, `tool_call_start`,
`tool_call_result`, `run_cancelled`, `runtime_event`.

## Ferramentas registradas (`backend/core/tools/__init__.py`)

34 chamadas a `registry.register(...)`. Lista completa de aliases está no próprio arquivo. Todo tool novo
deve ter: classificação de risco (`core/policy/tool_risk.py`), teste no smoke sem chamada real, e — se
devolve conteúdo de fora — passar pelo envelope de `content_origin.py`.

## Dívida técnica conhecida (tamanho de arquivo)

| Arquivo | Linhas | Nota |
|---|---|---|
| `backend/brain/quinta_feira_brain.py` | ~2500 | concentra roteamento determinístico + prompt + execução de tools; candidato a split (ex.: roteadores em módulo próprio) |
| `backend/main.py` | ~1800 | todos os endpoints num arquivo; candidato a `APIRouter` por área (memória, aprovação, plugins...) |
| `backend/automation.py` | ~1400 | automação de SO/YouTube/Twitch; parte já tem `core/media/*` extraído — continuar essa extração |
| `backend/diagnostics/smoke_test.py` | ~4000 | cresce 1 função de teste por feature; aceitável para um smoke test, mas fica pesado para navegar — considerar dividir por área em import |

## Como usar isto para achar falhas

1. **Rotas sem teste correspondente:** cruzar esta lista de endpoints com `grep -n "def test_" diagnostics/smoke_test.py`
   — qualquer endpoint sem menção é candidato a cobertura.
2. **Caminhos duplicados:** os pares `/chat`×`/api/chat` e `/ws/{session_id}`×`/ws/chat/{session_id}` acima.
3. **Código morto:** `page-with-websocket.tsx` já achado; vale repetir a busca por "nenhuma referência" em
   `frontend/components/` e `backend/core/tools/` periodicamente (tools registradas mas nunca chamadas pelo
   roteamento determinístico nem mencionadas no system prompt são um sinal, não uma prova).
4. **Dois caminhos para a mesma coisa:** `automation.py` (motor real do YouTube) e
   `core/async_youtube_handler.py` (mencionado na memória do projeto como "caminho morto") — revalidar se
   `async_youtube_handler.py` ainda é usado por algo antes de remover.
