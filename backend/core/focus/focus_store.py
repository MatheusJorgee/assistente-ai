"""
FocusStore — sessões de foco (pomodoro) que a Quinta-Feira conduz.

Ela inicia um ciclo (foco 25min / pausa 5min, configurável), protege o Matheus
de distração (o monitor segura avisos durante o foco) e avisa a virada de cada
fase. Estado em .runtime/focus_session.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_FILE = Path(__file__).resolve().parents[2] / ".runtime" / "focus_session.json"


def _load() -> Dict[str, Any]:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"ativo": False}


def _save(d: Dict[str, Any]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def iniciar(foco_min: int = 25, pausa_min: int = 5, ciclos: int = 4) -> Dict[str, Any]:
    estado = {
        "ativo": True,
        "fase": "foco",
        "foco_min": max(1, foco_min),
        "pausa_min": max(1, pausa_min),
        "ciclos_alvo": max(1, ciclos),
        "ciclos_feitos": 0,
        "proxima_ts": time.time() + max(1, foco_min) * 60,
        "iniciado_ts": time.time(),
    }
    _save(estado)
    return estado


def parar() -> bool:
    d = _load()
    if d.get("ativo"):
        _save({"ativo": False})
        return True
    return False


def status() -> Dict[str, Any]:
    d = _load()
    if d.get("ativo") and d.get("proxima_ts"):
        d["restante_min"] = max(0, round((d["proxima_ts"] - time.time()) / 60, 1))
    return d


def em_foco_ativo() -> bool:
    """True se há sessão ativa na fase de FOCO (pra suprimir distrações)."""
    d = _load()
    return bool(d.get("ativo") and d.get("fase") == "foco")


def transicao_devida() -> Optional[Dict[str, Any]]:
    """
    Se a fase atual venceu, AVANÇA (foco→pausa→foco...) e retorna o que anunciar:
    {evento: 'fim_foco'|'fim_pausa'|'fim_sessao', ...}. Senão, None.
    """
    d = _load()
    if not d.get("ativo") or not d.get("proxima_ts"):
        return None
    if time.time() < d["proxima_ts"]:
        return None

    if d["fase"] == "foco":
        d["ciclos_feitos"] = int(d.get("ciclos_feitos", 0)) + 1
        if d["ciclos_feitos"] >= d.get("ciclos_alvo", 4):
            _save({"ativo": False})
            return {"evento": "fim_sessao", "ciclos": d["ciclos_feitos"]}
        d["fase"] = "pausa"
        d["proxima_ts"] = time.time() + d.get("pausa_min", 5) * 60
        _save(d)
        return {"evento": "fim_foco", "pausa_min": d.get("pausa_min", 5), "ciclos": d["ciclos_feitos"]}
    else:  # pausa → foco
        d["fase"] = "foco"
        d["proxima_ts"] = time.time() + d.get("foco_min", 25) * 60
        _save(d)
        return {"evento": "fim_pausa", "foco_min": d.get("foco_min", 25)}
