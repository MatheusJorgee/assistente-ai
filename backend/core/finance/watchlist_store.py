"""
Watchlist financeira: os ativos que o Matheus pediu pra ela acompanhar.

SQLite em .runtime/watchlist.db. Guarda o último preço avisado por ativo, pra
o monitor só falar quando o movimento for relevante (threshold de variação).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import sqlite3

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_DB_PATH = Path(__file__).resolve().parents[2] / ".runtime" / "watchlist.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            simbolo TEXT NOT NULL UNIQUE,
            limite_pct REAL DEFAULT 3.0,
            ultimo_preco_avisado REAL,
            criado_em TEXT NOT NULL
        )
        """
    )
    return conn


def adicionar(nome: str, tipo: str, simbolo: str, limite_pct: float = 3.0) -> bool:
    try:
        with _conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO watchlist (nome, tipo, simbolo, limite_pct, criado_em) "
                "VALUES (?, ?, ?, ?, ?)",
                (nome.strip(), tipo, simbolo.upper(), float(limite_pct), datetime.now().isoformat()),
            )
        return True
    except Exception as exc:
        logger.debug(f"[FINANCAS] add falhou: {exc}")
        return False


def remover(nome_ou_simbolo: str) -> bool:
    alvo = nome_ou_simbolo.strip()
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM watchlist WHERE simbolo = ? OR LOWER(nome) = LOWER(?)",
            (alvo.upper(), alvo),
        )
        return cur.rowcount > 0


def listar() -> List[Dict[str, Any]]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, nome, tipo, simbolo, limite_pct, ultimo_preco_avisado FROM watchlist "
            "ORDER BY criado_em"
        ).fetchall()]


def marcar_preco_avisado(simbolo: str, preco: float) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE watchlist SET ultimo_preco_avisado = ? WHERE simbolo = ?",
            (float(preco), simbolo.upper()),
        )
