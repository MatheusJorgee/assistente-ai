"""
Database Service - Persistência de memória com SQLite.

Implementação local para services (usa backend/data/quinta_feira.db).

Estratégia:
- Memória em RAM (rápido, para conversa atual)
- Persistência em SQLite (recuperação após reinício)
- Criar tabelas automaticamente na inicialização se não existirem
- Armazenar: conversas, imagens, comandos executados, eventos
"""

import sqlite3
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
import threading

try:
    from core import get_logger
except ImportError:
    from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """Mensagem armazenada."""
    id: Optional[int] = None
    session_id: str = ""
    role: str = ""  # "user", "assistant", "tool"
    content: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Event:
    """Evento registrado."""
    id: Optional[int] = None
    session_id: str = ""
    event_type: str = ""  # "tool_started", "tool_completed", "vision_captured"
    data: Dict[str, Any] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Image:
    """Imagem capturada."""
    id: Optional[int] = None
    session_id: str = ""
    base64_data: str = ""
    width: int = 0
    height: int = 0
    format: str = "png"  # "png", "webp", "jpg"
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class Database:
    """Serviço de banco de dados com SQLite + memória."""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Inicializa database.
        
        Args:
            db_path: Caminho do arquivo SQLite (default: backend/data/quinta_feira.db)
        """
        if db_path is None:
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "quinta_feira.db")
        
        self.db_path = db_path
        self._lock = threading.RLock()  # Thread-safe
        self._memory = {
            "messages": [],
            "events": [],
            "images": [],
        }
        
        # ✅ CRÍTICO: Criar tabelas na inicialização
        self._init_db()
        logger.info(f"[DATABASE] Inicializado com sucesso: {db_path}")
    
    def _init_db(self) -> None:
        """
        Cria schema de tabelas se não existir.
        
        Garante que as tabelas necessárias existem:
        - messages: para armazenar conversas
        - events: para armazenar histórico de eventos  
        - images: para armazenar capturas de tela
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Tabela de mensagens - com todas as colunas usadas por _save_message_to_db
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        metadata TEXT
                    )
                """)
                
                # Tabela de eventos
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        data TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                
                # Tabela de imagens
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        base64_data TEXT NOT NULL,
                        width INTEGER,
                        height INTEGER,
                        format TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                
                conn.commit()
                logger.debug("[DATABASE] Schema de tabelas inicializado com CREATE TABLE IF NOT EXISTS")
                
            except sqlite3.Error as e:
                logger.error(f"[DATABASE] Erro ao criar tabelas: {e}")
                raise
            finally:
                conn.close()
    
    async def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> Message:
        """
        Adiciona mensagem ao banco e memória.
        
        Args:
            session_id: ID da sessão
            role: "user", "assistant", "tool"
            content: Conteúdo da mensagem
            metadata: Dados adicionais
        
        Returns:
            Message com ID atribuído
        """
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        with self._lock:
            # Salvar em memória
            self._memory["messages"].append(msg)
            
            # Persistir em SQLite
            await asyncio.to_thread(self._save_message_to_db, msg)
        
        logger.debug(f"[DATABASE] Mensagem adicionada: {role} ({len(content)} chars)")
        return msg
    
    def _save_message_to_db(self, msg: Message) -> None:
        """
        Salva mensagem em SQLite.
        
        Insere nas colunas: session_id, role, content, timestamp, metadata
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO messages (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                msg.session_id,
                msg.role,
                msg.content,
                msg.timestamp,
                json.dumps(msg.metadata)
            ))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[DATABASE] Erro ao salvar mensagem: {e}")
            raise
        finally:
            conn.close()
    
    async def get_messages(self, session_id: str, limit: int = 50) -> List[Message]:
        """
        Retorna mensagens de uma sessão (do mais recente).
        
        Args:
            session_id: ID da sessão
            limit: Número máximo de mensagens
        
        Returns:
            Lista de mensagens
        """
        with self._lock:
            # Retornar de memória (mais rápido)
            messages = [
                m for m in self._memory["messages"]
                if m.session_id == session_id
            ]
            return messages[-limit:]
    
    async def add_event(self, session_id: str, event_type: str, data: Optional[Dict] = None) -> Event:
        """Adiciona evento."""
        event = Event(
            session_id=session_id,
            event_type=event_type,
            data=data or {}
        )
        
        with self._lock:
            self._memory["events"].append(event)
            await asyncio.to_thread(self._save_event_to_db, event)
        
        logger.debug(f"[DATABASE] Evento: {event_type}")
        return event
    
    def _save_event_to_db(self, event: Event) -> None:
        """Salva evento em SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO events (session_id, event_type, data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                event.session_id,
                event.event_type,
                json.dumps(event.data),
                event.timestamp
            ))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[DATABASE] Erro ao salvar evento: {e}")
            raise
        finally:
            conn.close()
    
    async def add_image(self, session_id: str, base64_data: str, width: int, height: int, format: str = "png") -> Image:
        """Adiciona imagem capturada."""
        img = Image(
            session_id=session_id,
            base64_data=base64_data,
            width=width,
            height=height,
            format=format
        )
        
        with self._lock:
            self._memory["images"].append(img)
            await asyncio.to_thread(self._save_image_to_db, img)
        
        logger.debug(f"[DATABASE] Imagem: {width}x{height}")
        return img
    
    def _save_image_to_db(self, img: Image) -> None:
        """Salva imagem em SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO images (session_id, base64_data, width, height, format, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                img.session_id,
                img.base64_data,
                img.width,
                img.height,
                img.format,
                img.timestamp
            ))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[DATABASE] Erro ao salvar imagem: {e}")
            raise
        finally:
            conn.close()
    
    async def get_images(self, session_id: str, limit: int = 10) -> List[Image]:
        """Retorna imagens de uma sessão."""
        with self._lock:
            images = [
                i for i in self._memory["images"]
                if i.session_id == session_id
            ]
            return images[-limit:]
    
    async def clear_session(self, session_id: str) -> None:
        """Limpa dados de uma sessão."""
        with self._lock:
            self._memory["messages"] = [
                m for m in self._memory["messages"]
                if m.session_id != session_id
            ]
            self._memory["events"] = [
                e for e in self._memory["events"]
                if e.session_id != session_id
            ]
            self._memory["images"] = [
                i for i in self._memory["images"]
                if i.session_id != session_id
            ]
            
            # Limpar em SQLite
            await asyncio.to_thread(self._clear_session_from_db, session_id)
        
        logger.info(f"[DATABASE] Sessão limpa: {session_id}")
    
    def _clear_session_from_db(self, session_id: str) -> None:
        """Limpa sessão em SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM images WHERE session_id = ?", (session_id,))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[DATABASE] Erro ao limpar sessão: {e}")
            raise
        finally:
            conn.close()
    
    async def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do banco."""
        with self._lock:
            return {
                "messages_count": len(self._memory["messages"]),
                "events_count": len(self._memory["events"]),
                "images_count": len(self._memory["images"]),
                "db_file": self.db_path
            }


# Singleton global
_db_instance = None

async def get_database(db_path: Optional[str] = None) -> Database:
    """Factory para obter instância de database (singleton)."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance

