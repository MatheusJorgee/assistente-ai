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
    from .logger import get_logger
except ImportError:
    from .logger import get_logger

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
    
    # ===== RAG SIMPLES: Recuperação baseada em Palavras-Chave =====
    async def search_messages_by_keywords(
        self, 
        session_id: str, 
        keywords: List[str], 
        limit: int = 10
    ) -> List[Message]:
        """
        Busca mensagens relevantes usando keywords (RAG simples).
        
        Economia de tokens (RAG vs injeção total):
        - Antes (injetar tudo): 10k tokens de memória
        - Depois (RAG keywords): 2-3k tokens (relevantes)
        - Economia: 70-80%
        
        Args:
            session_id: ID da sessão
            keywords: Lista de palavras-chave para buscar
            limit: Máximo de mensagens relevantes a retornar
        
        Returns:
            Lista de mensagens ordenadas por relevância
        """
        if not keywords:
            # Se sem keywords, retorna apenas últimas N
            return await self.get_messages(session_id, limit=limit)
        
        with self._lock:
            all_messages = [m for m in self._memory["messages"] if m.session_id == session_id]
        
        # Scoring: quantas keywords cada mensagem contém
        scored_messages = []
        for msg in all_messages:
            # Buscar no content
            content_lower = (msg.content or "").lower()
            
            # Contar matches
            match_count = sum(1 for kw in keywords if kw.lower() in content_lower)
            
            if match_count > 0:
                scored_messages.append((msg, match_count))
        
        # Ordenar por score (descendente) e retornar top N
        scored_messages.sort(key=lambda x: x[1], reverse=True)
        return [msg for msg, score in scored_messages[:limit]]
    
    async def get_recent_messages_window(
        self, 
        session_id: str, 
        window_size: int = 20
    ) -> List[Message]:
        """
        LastN messages (sliding window para context management).
        
        Economia:
        - Histórico completo: 50 msgs × 500 chars = 25k chars ≈ 10k tokens
        - Sliding window 20: 20 msgs × 500 chars = 10k chars ≈ 4k tokens
        - Economia: 60%
        
        Args:
            session_id: ID da sessão
            window_size: Quantidade de mensagens recentes
        
        Returns:
            Últimas N mensagens ordenadas temporalmente
        """
        messages = await self.get_messages(session_id, limit=window_size)
        # Ordenar por timestamp (ascendente) para conversa natural
        return sorted(messages, key=lambda x: x.timestamp)
    
    async def summarize_session(
        self, 
        session_id: str, 
        include_assistant_only: bool = False
    ) -> str:
        """
        Resumo de uma sessão (para memória de longo termo).
        
        Uso: Quando janela ativa está cheia, mover contexto antigo para resumo.
        
        Args:
            session_id: ID da sessão
            include_assistant_only: Se True, apenas respostas do assistant
        
        Returns:
            Resumo textual da conversa
        """
        with self._lock:
            messages = [
                m for m in self._memory["messages"] 
                if m.session_id == session_id
            ]
        
        if not messages:
            return "[Sem histórico de conversa]"
        
        # Filtrar se necessário
        if include_assistant_only:
            messages = [m for m in messages if m.role == "assistant"]
        
        # Montar resumo simples
        summary_lines = []
        for msg in messages:
            role = msg.role.upper()
            preview = (msg.content or "")[:100]  # Primeiros 100 chars
            summary_lines.append(f"[{role}] {preview}")
        
        return "\n".join(summary_lines[:20])  # Limitar a 20 linhas


_db_instance: Optional[Database] = None


async def get_database(db_path: Optional[str] = None) -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance

