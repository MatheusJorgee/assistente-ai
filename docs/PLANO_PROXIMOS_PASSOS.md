# Plano: próximos passos da Quinta-Feira

## STATUS (2026-09-24)

| Item | Estado | Observação |
|---|---|---|
| 1.1 Versionar | **BLOQUEADO (D1)** | `git status` na pasta do projeto falha por causa do worktree fantasma `festive-euler`; consertar é mexer em config/worktree do git (vetado). Só li o estado. |
| 1.2 Backup da memória | feito | `core/host/backup.py`; diário automático; restauração no próximo boot (`/backups`) |
| 1.3 Token por sessão | feito, em modo **registrar** | virar `SESSION_TOKEN_MODE=exigir` depois de validar com o backend real |
| 1.4 Chaves no cofre do Windows | feito (código); **migração é sua** | `python -m core.host.segredos status` / `migrar [--limpar-env]` |
| 1.5 Telegram | feito | sem dono automático; só dono configurado, só conversa privada |
| 2.1 Dados falsos | feito | `capturar_tela` era falsa (achado); agora real; teste permanente contra simulação |
| 2.2 Player da música | **sem mudança (de propósito)** | publicar o evento faria tocar em dobro |
| 2.3 Teste com Gemini real | feito (opt-in) | `python diagnostics/integracao_real.py --confirmo` |
| 2.4 Painel único | feito | `GET /painel` + aba "Saúde" |
| 3.1 Ver o resultado (Steam) | feito | tool `abrir_e_olhar` |
| 3.2 Pendências próprias | feito | reflexão + retomada 1x/dia, 3 toques, arquiva sozinha |
| 3.3 Bastidor | feito | 2 pesquisas + 2 chamadas leves por noite, 2h–6h, ele ausente |
| 3.4 Aprender com a reação | feito | respondida × ignorada ajusta o intervalo de cada tipo de aviso |
| 4.1 Voz local | **adiado (D4)** | precisa baixar modelos |
| 4.2 Latência real | pendente | precisa do backend real (`/traces`, `voz_eval.py`) |
| 5.1 Dividir arquivos grandes | pendente | só depois de versionar (D1) |
| 5.2 Lint | parcial | 41 → 18 problemas; os 18 restantes são regras do React sobre efeitos/dependências (mudam comportamento) e 2 arquivos de exemplo |

Cobre os 18 pontos levantados na conversa. Tamanhos: **P** = pequeno (uma sessão curta), **M** = médio, **G** = grande (várias sessões). Nenhum tamanho é promessa de prazo: é ordem de grandeza.

**Regras que valem em todos os itens** (você pediu; estão no smoke test):
- todo item traz teste; nenhum teste chama a API do Gemini (o smoke bloqueia e reprova se tentar);
- se o item toca o modelo, um teste com contador fixa o teto de chamadas por cenário;
- mudança de segurança só aperta; afrouxar (acesso total, autonomia) só com a sua decisão explícita;
- nada de git sem a sua aprovação (regra da sua memória).

---

## Fase 0: decisões suas (bloqueiam outras fases)

| # | Decisão | Bloqueia | Minha recomendação |
|---|---|---|---|
| D1 | Autorizar o versionamento do trabalho (ponto 18) | Fases 1 e 5 | Sim, primeiro de tudo |
| D2 | Liberar o modo de acesso total ao PC (ponto 2) | item 2, item 12 | Só depois do item 1 (token) |
| D3 | Vai ligar o Telegram? (ponto 4) | item 4 | Se não vai, pular a auditoria |
| D4 | Adiar ou fazer a voz local (ponto 14) | Fase 4 | Adiar até a Fase 3 |

---

## Fase 1: proteger o trabalho e fechar a superfície

### 1.1 Versionar o trabalho (ponto 18) — **P, depende de D1**
- **Problema:** nada do que foi feito está em commit; um worktree fantasma bloqueia o git.
- **Como:** (1) só LER o estado (`git status`, `git worktree list`, `git branch`) e mostrar a você; (2) você decide o que fazer com o worktree fantasma (eu não mexo em config nem em worktrees); (3) com a sua aprovação, uma branch nova e commits em blocos coerentes (segurança, holograma, aprendizado, MCP/plugins, voz/custo, docs); (4) conferir que `.env`, `.runtime/`, `data/` e `plugins_agent/` NÃO entram.
- **Pronto quando:** `git status` limpo numa branch com histórico legível, e um `git ls-files` sem nenhum segredo.

