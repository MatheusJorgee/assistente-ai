"""
Chaves de API no Gerenciador de Credenciais do Windows (em vez de texto puro no `.env`).

Por quê: o `.env` é um arquivo comum; qualquer programa (ou backup, ou upload sem querer) que o leia leva
todas as chaves. O Gerenciador de Credenciais guarda por usuário do Windows, cifrado com a sua conta.

Sem dependência nova: usa a API do Windows (advapi32) via ctypes. Fora do Windows, tudo é no-op e o
`.env` continua valendo.

Uso:
    python -m core.host.segredos status              # quais chaves estão no cofre e quais só no .env
    python -m core.host.segredos migrar              # copia do .env para o cofre (não mexe no .env)
    python -m core.host.segredos migrar --limpar-env # ...e esvazia os valores migrados no .env (depois de conferir)
    python -m core.host.segredos apagar NOME

No boot, `carregar_no_ambiente()` completa as variáveis que estiverem vazias com o valor do cofre; o resto
do código continua lendo `os.getenv(...)` como sempre. Os subprocessos continuam sem enxergar essas chaves
(core/host/safe_env.py).
"""

import ctypes
import os
import re
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Dict, List, MutableMapping, Optional

NOMES = (
    "GEMINI_API_KEY", "TAVILY_API_KEY", "ELEVENLABS_API_KEY", "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN", "OPENWEATHER_API_KEY", "YOUTUBE_API_KEY", "NGROK_AUTH_TOKEN",
)
PREFIXO_ALVO = "QuintaFeira/"          # sobrescrito nos testes
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
_WINDOWS = sys.platform == "win32"


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR), ("LastWritten", _FILETIME), ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD), ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
    ]


def _api():
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    adv.CredWriteW.restype = wintypes.BOOL
    adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredDeleteW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [wintypes.LPVOID]
    return adv


def disponivel() -> bool:
    return _WINDOWS


def salvar(nome: str, valor: str) -> bool:
    if not _WINDOWS or not nome or not valor:
        return False
    dados = valor.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(dados)).from_buffer_copy(dados)
    cred = _CREDENTIALW()
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = PREFIXO_ALVO + nome
    cred.CredentialBlobSize = len(dados)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = "quinta-feira"
    return bool(_api().CredWriteW(ctypes.byref(cred), 0))


def ler(nome: str) -> Optional[str]:
    if not _WINDOWS:
        return None
    adv = _api()
    ponteiro = ctypes.POINTER(_CREDENTIALW)()
    if not adv.CredReadW(PREFIXO_ALVO + nome, CRED_TYPE_GENERIC, 0, ctypes.byref(ponteiro)):
        return None
    try:
        c = ponteiro.contents
        bruto = bytes(bytearray(c.CredentialBlob[i] for i in range(c.CredentialBlobSize)))
        return bruto.decode("utf-16-le")
    finally:
        adv.CredFree(ponteiro)


def apagar(nome: str) -> bool:
    return bool(_WINDOWS and _api().CredDeleteW(PREFIXO_ALVO + nome, CRED_TYPE_GENERIC, 0))


def carregar_no_ambiente(env: Optional[MutableMapping[str, str]] = None, nomes: Optional[List[str]] = None) -> List[str]:
    """Completa as variáveis VAZIAS/ausentes com o valor do cofre. Devolve os nomes preenchidos."""
    alvo = os.environ if env is None else env
    preenchidos: List[str] = []
    for nome in (nomes or NOMES):
        if (alvo.get(nome) or "").strip():
            continue
        try:
            valor = ler(nome)
        except Exception:
            valor = None
        if valor:
            alvo[nome] = valor
            preenchidos.append(nome)
    return preenchidos


# ------------------------------------------------------------------ migração (você roda)

_LINHA = re.compile(r"^(?P<nome>[A-Z][A-Z0-9_]*)\s*=\s*(?P<valor>.*?)\s*$")


def _valores_do_env(arquivo: Path) -> Dict[str, str]:
    achados: Dict[str, str] = {}
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if linha.lstrip().startswith("#"):
            continue
        m = _LINHA.match(linha)
        if m and m["nome"] in NOMES:
            valor = m["valor"].strip().strip('"').strip("'")
            if valor:
                achados[m["nome"]] = valor
    return achados


def migrar(arquivo_env: Path, limpar_env: bool = False) -> Dict[str, str]:
    """Copia as chaves do `.env` para o cofre. Só depois de LER DE VOLTA e conferir, e só se
    `limpar_env`, esvazia os valores no `.env`. Devolve {nome: 'ok'|'falhou'} (nunca o valor)."""
    resultado: Dict[str, str] = {}
    valores = _valores_do_env(arquivo_env)
    for nome, valor in valores.items():
        resultado[nome] = "ok" if salvar(nome, valor) and ler(nome) == valor else "falhou"
    if limpar_env and valores and all(v == "ok" for v in resultado.values()):
        novas = []
        for linha in arquivo_env.read_text(encoding="utf-8").splitlines():
            m = _LINHA.match(linha) if not linha.lstrip().startswith("#") else None
            novas.append(f"{m['nome']}=" if m and m["nome"] in valores else linha)
        arquivo_env.write_text("\n".join(novas) + "\n", encoding="utf-8")
    return resultado


def status(arquivo_env: Optional[Path]) -> Dict[str, str]:
    """Para cada nome: 'no cofre', 'só no .env' ou 'ausente'. Sem revelar valores."""
    no_env = _valores_do_env(arquivo_env) if arquivo_env and arquivo_env.exists() else {}
    saida = {}
    for nome in NOMES:
        saida[nome] = "no cofre" if ler(nome) else ("só no .env" if nome in no_env else "ausente")
    return saida


def _cli(argv: List[str]) -> int:
    env = Path(__file__).resolve().parents[2] / ".env"
    if not disponivel():
        print("Gerenciador de Credenciais só existe no Windows; o .env continua valendo.")
        return 1
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        for nome, est in status(env).items():
            print(f"  {nome:<22} {est}")
        return 0
    if cmd == "migrar":
        if not env.exists():
            print("Não achei o .env.")
            return 1
        res = migrar(env, limpar_env="--limpar-env" in argv)
        for nome, r in res.items():
            print(f"  {nome:<22} {r}")
        print("Nada a migrar." if not res else ("Concluído. " + ("Valores do .env esvaziados." if "--limpar-env" in argv else "O .env não foi alterado (use --limpar-env para esvaziá-lo).")))
        return 0 if all(v == "ok" for v in res.values()) else 2
    if cmd == "apagar" and len(argv) > 1:
        print("apagado" if apagar(argv[1]) else "não estava no cofre")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
