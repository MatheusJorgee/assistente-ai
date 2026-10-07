"""
Aprovação amarrada ao ALVO (B9).

O cartão mostra "python limpar.py" e o Matheus aprova. Se `limpar.py` for trocado enquanto o cartão
está aberto (ou entre a aprovação e a execução), o que roda já não é o que foi aprovado. Aqui, antes
de pedir a aprovação, tira-se uma impressão digital dos argumentos e dos ARQUIVOS que o comando
referencia (scripts); depois da aprovação confere-se de novo. Mudou -> nega.

Local, sem LLM. Só olha arquivos pequenos e existentes; o resto é ignorado (não é falha).
"""

import hashlib
import json
import os
import shlex
from pathlib import Path
from typing import Any, Dict, Mapping

EXTENSOES_SCRIPT = {".py", ".ps1", ".bat", ".cmd", ".sh", ".js", ".vbs", ".psm1", ".exe", ".jar"}
TAMANHO_MAX = 20 * 1024 * 1024
TOKENS_MAX = 16
CAMPOS_COMANDO = {"executar_terminal": "comando", "v2_os_command": "script"}


def _sha_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def _tokens(texto: str):
    try:
        return shlex.split(texto, posix=False)[:TOKENS_MAX]
    except ValueError:
        return texto.split()[:TOKENS_MAX]


def arquivos_referenciados(comando: str, cwd: str = "") -> Dict[str, str]:
    """{caminho absoluto: sha256} dos scripts existentes citados no comando."""
    achados: Dict[str, str] = {}
    base = Path(cwd) if cwd else Path.cwd()
    for tok in _tokens(comando or ""):
        tok = tok.strip("\"'")
        if not tok or Path(tok).suffix.lower() not in EXTENSOES_SCRIPT:
            continue
        p = Path(os.path.expandvars(tok)).expanduser()
        if not p.is_absolute():
            p = base / p
        try:
            if p.is_file() and p.stat().st_size <= TAMANHO_MAX:
                achados[str(p.resolve())] = _sha_arquivo(p)
        except OSError:
            continue
    return achados


def impressao(ferramenta: str, argumentos: Mapping[str, Any]) -> Dict[str, Any]:
    """Impressão digital do que vai ser feito: hash dos argumentos + scripts referenciados."""
    args = dict(argumentos or {})
    bruto = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    out: Dict[str, Any] = {"args": hashlib.sha256(bruto.encode("utf-8")).hexdigest()}
    campo = CAMPOS_COMANDO.get(ferramenta)
    if campo:
        out["arquivos"] = arquivos_referenciados(str(args.get(campo) or ""), str(args.get("cwd") or ""))
    return out


def mudou(antes: Dict[str, Any], depois: Dict[str, Any]) -> str:
    """'' se igual; senão, o motivo (para o Matheus e para o log)."""
    if antes.get("args") != depois.get("args"):
        return "os argumentos mudaram depois da aprovação"
    a, d = antes.get("arquivos") or {}, depois.get("arquivos") or {}
    for caminho in sorted(set(a) | set(d)):
        if a.get(caminho) != d.get(caminho):
            return f"o arquivo {Path(caminho).name} mudou depois da aprovação"
    return ""