### 1.2 Cópia de segurança da memória (ponto 5) — **P–M**
- **Como:** rotina diária que copia `quinta_feira.db`, `people.db`, `ideas.db`, lembretes, lições, `lessons.json`, `melhorias.json`, `casos.jsonl` para `backups/AAAA-MM-DD/` (SQLite via API de backup, sem travar), mantém 14 dias, e expõe `GET /backups` e "restaurar" com confirmação.
- **Teste:** cria dados, faz backup, corrompe, restaura e confere; teto de espaço; zero chamadas de modelo.
- **Pronto quando:** restaurar de ponta a ponta funciona num diretório temporário.

### 1.3 Token por sessão no backend (ponto 1) — **M**
- **Como:** o backend gera um token aleatório ao subir (arquivo local só do seu usuário); o frontend o recebe pelo Next (rota do servidor, nunca no bundle público) e o manda no WebSocket e nos POSTs; sem token válido, recusa. O guarda de origem atual continua.
- **Risco:** quebrar o frontend ou o Telegram/scripts locais; por isso, primeiro modo "só registrar" por uma sessão, depois "exigir".
- **Teste:** cliente sem token é recusado; com token passa; token errado é registrado; sem regressão no smoke.
- **Pronto quando:** `curl` sem token recebe 401 e o app funciona normal.

### 1.4 Chaves fora do texto puro (ponto 3) — **M**
- **Como:** guardar as chaves no Gerenciador de Credenciais do Windows (`keyring`) e ler de lá; `.env` só com o que não é segredo. Migração assistida (você roda um comando; eu não leio o `.env`).
- **Depende de:** D1 (versionado antes) e do item 1.3.
- **Pronto quando:** o backend sobe sem chaves no `.env` e a `safe_env` continua bloqueando vazamento para subprocessos.

### 1.5 Auditoria do Telegram (ponto 4) — **P, depende de D3**
- **Como:** ler `telegram_bridge.py` inteiro; exigir `TELEGRAM_CHAT_ID` preenchido (sem "primeiro que escrever vira dono"); toda ação vinda dele com origem `telegram`, nunca com mais poder que o chat; teste de mensagem de outro chat.
- **Pronto quando:** sem `CHAT_ID` a ponte se recusa a iniciar.

---

## Fase 2: verdade e confiabilidade

### 2.1 Caçar dados falsos nas ferramentas (ponto 6) — **M**
- **Como:** varrer todas as ferramentas por simulação (`mock`, `simula`, `Simulação`, dados fixos): `process_control`, `network_scan`, `whatsapp`, `discord` e o resto. Para cada uma: real, ou removida, ou devolvendo `[ERRO] não implementado` (nunca dado inventado).
- **Teste permanente:** um teste estático que reprova se aparecer texto de simulação em saída de ferramenta.
- **Pronto quando:** lista das ferramentas com veredito (real / consertada / desativada) no doc.

### 2.2 Player da música na tela (ponto 9) — **P**
- **Como:** com o backend real rodando, pedir "toca X" e observar se o evento `media_playback_requested` chega; se não, publicar o evento na `TocarMusicaTool`.
- **Precisa de você:** reiniciar o backend e me dizer o que apareceu (ou eu observo por Playwright).

### 2.3 Teste opt-in com o Gemini de verdade (ponto 7) — **M**
- **Como:** `diagnostics/integracao_real.py`, nunca no smoke; roda ~5 conversas fixas (música, holograma, "o que ocupa espaço", uma correção, uma pergunta simples), mostra chamadas e custo antes de rodar e exige `--confirmo`.
- **Pronto quando:** relatório passa/falha com custo real medido e comparado ao orçamento.

### 2.4 Painel único de custo e qualidade (ponto 8) — **M**
- **Como:** uma rota `/painel` e uma aba na tela juntando gasto do dia (ledger), latência (`traces`), falhas (`lacunas`), regressões (`evals`), avisos falados hoje (atenção) e backups.
- **Pronto quando:** uma tela responde "quanto gastei hoje, o que falhou, o que piorou".

---

## Fase 3: autonomia e inteligência

### 3.1 Ver o resultado das ações — o caso da Steam (ponto 12) — **M, depende de 1.3 e D2**
- **Como:** lista de programas que VOCÊ marca ("olhar a tela depois de abrir"); depois de abrir, uma captura + uma chamada de modelo com imagem (só para esses) diz se há escolha de conta/login; ela PERGUNTA qual conta; sua resposta vira preferência salva. Clique só com uma ferramenta de UI restrita, com confirmação na primeira vez; **nunca digita senha**.
- **Teste:** contador de chamadas (no máximo 1 com imagem por abertura de programa marcado); zero para os não marcados.

