"""
ScheduledStore — ações que RODAM sozinhas no horário (não só lembretes que falam).

Cada tarefa: um comando em linguagem natural ("me dá o resumo do mercado") que,
no horário marcado, passa pelo brain.ask e o resultado é narrado. Diferente do
lembrete (que só avisa), isto EXECUTA.

JSON em .runtime/scheduled.json. Agendamento: hora "HH:MM" + dias da semana
(0=segunda..6=domingo; vazio = todo dia).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_FILE = Path(__file__).resolve().parents[2] / ".runtime" / "scheduled.json"


def _load() -> List[Dict[str, Any]]:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(tarefas: List[Dict[str, Any]]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(tarefas, ensure_ascii=False, indent=1), encoding="utf-8")


def criar(comando: str, hora: str, dias: List[int] | None = None) -> int:
    tarefas = _load()
    novo_id = (max((t["id"] for t in tarefas), default=0) + 1)
    tarefas.append({
        "id": novo_id,
        "comando": comando.strip(),
        "hora": hora.strip(),           # "HH:MM"
        "dias": dias or [],             # [] = todo dia
        "ultima_exec": "",              # "YYYY-MM-DD"
        "criado_em": datetime.now().isoformat(),
    })
    _save(tarefas)
    return novo_id


def listar() -> List[Dict[str, Any]]:
    return _load()


def cancelar(tid: int) -> bool:
    tarefas = _load()
    novas = [t for t in tarefas if t["id"] != int(tid)]
    if len(novas) != len(tarefas):
        _save(novas)
        return True
    return False


def devidas(agora: datetime | None = None) -> List[Dict[str, Any]]:
    """Tarefas que devem rodar AGORA (hora bateu, dia confere, não rodou hoje)."""
    agora = agora or datetime.now()
    hoje = agora.strftime("%Y-%m-%d")
    hhmm = agora.strftime("%H:%M")
    out = []
    for t in _load():
        if t.get("ultima_exec") == hoje:
            continue
        dias = t.get("dias") or []
        if dias and agora.weekday() not in dias:
            continue
        # bate se a hora atual >= hora marcada e ainda não rodou hoje
        # (tolera atraso de ticks; roda no primeiro tick após o horário)
        if hhmm >= t.get("hora", "99:99"):
            out.append(t)
    return out


def marcar_executada(tid: int) -> None:
    tarefas = _load()
    hoje = datetime.now().strftime("%Y-%m-%d")
    for t in tarefas:
        if t["id"] == int(tid):
            t["ultima_exec"] = hoje
    _save(tarefas)
