"""
IdeasStore — captura rápida de ideias do Matheus.

Ele joga uma ideia a qualquer hora ("ideia de vídeo sobre X", "lembrar de testar Y")
e ela guarda, com categoria opcional, pra revisitar depois. Inbox de criador:
o que importa é registrar sem fricção.

SQLite em .runtime/ideas.db.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_DB = Path(__file__).resolve().parents[2] / ".runtime" / "ideas.db"


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT NOT NULL,
            categoria TEXT DEFAULT 'geral',
            criado_em TEXT NOT NULL,
            arquivada INTEGER DEFAULT 0
        )
        """
    )
    return c


def anotar(texto: str, categoria: str = "geral") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO ideas (texto, categoria, criado_em) VALUES (?, ?, ?)",
            (texto.strip(), (categoria or "geral").strip().lower(), datetime.now().isoformat()),
        )
        return int(cur.lastrowid)


def listar(categoria: Optional[str] = None, incluir_arquivadas: bool = False) -> List[Dict[str, Any]]:
    q = "SELECT id, texto, categoria, criado_em FROM ideas WHERE 1=1"
    params: list = []
    if not incluir_arquivadas:
        q += " AND arquivada = 0"
    if categoria:
        q += " AND categoria = ?"
        params.append(categoria.strip().lower())
    q += " ORDER BY datetime(criado_em) DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, tuple(params)).fetchall()]


def categorias() -> List[Dict[str, Any]]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT categoria, COUNT(*) n FROM ideas WHERE arquivada=0 GROUP BY categoria ORDER BY n DESC"
        ).fetchall()]


def arquivar(idea_id: int) -> bool:
    with _conn() as c:
        cur = c.execute("UPDATE ideas SET arquivada=1 WHERE id=?", (int(idea_id),))
        return cur.rowcount > 0
