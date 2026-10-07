"""
MacrosStore — "modos"/cenas da Quinta-Feira.

Cada macro é um nome + uma sequência de passos. Cada passo é uma chamada de
ferramenta: {"ferramenta": "abrir_programa", "args": {"nome": "Premiere"}}.
Ex.: macro "edição" = abrir Premiere + (futuro) fechar Discord + modo foco.

JSON em .runtime/macros.json. Busca por nome case-insensitive/parcial.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_FILE = Path(__file__).resolve().parents[2] / ".runtime" / "macros.json"


def _load() -> Dict[str, Any]:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: Dict[str, Any]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def salvar(nome: str, passos: List[Dict[str, Any]], descricao: str = "") -> bool:
    nome = (nome or "").strip()
    if not nome or not passos:
        return False
    data = _load()
    data[nome.lower()] = {"nome": nome, "passos": passos, "descricao": descricao}
    _save(data)
    return True


def buscar(nome: str) -> Optional[Dict[str, Any]]:
    alvo = (nome or "").strip().lower()
    if not alvo:
        return None
    data = _load()
    if alvo in data:
        return data[alvo]
    for k, v in data.items():  # parcial
        if alvo in k or k in alvo:
            return v
    return None


def listar() -> List[Dict[str, Any]]:
    return [
        {"nome": v["nome"], "descricao": v.get("descricao", ""), "passos": len(v.get("passos", []))}
        for v in _load().values()
    ]


def remover(nome: str) -> bool:
    data = _load()
    alvo = (nome or "").strip().lower()
    if alvo in data:
        del data[alvo]
        _save(data)
        return True
    return False