### 3.2 Pendências próprias (ponto 10) — **G**
- **Como:** extrair, sem LLM extra (na reflexão diária que já roda), o que ficou em aberto; guardar como lista com estado (aberta, em andamento, resolvida, dispensada); a Quinta a consulta uma vez por dia e propõe UM próximo passo; você dispensa ou aceita.
- **Custo:** dentro do orçamento diário de iniciativa (novo teto, com teste de simulação de 30 dias).

### 3.3 Trabalho de bastidor só de leitura (ponto 11) — **M, depende de 3.2**
- **Como:** de madrugada, para pendências abertas, preparar material (pesquisa, resumo) em `bastidor/`, sem executar nada crítico; entregar quando você abrir a tela. Cada tarefa com teto de chamadas e de tempo.

### 3.4 Aprender com a reação à iniciativa (ponto 13) — **M, depende de 2.4**
- **Como:** registrar, para cada fala espontânea, o desfecho (ignorada, cortada com Esc, respondida, elogiada) e ajustar frequência por tipo; visível no painel; reversível.

---

## Fase 4: voz (depende de D4)

### 4.1 Voz local (ponto 14) — **G**
- Whisper local para reconhecimento e Piper/Kokoro para fala, como plano B quando a cota acaba e para tirar a dependência da Web Speech (Brave). Exige baixar modelos e instalar pacotes: eu peço a sua liberação antes de instalar qualquer coisa.

### 4.2 Medir a latência real (ponto 15) — **P**
- Usar `/traces` e `voz_eval.py` com o backend real por alguns dias; só então decidir onde otimizar.

---

## Fase 5: qualidade do código (depende de 1.1 e de testes verdes)

### 5.1 Quebrar arquivos grandes (ponto 16) — **G**
- `quinta_feira_brain.py` (~2.400 linhas) em módulos por responsabilidade (roteamento, prompt, ferramentas, proativo); `useQuintaFeira.ts` em hooks menores (WebSocket, fala, aprovações, holograma).
- **Regra:** refatoração pura, sem mudar comportamento; o smoke inteiro (490 checks) precisa continuar verde a cada passo, um módulo por vez, cada um num commit.

### 5.2 Avisos de lint antigos (ponto 17) — **P**
- Zerar os 10 avisos dos hooks; travar com `eslint` no fluxo de teste.

---

## Ordem de execução

```
Fase 0 (decisões) ─► 1.1 versionar ─► 1.2 backup ─► 1.3 token ─► 1.4 chaves ─► 1.5 Telegram
                                  └─► 2.1 dados falsos ─► 2.2 player ─► 2.3 teste real ─► 2.4 painel
                                                                            └─► 3.1 ver resultado ─► 3.2 pendências ─► 3.3 bastidor ─► 3.4 reação
                                                                            └─► 4.2 latência ─► 4.1 voz local (se D4)
                                                                            └─► 5.2 lint ─► 5.1 refatorar
```

Pode andar em paralelo: 2.1 com 1.2/1.3 (não se tocam) e 5.2 a qualquer hora.

## Marcos e critério de "feito"

| Marco | Itens | Como saber que fechou |
|---|---|---|
| **M1 Seguro** | 1.1–1.5 | tudo versionado, backup restaurando, backend exige token, sem chave em texto puro |
| **M2 Honesto** | 2.1–2.4 | nenhuma ferramenta inventa dado; teste real com custo medido; painel único |
| **M3 Autônomo** | 3.1–3.4 | pendências vivas, bastidor entregue, reação medida, tudo dentro do orçamento |
| **M4 Sustentável** | 4.x, 5.x | voz de reserva local (se aprovada), código dividido, lint limpo |

## Riscos do plano

- **Token por sessão (1.3)** pode quebrar o frontend; mitigado pelo modo "só registrar" antes de exigir.
- **Refatorar (5.1)** é onde mais dá erro de edição; só depois de tudo versionado e com o smoke verde a cada passo.
- **Autonomia (Fase 3)** aumenta gasto e superfície; cada item nasce com teto de chamadas e simulação de custo.
- **Acesso total (D2)** amplia o dano possível de um erro dela; por isso vem depois do token e continua perguntando quando a ordem vier de texto de terceiros.
- **O que eu não consigo verificar daqui:** roteador/firewall, comportamento real do Gemini nas conversas (só o item 2.3 mede isso) e o player/áudio (item 2.2 e 4.2 precisam do backend real rodando).
