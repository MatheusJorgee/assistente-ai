# Pesquisa: o que os outros assistentes fazem e o que adaptar na Quinta-Feira

Gerado em 2026-09-24 a partir de 5 agentes de pesquisa (código do FatihMakes, runtimes de agente, voz/HUD/companions, fóruns e issues, redes sociais e criadores). Complementa `PLANO_EVOLUCAO.md`.

> **Como ler este documento.** Os agentes **leram código e páginas públicas; nada foi executado**. Eu não reverifiquei cada afirmação. O que é inferência deles está marcado "(não verificado)". Fatos do estado atual da Quinta vêm do que construímos nesta conversa.

---

## 1. Conclusões em 8 linhas

1. **O Fatih não é mágico por dentro.** ~18 mil linhas de Python, um `main.py` de 2.283 linhas fazendo tudo e uma UI de 233 KB num arquivo só. O que ele tem de bom é pontual: eco, lip-sync, desfazer, memória com índice, prompt que se descreve.
2. **A vantagem real dele é a voz**, e ela vem de uma decisão de arquitetura: app desktop + Gemini Live (áudio nativo). Não é algo que se "copia": é o caminho 4.4 do plano.
3. **Ele mesmo deixou desligado** o barge-in por voz ("sem testar em hardware") e **apagou** o planejador de tarefas que tinha. A confirmação dele é mais fraca que a nossa (3 ações, um slot, sem log).
4. **A Quinta já está à frente em segurança e autonomia:** classificação de risco por ação, aprovação na tela imposta no código, defesa contra injeção com contaminação por turno, ledger de custo, lições, streaming, parar.
5. **O maior gargalo medido é a voz** (TTS ~1,8 s por frase). Três projetos MIT/Apache mostram como atacar: primeira frase curta, síntese em paralelo com ordem, filler local.
6. **O consenso dos agentes 24/7:** o gate do proativo tem que ser **sem LLM** (senão o heartbeat queima créditos: relatos de ~2.500 créditos/dia parado), memória curada e pequena, nunca apagar (só arquivar), skill = pasta com `SKILL.md`.
7. **Os incidentes reais se repetem:** instruções de cautela perdidas na compactação, skills maliciosas (341 de 2.857 no ClawHub), instâncias expostas, loops de consolidação, falsos positivos de scanner. Todos têm defesa na nossa arquitetura ou no backlog abaixo.
8. **Licença decide o que dá para reaproveitar** (seção 3). Vários dos melhores exemplos são AGPL, GPL ou "não comercial": só ideias, reescritas do zero.

---

## 2. Quem é quem

