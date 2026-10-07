"""
PeopleStore — o "CRM pessoal" da Quinta-Feira.

As pessoas da vida do Matheus: quem são, apelidos, relação, o que importa,
quando foi o último contato, aniversário. Alimentado pela conversa (ela registra
quando ele fala de alguém) e pela triagem do WhatsApp (atualiza último contato).
Vira presença de secretária: "faz 2 semanas que você não fala com a Yngrid".

SQLite em .runtime/people.db. Busca por nome OU apelido (case-insensitive).
"""

from __future__ import annotations

import json
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

_DB_PATH = Path(__file__).resolve().parents[2] / ".runtime" / "people.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            apelidos TEXT,            -- JSON list
            relacao TEXT,             -- "namorada", "amigo", "mãe", "colega"...
            fatos TEXT,               -- JSON list de fatos
            aniversario TEXT,         -- "MM-DD"
            ultimo_contato_ts REAL,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )
    return conn


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def buscar(nome_ou_apelido: str) -> Optional[Dict[str, Any]]:
    alvo = _norm(nome_ou_apelido)
    if not alvo:
        return None
    with _conn() as c:
        rows = c.execute("SELECT * FROM people").fetchall()
    for r in rows:
        d = dict(r)
        if _norm(d["nome"]) == alvo:
            return _hydrate(d)
        apel = [_norm(a) for a in json.loads(d.get("apelidos") or "[]")]
        if alvo in apel:
            return _hydrate(d)
    # match parcial (contém)
    for r in rows:
        d = dict(r)
        if alvo in _norm(d["nome"]):
            return _hydrate(d)
    return None


def _hydrate(d: Dict[str, Any]) -> Dict[str, Any]:
    d["apelidos"] = json.loads(d.get("apelidos") or "[]")
    d["fatos"] = json.loads(d.get("fatos") or "[]")
    return d


def salvar(
    nome: str,
    relacao: Optional[str] = None,
    apelidos: Optional[List[str]] = None,
    fatos: Optional[List[str]] = None,
    aniversario: Optional[str] = None,
) -> Dict[str, Any]:
    """Cria ou atualiza (merge) uma pessoa. Fatos e apelidos são acumulados."""
    nome = nome.strip()
    if not nome:
        return {"ok": False, "erro": "nome vazio"}
    agora = datetime.now().isoformat()
    existente = buscar(nome)
    with _conn() as c:
        if existente:
            apel = existente["apelidos"]
            for a in (apelidos or []):
                if _norm(a) not in [_norm(x) for x in apel]:
                    apel.append(a.strip())
            fat = existente["fatos"]
            for f in (fatos or []):
                if f.strip() and f.strip() not in fat:
                    fat.append(f.strip())
            c.execute(
                """UPDATE people SET relacao=COALESCE(?,relacao), apelidos=?, fatos=?,
                   aniversario=COALESCE(?,aniversario), atualizado_em=? WHERE id=?""",
                (relacao, json.dumps(apel, ensure_ascii=False), json.dumps(fat, ensure_ascii=False),
                 aniversario, agora, existente["id"]),
            )
            return {"ok": True, "id": existente["id"], "atualizado": True}
        c.execute(
            """INSERT INTO people (nome, apelidos, relacao, fatos, aniversario, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nome, json.dumps(apelidos or [], ensure_ascii=False), relacao,
             json.dumps(fatos or [], ensure_ascii=False), aniversario, agora, agora),
        )
        return {"ok": True, "criado": True}


def registrar_contato(nome: str, ts: Optional[float] = None) -> None:
    """Marca último contato (chamado pela triagem do WhatsApp)."""
    p = buscar(nome)
    ts = ts or time.time()
    with _conn() as c:
        if p:
            c.execute("UPDATE people SET ultimo_contato_ts=? WHERE id=?", (ts, p["id"]))
        else:
            agora = datetime.now().isoformat()
            c.execute(
                "INSERT OR IGNORE INTO people (nome, ultimo_contato_ts, criado_em, atualizado_em) VALUES (?,?,?,?)",
                (nome.strip(), ts, agora, agora),
            )


def listar() -> List[Dict[str, Any]]:
    with _conn() as c:
        return [_hydrate(dict(r)) for r in c.execute(
            "SELECT * FROM people ORDER BY ultimo_contato_ts DESC NULLS LAST, nome"
        ).fetchall()]


def sem_contato_ha(dias: int) -> List[Dict[str, Any]]:
    """Pessoas com relação definida que ele não fala há mais de `dias`."""
    limite = time.time() - dias * 86400
    out = []
    for p in listar():
        if p.get("relacao") and p.get("ultimo_contato_ts") and p["ultimo_contato_ts"] < limite:
            out.append(p)
    return out
