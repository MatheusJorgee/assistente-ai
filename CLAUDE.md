# CLAUDE.md — Quinta-Feira

Veja **`AGENTS.md`** primeiro: stack, como rodar/testar, arquitetura de roteamento determinístico×LLM,
convenções e a lista do que não fazer sem aprovação. Este arquivo só tem o que é específico de trabalhar
aqui *via Claude Code*.

## Antes de editar

- `python diagnostics/smoke_test.py` (backend, `PYTHONUTF8=1` no console) tem que terminar "0 falhou" antes
  de considerar qualquer tarefa pronta. Ele é rápido e **não gasta crédito de API** — é o jeito de provar
  isso a cada feature nova, que é uma exigência explícita do usuário.
- O usuário roda backend/frontend fora desta sessão boa parte do tempo. Não assumir que a porta 8000/3000
  está livre; checar antes (`Get-NetTCPConnection -LocalPort 8000,3000 -State Listen`) e nunca derrubar um
  processo que já estava rodando sem perguntar.
- Scripts de edição multi-trecho: usar o Write tool para gravar um `.py` no scratchpad e rodá-lo, em vez de
  heredoc via Bash — heredocs aqui mangle `\n`/escapes dentro de strings Python com frequência.

## Memória (`~/.claude/.../memory/`)

O índice em `MEMORY.md` tem o histórico do projeto (features, gotchas, bloqueios). Ler antes de assumir que
algo "não existe ainda" — é comum já ter sido construído em sessão anterior. Gotchas recorrentes que valem
conferir antes de reintroduzir o mesmo bug: busca do YouTube (`gotcha-youtube-search.md`), config/worktree do
git (`feedback-git-config.md`), exigência de teste de custo (`feedback-teste-de-custo.md`).

## Bloqueios conhecidos (não insistir sem o usuário decidir)

- `git status`/`add`/`commit` falham por um worktree fantasma (`festive-euler`) herdado de um caminho antigo
  do projeto. `git log`/`diff` funcionam. Não tentar "corrigir" isso sem pedido explícito.
- Subir o backend por conta própria às vezes é bloqueado pelo classificador de permissões do Claude Code
  ("Interfere With Workloads"). Quando isso acontecer, não contornar por outro caminho — explicar e pedir
  pro usuário rodar (ou usar o atalho "Quinta-Feira" na área de trabalho, que chama
  `scripts\quinta_control.ps1`).
- `PC_ACCESS=total` (acesso irrestrito ao PC) depende de o usuário liberar uma regra de permissão ou setar
  `AUTONOMY_MODE=autonoma` no `.env` — não é algo para destravar por conta própria.