| Projeto | Tipo | Licença | O que faz de melhor | Cuidado |
|---|---|---|---|---|
| **FatihMakes / Mark-LIV** | Desktop (PyQt6) + Gemini Live | CC BY-NC 4.0 | Voz nativa, rosto com lip-sync, desfazer, memória com índice, prompt auto-descritivo, escada de modelos | Chave em texto puro; certificado privado no histórico do git; painel de celular fraco; plugins sem sandbox |
| **gcocenza/jarvis** | **Web** (Vite/React) | **MIT** | VAD por energia no navegador, barge-in, TTS frase a frase, filler, Whisper local | Mais próximo da Quinta |
| **Open-LLM-VTuber** | Python + Live2D | MIT (modelos de exemplo têm licença própria) | Síntese por frase em paralelo com ordem, envelope de volume, tags de emoção | |
| **OpenClaw** | Runtime 24/7 (TS) | MIT (fundação) | Heartbeat barato, dreaming com portão de origem, oficina de skills com proposta, aprovações amarradas a hash | Gigante; incidentes de segurança |
| **Hermes Agent** | Runtime 24/7 (Python) | MIT | `skill_manage`, staging de escrita, aprendizado em background, curador que só arquiva | Guardas geram loops e falsos positivos |
| **nanobot (HKUDS)** | Runtime (Python) | MIT | Pré-gate sem LLM + avaliador fail-closed, Dream com git, ambiente mínimo | "Best effort" |
| **QwenPaw** | Runtime (Python) | Apache-2.0 | Guarda de shell com estado de aspas, níveis STRICT/SMART/AUTO, sandbox AppContainer no Windows | Sandbox grande e pouco auditado |
| **Vellum Assistant** | Runtime | MIT | Executor de credenciais em processo separado, envelope de conteúdo externo | |
| **nanoclaw** | Runtime | MIT | **Script gate**: script barato decide se acorda o LLM | |
| **Sutando** | Voz + executor | MIT | Fila `tasks/results` separando voz de executor, watchdogs | |
| **OpenJarvis (Stanford)** | Framework | Apache-2.0 | Traces por passo, `doctor`, evals | Voz básica |
| **ChatdollKit** | Unity | Apache-2.0 | Fatiar a 1ª frase em vírgula, fila de prefetch | |
| **Amadeus** | Desktop | **AGPL-3.0** | Época de reprodução, "o que foi realmente falado" | Só a ideia |
| **isair/jarvis** | Desktop local | **Não comercial** | Evals de voz (340/354), redação de PII, buffer de escuta | Só referência |
| **Soul-of-Waifu** | Companion | **GPL-3.0** | Estado emocional, pensamento interno | Só ideias; parte do que eu tinha dito sobre ele **não foi confirmado** |

---

## 3. Licenças: o que dá para reaproveitar

| Pode adaptar **código** (com aviso/atribuição) | Só **ideias**, reescritas do zero |
|---|---|
| MIT: gcocenza/jarvis, Open-LLM-VTuber, OpenClaw, Hermes, nanobot, Vellum, nanoclaw, Sutando | **CC BY-NC 4.0**: FatihMakes |
| Apache-2.0: QwenPaw (manter o NOTICE), OpenJarvis, ChatdollKit | **AGPL-3.0**: Amadeus |
| | **Não comercial**: isair/jarvis |
| | **GPL-3.0**: Soul-of-Waifu |

Para uso **pessoal** da Quinta, o CC BY-NC seria permitido com atribuição, mas a Quinta pode virar produto um dia: por isso a regra é **ideias, não cópia** para tudo que não seja MIT/Apache.

---

## 4. Matriz de funcionalidades

`✓` tem · `~` parcial · `—` não tem · `?` não verificado

| Funcionalidade | Fatih | OpenClaw | Hermes | nanobot | gc/jarvis | OLV | **Quinta hoje** |
|---|---|---|---|---|---|---|---|
| Voz nativa full-duplex (Gemini Live) | ✓ | — | — | — | — | — | — |
| Barge-in (interromper falando) | desligado | — | — | — | ✓ | ~ | — |
| Botão/Esc de parar | ✓ | ? | ? | ? | ✓ | ? | ✓ |
| VAD local (sem Web Speech) | ✓ | — | — | — | ✓ | ✓ | — |
| Wake word local | ✓ (inglês) | — | — | — | ~ | — | — (só por texto) |
| TTS frase a frase com prefetch | ~ | — | — | — | ✓ | ✓ | ✓ |
| Primeira frase curta / filler | ✓ (ack) | — | — | — | ✓ | — | — |
| Rosto / lip-sync | ✓ | — | — | — | ~ | ✓ | — (orbe) |
| Desfazer ações | ✓ | — | — | — | — | — | — |
| Aprovação de ações críticas | ~ (3 ações) | ✓ | ✓ | ~ | ✓ | — | **✓ (por ação, na tela)** |
| Defesa contra injeção (origem do conteúdo) | ? | ✓ | ✓ | ✓ | — | — | **✓** |
| Auditoria de decisões | — | ✓ | ✓ | — | — | — | **✓** |
| Ledger de custo por função | — | — | — | — | — | — | **✓** |
| Plugins de arquivo único | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| Skills autodidatas | — | ✓ | ✓ | ✓ | — | — | — |
| MCP | ✓ (via ADK em forks) | ✓ | ✓ | ✓ | — | — | — |
| Memória curada + índice + recall | ✓ | ✓ | ✓ | ✓ | — | — | ~ (embeddings, sem índice de chaves) |
| Consolidação de memória em background | — | ✓ | ✓ | ✓ | — | — | ✓ (diária) |
| Lições/aprender com correção | — | ~ | ✓ | ~ | — | — | ✓ |
| Proatividade | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Gate sem LLM no proativo | — | ~ | — | ✓ | — | — | ~ (regras, mas o pulso chama LLM) |
| Fallback local (LLM/STT/TTS) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Escada de modelos com cooldown de cota | ✓ | ✓ | ? | ✓ | — | — | ~ (fallback simples) |
| Canal remoto (celular) | ~ (fraco) | ✓ | ✓ | ✓ | — | — | ✓ (Telegram) |
| Traces por etapa / evals | — | ~ | ~ | — | ✓ | — | ~ (só custo; 161 checks) |
| Painel de memória editável | ✓ | ✓ | ✓ | ✓ | — | — | ~ (vê, não edita) |
| Resumo natural do dia anterior | ✓ | ✓ | ✓ | ✓ | — | — | ~ (diário existe) |

