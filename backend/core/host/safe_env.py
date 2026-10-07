"""
Ambiente MINIMO para subprocessos comandados pelo LLM (correcao A9).

O problema: o backend carrega o `.env` no `os.environ` (GEMINI_API_KEY, TAVILY_API_KEY,
ELEVENLABS_API_KEY, TELEGRAM_BOT_TOKEN...) e todo subprocesso filho HERDA isso. Entao um comando
de terminal — mesmo aprovado por voce na tela — enxergava todas as suas chaves
(`echo $env:GEMINI_API_KEY`), e um comando malicioso podia leva-las embora.

A defesa e por ALLOWLIST: so passa o que o Windows/ferramentas precisam para funcionar.
Uma variavel nova (ou uma chave com nome que ninguem previu) NAO vaza por esquecimento, como
aconteceria com uma denylist. Uma denylist por padrao de nome ainda vence a allowlist (cinto e
suspensorio). Para liberar algo de proposito (ex.: GITHUB_TOKEN p/ um `git push`), use
SAFE_ENV_EXTRA=NOME1,NOME2 no ambiente — e uma decisao explicita sua.

ATENCAO: nao remova SystemRoot — sem ele o winsock e o Python quebram no Windows.
"""

import os
import re
from typing import Dict, Iterable, Mapping, Optional

# Nomes (em MAIUSCULAS: no Windows o ambiente nao diferencia caixa) que os processos precisam.
_PERMITIDAS = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "OS",
    "TEMP", "TMP", "TMPDIR",
    "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH", "USERNAME", "USERDOMAIN", "COMPUTERNAME",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PUBLIC", "ALLUSERSPROFILE",
    "NUMBER_OF_PROCESSORS", "PSMODULEPATH", "DRIVERDATA",
    "LANG", "LANGUAGE", "TZ", "TERM", "SHELL",
    "PYTHONUTF8", "PYTHONIOENCODING", "NO_COLOR",
})

# Familias de nomes permitidas por prefixo.
_PREFIXOS_PERMITIDOS = (
    "PROCESSOR_", "PROGRAMFILES", "COMMONPROGRAMFILES", "PROGRAMW6432", "COMMONPROGRAMW6432", "LC_",
)

# O que NUNCA passa, mesmo que apareca numa allowlist/prefixo: cara de segredo.
_PADRAO_SEGREDO = re.compile(
    r"(_KEY$|_TOKEN$|_SECRET$|_PASSWORD$|_PASSWD$|PASSWORD|SECRET|TOKEN|API_?KEY|CREDENTIAL|PRIVATE_KEY)",
    re.IGNORECASE,
)


def _parece_segredo(nome: str) -> bool:
    return bool(_PADRAO_SEGREDO.search(nome))


def _permitida(nome: str) -> bool:
    n = nome.upper()
    return n in _PERMITIDAS or any(n.startswith(p) for p in _PREFIXOS_PERMITIDOS)


def _extras_do_ambiente() -> set:
    bruto = os.environ.get("SAFE_ENV_EXTRA", "")
    return {x.strip().upper() for x in bruto.split(",") if x.strip()}


def build_env(
    extra: Optional[Iterable[str]] = None,
    fonte: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Ambiente reduzido para `subprocess`/`asyncio.create_subprocess_*`.

    `extra`: nomes adicionais a liberar (alem de SAFE_ENV_EXTRA). Liberar um extra e uma decisao
    explicita e vale mesmo que o nome pareca segredo. `fonte`: mapeamento de origem (padrao:
    os.environ; existe para testar sem tocar no ambiente real).
    """
    origem = os.environ if fonte is None else fonte
    liberados = {e.strip().upper() for e in (extra or []) if e and e.strip()} | _extras_do_ambiente()

    saida: Dict[str, str] = {}
    for nome, valor in origem.items():
        n = nome.upper()
        if n in liberados:
            saida[nome] = valor
        elif _permitida(nome) and not _parece_segredo(nome):
            saida[nome] = valor
    return saida
