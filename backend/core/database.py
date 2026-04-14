"""
Database canÃ´nico do Core com SQLite.

MantÃ©m persistÃªncia local do projeto em backend/.runtime para respeitar
o princÃ­pio Zero-Trace Host (nada em pastas globais do Windows hospedeiro).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from core.logger import get_logger
except ImportError:
    from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    id: Optional[int] = None
    session_id: str = ""
    role: str = ""
    content: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Event:
    id: Optional[int] = None
    session_id: str = ""
    event_type: str = ""
    data: Dict[str, Any] | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if self.data is None:
            self.data = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Image:
    id: Optional[int] = None
    session_id: str = ""
    base64_data: str = ""
    width: int = 0
    height: int = 0
    format: str = "png"
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class Database:
    """ServiÃ§o canÃ´nico de banco SQLite do Core."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            backend_root = Path(__file__).resolve().parent.parent
            runtime_dir = backend_root / ".runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(runtime_dir / "quinta_feira.db")

        self.db_path = db_path
        self._lock = threading.RLock()
        self._memory = {
            "messages": [],
            "events": [],
            "images": [],
        }
        self._init_db()
        logger.info(f"[DATABASE] Inicializado: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    base64_data TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    format TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        return await asyncio.to_thread(self._execute_sync, query, params)

    def _execute_sync(self, query: str, params: tuple[Any, ...]) -> int:
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(query, params)
            lastrowid = cur.lastrowid
            conn.commit()
            conn.close()
            return int(lastrowid or 0)

    async def query_all(self, query: str, params: tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._query_all_sync, query, params)

    def _query_all_sync(self, query: str, params: tuple[Any, ...]) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(query, params)
            rows = [dict(row) for row in cur.fetchall()]
            conn.close()
            return rows

    async def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        msg = Message(session_id=session_id, role=role, content=content, metadata=metadata or {})
        with self._lock:
            self._memory["messages"].append(msg)
        await self.execute(
            """
            INSERT INTO messages (session_id, role, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (msg.session_id, msg.role, msg.content, msg.timestamp, json.dumps(msg.metadata)),
        )
        return msg

    async def get_messages(self, session_id: str, limit: int = 50) -> List[Message]:
        with self._lock:
            msgs = [m for m in self._memory["messages"] if m.session_id == session_id]
        return msgs[-limit:]

    async def add_event(self, session_id: str, event_type: str, data: Optional[Dict[str, Any]] = None) -> Event:
        evt = Event(session_id=session_id, event_type=event_type, data=data or {})
        with self._lock:
            self._memory["events"].append(evt)
        await self.execute(
            """
            INSERT INTO events (session_id, event_type, data, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (evt.session_id, evt.event_type, json.dumps(evt.data), evt.timestamp),
        )
        return evt

    async def add_image(self, session_id: str, base64_data: str, width: int, height: int, format: str = "png") -> Image:
        img = Image(session_id=session_id, base64_data=base64_data, width=width, height=height, format=format)
        with self._lock:
            self._memory["images"].append(img)
        await self.execute(
            """
            INSERT INTO images (session_id, base64_data, width, height, format, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (img.session_id, img.base64_data, img.width, img.height, img.format, img.timestamp),
        )
        return img

    async def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "messages_count": len(self._memory["messages"]),
                "events_count": len(self._memory["events"]),
                "images_count": len(self._memory["images"]),
                "db_file": self.db_path,
            }


_db_instance: Optional[Database] = None


async def get_database(db_path: Optional[str] = None) -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance

