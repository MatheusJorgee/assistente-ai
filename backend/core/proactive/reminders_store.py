"""
ReminderStore — lembretes e datas que a Quinta-Feira gerencia sozinha.

Dois tipos:
  - PONTUAL: "me lembra amanhã às 15h de renovar o boleto" (due_ts).
  - ANUAL:   aniversários e datas fixas ("09-09 aniversário da Yngrid") —
             ela avisa todo ano, no dia.

Storage próprio (backend/.runtime/reminders.db, SQLite síncrono — os callers
usam asyncio.to_thread). A ENTREGA é do ProactiveMonitor: lembrete vencido
vira aviso falado no tom dela.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_DB_PATH = Path(__file__).resolve().parents[2] / ".runtime" / "reminders.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT NOT NULL,
            due_ts REAL,
            anual_mmdd TEXT,
            origem TEXT DEFAULT 'chat',
            criado_em TEXT NOT NULL,
            entregue INTEGER DEFAULT 0,
            ultimo_ano_entregue INTEGER
        )
        """
    )
    return conn


def criar(
    texto: str,
    due_ts: Optional[float] = None,
    anual_mmdd: Optional[str] = None,
    origem: str = "chat",
) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO reminders (texto, due_ts, anual_mmdd, origem, criado_em) "
            "VALUES (?, ?, ?, ?, ?)",
            (texto.strip(), due_ts, anual_mmdd, origem, datetime.now().isoformat()),
        )
        return int(cur.lastrowid)


def listar_pendentes(limite: int = 30) -> List[Dict[str, Any]]:
    agora = time.time()
    with _conn() as c:
        rows = c.execute(
            """
            SELECT id, texto, due_ts, anual_mmdd, origem, criado_em FROM reminders
            WHERE (anual_mmdd IS NOT NULL)
               OR (entregue = 0 AND due_ts IS NOT NULL AND due_ts >= ?)
            ORDER BY COALESCE(due_ts, 9e12) ASC LIMIT ?
            """,
            (agora - 60, limite),
        ).fetchall()
    return [dict(r) for r in rows]


def cancelar(reminder_id: int) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM reminders WHERE id = ?", (int(reminder_id),))
        return cur.rowcount > 0


def vencidos(agora_ts: Optional[float] = None) -> List[Dict[str, Any]]:
    """Lembretes pontuais que venceram e ainda não foram entregues."""
    agora_ts = agora_ts or time.time()
    with _conn() as c:
        rows = c.execute(
            "SELECT id, texto, due_ts, origem FROM reminders "
            "WHERE entregue = 0 AND due_ts IS NOT NULL AND due_ts <= ?",
            (agora_ts,),
        ).fetchall()
    return [dict(r) for r in rows]


def marcar_entregue(reminder_id: int) -> None:
    with _conn() as c:
        c.execute("UPDATE reminders SET entregue = 1 WHERE id = ?", (int(reminder_id),))


def aniversarios_de_hoje() -> List[Dict[str, Any]]:
    """Datas anuais de hoje que ainda não foram avisadas ESTE ano."""
    hoje = datetime.now()
    mmdd = hoje.strftime("%m-%d")
    with _conn() as c:
        rows = c.execute(
            "SELECT id, texto, anual_mmdd FROM reminders "
            "WHERE anual_mmdd = ? AND (ultimo_ano_entregue IS NULL OR ultimo_ano_entregue < ?)",
            (mmdd, hoje.year),
        ).fetchall()
        out = [dict(r) for r in rows]
        if out:
            c.execute(
                f"UPDATE reminders SET ultimo_ano_entregue = ? "
                f"WHERE id IN ({','.join('?' * len(out))})",
                (hoje.year, *[r["id"] for r in out]),
            )
    return out