---

## 5. O que a Quinta tem que poucos têm

Pelo que os agentes leram (e sem afirmar o que **não** leram): aprovação **por ação** com resumo do que vai acontecer, contaminação por turno depois de ler conteúdo de fora, auditoria de cada decisão, ledger de custo por função, política de modelo por tarefa, streaming com voz por frase e o botão de parar que também cancela aprovações pendentes. **Mantenha e não regrida** ao copiar ideias de projetos com segurança mais fraca.

---

## 6. Backlog priorizado

Esforço: **P** pequeno (horas) · **M** médio (dias) · **G** grande (semanas). Licença: quando a fonte é MIT/Apache, código pode ser adaptado; nas demais, só a ideia.

### Onda A: barato e de alto impacto (comece por aqui)

| # | Ideia | Fonte (licença) | Esforço | Por quê |
|---|---|---|---|---|
| A1 | **Primeira frase curta:** cortar a 1ª frase numa vírgula ou em ~40 caracteres | ChatdollKit (Apache) | P | O TTS leva ~1,8 s por frase; frase menor = voz começa antes |
| A2 | **Síntese em paralelo com ordem** (`seq`) no servidor, em vez do prefetch simples | Open-LLM-VTuber (MIT) | M | Frases seguintes ficam prontas enquanto a atual toca |
| A3 | **Filler local:** 8 a 10 frases curtas pré-sintetizadas em cache, tocadas quando uma ferramenta dispara | gc/jarvis (MIT) | P | Corta a espera percebida em consultas lentas |
| A4 | **Pré-gate sem LLM no monitor proativo:** cada regra devolve `{wake, data}` em Python; só chama o Gemini se `wake` | nanoclaw + nanobot (MIT) | P | Evita a queima de créditos que derrubou o OpenClaw; hoje o pulso de presença chama LLM |
| A5 | **Avaliador de notificação fail-closed:** chamada barata `{notify}` com padrão "não avisa" | nanobot (MIT) | P | Menos avisos vazios |
| A6 | **Escada de modelos com "esgotado até T":** 429 tira o modelo por 5 min e cai para o próximo | Fatih (ideia) + nanobot | P | Evita a Quinta ficar muda quando a cota acaba (Anthropic e Google já restringiram assinaturas de terceiros) |
| A7 | **Índice de chaves da memória no prompt** ("também lembro: …") + teto por categoria | Fatih + Hermes (ideia / MIT) | P | O modelo passa a saber o que pode buscar; reduz tokens (item 2.8 do plano) |
| A8 | **Prompt auto-descritivo:** capacidades geradas das ~29 tools reais e limites da arquitetura | Fatih (ideia) | P | Menos alucinação de capacidade |
| A9 | **Ambiente mínimo nos subprocessos** (sem `GEMINI_API_KEY`) | nanobot (MIT) | P | **Conferir agora:** o terminal da Quinta pode herdar as chaves |
| A10 | **Robustez de áudio:** detectar microfone ausente com erro claro; reconectar depois de suspender o Windows | Issues do Mark-LIV (#94, #115) | P | Bugs que os usuários dele mais sofrem |

### Onda B: médio

| # | Ideia | Fonte (licença) | Esforço |
|---|---|---|---|
| B1 | **Desfazer:** pilha de 10, só empilha se souber o estado anterior; apagar vai para **quarentena** em vez de excluir | Fatih (ideia) | M |
| B2 | **VAD por energia local + Whisper local** (sai da Web Speech, que o Brave bloqueia); habilita o barge-in | gc/jarvis (MIT) | M-G |
| B3 | **TTS local para a 1ª frase** (voz do navegador, Piper ou Kokoro) e edge-tts para o resto | gc (MIT) | M |
| B4 | **Orbe reativo à voz:** nível do `AnalyserNode` (ou envelope de volume calculado no servidor) e tags de emoção `[joy]` que mudam cor/forma | gc + OLV (MIT) | P-M |
| B5 | **Registrar o que foi realmente falado ao ser interrompido** (prefixo + marca "[interrompido]" no histórico) | Amadeus (só ideia) | P |
| B6 | **Staging de escrita de memória e skills** (`pending_writes` com hash-base, gate fechado por padrão) | Hermes (MIT), OpenClaw (MIT) | M |
| B7 | **Skills autodidatas v1** (só texto `SKILL.md`, sem scripts): proposta em quarentena, scanner, aprovação com diff, rollback (esboço no fim) | Hermes + OpenClaw + nanobot | M-G |
| B8 | **Guarda de shell com estado de aspas para PowerShell** (`$()`, crases, `-EncodedCommand`, `iex`, `<#`) ligada à classificação de risco | QwenPaw (Apache) | M |
| B9 | **Aprovação amarrada a hash do alvo** (argv, cwd, sha256 do script; nega se mudou) | OpenClaw (MIT) | P-M |
| B10 | **Portão de origem na consolidação de memória** (candidato vindo de conteúdo externo não entra) + preimage antes de reescrever | OpenClaw dreaming (MIT) | M |
| B11 | **Traces por etapa** (fim da fala → 1º token → 1ª frase → 1º byte de áudio) e **evals de voz** | OpenJarvis (Apache) | M |
| B12 | **Painel de memória editável** (corrigir/apagar fato) e **"ontem você falou de X"** no briefing da manhã | Mark L/LII (ideia) | P-M |
| B13 | **Lições → guardas:** contador de recorrência; ao chegar em N, propõe regra do monitor/classificador de risco (não texto de prompt), com veredito registrado para nunca repropor as rejeitadas | ai-chief-of-staff (MIT) | M |
| B14 | **Fallback local de STT/TTS em PT-BR** (Whisper, Kokoro) para quando a cota do Gemini acaba | TabNews + Fatih | M |

### Onda C: grande

| # | Ideia | Nota |
|---|---|---|
| C1 | **Gemini Live como modo conversa** (áudio nos dois sentidos, ~450-600 ms realistas no Brasil segundo teste do TabNews) atrás de portão local (VAD + voz) | Áudio vai ao Google; modelos novos (confirmar). É o item 4.4 do plano |
| C2 | **Sandbox para skills com scripts** (AppContainer no Windows ou executor separado) | Só depois das skills de texto |
| C3 | **Integração MCP** com política de aprovação por chamada | Itens 3.0 e 3B do plano |
| C4 | **Rosto animado** (Canvas/SVG guiado por áudio, sem GPU) | Depois de B4; avaliar se vale |
| C5 | **Plugins de arquivo único** com risco declarado | Depois do registro dinâmico (3.0) |

---

## 7. Recomendação de ordem

1. **Onda A inteira em uma sequência** (A1, A2, A3 atacam o gargalo medido de voz; A4-A6 cortam custo e mudez; A7-A8 melhoram a inteligência; A9 é uma checagem de segurança; A10 dá robustez).
2. **B3 + B2** (voz local): tira a dependência da Web Speech.
3. **B1 (desfazer)** e **B12 (painel de memória editável)**: são os ganhos mais visíveis no dia a dia.
4. **B6/B7 (skills autodidatas)** quando a base de segurança estiver pronta (já está em boa parte).
5. **C1 (Gemini Live)** depois de medir (B11).

---

## 8. Esboço: skills autodidatas com aprovação (v1)

**Formato:** `skills/<nome>/SKILL.md` com frontmatter (`name` por regex, `description` curta, `created_by: agent`) e `references/`. **Só texto de instruções na v1** (sem scripts), porque não há sandbox.

**Fluxo:** um passo de revisão em background (modelo barato, no ledger de custo) propõe uma skill só se o mesmo fluxo apareceu 2 ou mais vezes ou depois de uma correção sua. A proposta **nunca escreve em `skills/`**: vai para `pending_writes` com o hash-base. O scanner roda na proposta e de novo ao aplicar (só achado **crítico** bloqueia, para evitar os falsos positivos do Hermes). Você vê o diff, aprova, rejeita ou coloca em quarentena. Aplicar = gravação atômica e versão anterior guardada.

**Guardas obrigatórias:** o agente só edita skills `created_by: agent`; ler antes de escrever; tetos (~40 KB por skill, 50 pendentes); editar uma existente antes de criar nova; **turno contaminado não propõe nem edita** (é o caso real do QwenPaw: uma injeção mandando "apague todas as skills"); apagar só arquiva; **circuit-breaker** de 3 falhas iguais (os loops do Hermes e do nanobot vieram da falta disso).

---

## 9. O que NÃO copiar

- Chave da API em texto puro num arquivo; certificado privado no repositório (Fatih). **Confira o `.gitignore` da Quinta.**
- Painel de celular por HTTP puro com PIN curto e criptografia sem autenticação (Fatih).
- Confirmação de um slot só, sem log nem classificação de risco (Fatih): a nossa é melhor.
- Plugins no mesmo processo, sem tempo limite, sem sandbox, sem permissões declaradas.
- Barge-in por voz "no chute": o próprio Fatih o mantém desligado.
- Controle de computador por screenshot completo + "x,y" por regex (caro e impreciso).
- Bloqueio de assunto por lista de palavras; memória em um JSON único com corte por data.
- Deixar o gate falhar **aberto** (o Hermes falha aberto se o módulo não importa): o nosso falha fechado, mantenha.
- Planejador de tarefas com regras rígidas: o Fatih o removeu por causa de round-trips.

---

## 10. Lacunas da pesquisa (o que faltou e como complementar)

- **Reddit:** bloqueado para os agentes; os números de lá vêm de blogs que o citam. Lobsters, Bluesky, Mastodon e Discord nem foram tentados.
- **Vídeos:** YouTube barrou com captcha; Instagram, TikTok e X não foram acessados. **Ninguém viu os vídeos do @fatihmakes.** Se você me disser o que neles mais te impressionou, ajusto a prioridade.
- **Não lidos:** Project AIRI e `eadmin2/jarvis_ai`; a implementação dos níveis de confiança do Vellum e o `rule_guardian` do QwenPaw.
- **Inconsistências:** uma busca listou um repo "Mark-LII" do Fatih e o agente de código diz que ele não existe (não verificado). Os forks "Shirazi" e "AI-ASSISTANCE" não foram encontrados de novo.
- **Sem medições:** nenhum projeto publica latência de TTS medida; as metas de latência do plano de voz são estimativas.
