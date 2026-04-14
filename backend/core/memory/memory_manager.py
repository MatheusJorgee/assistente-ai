"""
Memory Manager (Long-Term Memory): episÃ³dica + semÃ¢ntica.

PersistÃªncia usa o SQLite canÃ´nico do Core.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from ..logger import get_logger
    from ..database import get_database
except ImportError:
    from ..logger import get_logger
    from ..database import get_database

logger = get_logger(__name__)


class MemoryManager:
    """Gerenciador de memÃ³ria de longo prazo."""

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        db = await get_database()
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS episodic_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT,
                importance REAL DEFAULT 0.5,
                tags TEXT,
                created_at TEXT NOT NULL,
                last_accessed_at TEXT,
                access_count INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.8,
                source TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                access_count INTEGER DEFAULT 0,
                UNIQUE(category, key)
            )
            """
        )
        self._initialized = True
        logger.info("[MEMORY] MemoryManager inicializado")

    async def save_memory(
        self,
        *,
        memory_type: str,
        content: str,
        session_id: str = "",
        event_type: str = "generic",
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        key: Optional[str] = None,
        category: str = "user",
        confidence: float = 0.85,
        source: str = "tool",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.initialize()
        db = await get_database()
        now = datetime.utcnow().isoformat() + "Z"
        normalized = memory_type.strip().lower()

        if normalized == "episodic":
            row_id = await db.execute(
                """
                INSERT INTO episodic_memories
                (session_id, event_type, summary, payload_json, importance, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event_type,
                    content,
                    json.dumps(payload or {}, ensure_ascii=False),
                    float(max(0.0, min(1.0, importance))),
                    json.dumps(tags or [], ensure_ascii=False),
                    now,
                ),
            )
            return {"ok": True, "memory_type": "episodic", "id": row_id}

        if normalized == "semantic":
            semantic_key = (key or content[:120]).strip() or "fact"
            existing = await db.query_all(
                "SELECT id FROM semantic_memories WHERE category = ? AND key = ? LIMIT 1",
                (category, semantic_key),
            )
            if existing:
                await db.execute(
                    """
                    UPDATE semantic_memories
                    SET value = ?, confidence = ?, source = ?, updated_at = ?
                    WHERE category = ? AND key = ?
                    """,
                    (content, float(max(0.0, min(1.0, confidence))), source, now, category, semantic_key),
                )
                return {"ok": True, "memory_type": "semantic", "id": int(existing[0]["id"]), "updated": True}

            row_id = await db.execute(
                """
                INSERT INTO semantic_memories
                (category, key, value, confidence, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (category, semantic_key, content, float(max(0.0, min(1.0, confidence))), source, now, now),
            )
            return {"ok": True, "memory_type": "semantic", "id": row_id, "updated": False}

        return {"ok": False, "error": "memory_type invÃ¡lido. Use 'episodic' ou 'semantic'."}

    async def retrieve_memory(self, *, memory_type: str = "all", limit: int = 10) -> Dict[str, Any]:
        await self.initialize()
        db = await get_database()
        top_n = max(1, min(int(limit), 100))
        mode = memory_type.strip().lower()

        episodic: List[Dict[str, Any]] = []
        semantic: List[Dict[str, Any]] = []

        if mode in {"all", "episodic"}:
            episodic = await db.query_all(
                """
                SELECT id, session_id, event_type, summary, payload_json, importance, tags, created_at
                FROM episodic_memories
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (top_n,),
            )

        if mode in {"all", "semantic"}:
            semantic = await db.query_all(
                """
                SELECT id, category, key, value, confidence, source, updated_at
                FROM semantic_memories
                ORDER BY datetime(updated_at) DESC
                LIMIT ?
                """,
                (top_n,),
            )

        return {"ok": True, "episodic": episodic, "semantic": semantic}

    async def search_memory(self, *, query: str, memory_type: str = "all", limit: int = 10) -> Dict[str, Any]:
        await self.initialize()
        db = await get_database()
        q = f"%{query.strip()}%"
        top_n = max(1, min(int(limit), 100))
        mode = memory_type.strip().lower()

        episodic: List[Dict[str, Any]] = []
        semantic: List[Dict[str, Any]] = []

        if mode in {"all", "episodic"}:
            episodic = await db.query_all(
                """
                SELECT id, session_id, event_type, summary, payload_json, importance, tags, created_at
                FROM episodic_memories
                WHERE summary LIKE ? OR event_type LIKE ? OR tags LIKE ?
                ORDER BY importance DESC, datetime(created_at) DESC
                LIMIT ?
                """,
                (q, q, q, top_n),
            )

        if mode in {"all", "semantic"}:
            semantic = await db.query_all(
                """
                SELECT id, category, key, value, confidence, source, updated_at
                FROM semantic_memories
                WHERE key LIKE ? OR value LIKE ? OR category LIKE ?
                ORDER BY confidence DESC, datetime(updated_at) DESC
                LIMIT ?
                """,
                (q, q, q, top_n),
            )

        return {"ok": True, "episodic": episodic, "semantic": semantic}

