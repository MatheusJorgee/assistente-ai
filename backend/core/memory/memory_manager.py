"""
Memory Manager (Long-Term Memory): episÃ³dica + semÃ¢ntica.

PersistÃªncia usa o SQLite canÃ´nico do Core.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

VAULT_BASE_PATH = "./.vault"

ENTIDADES_MAP = {
    r"\b(paulo)\b": "pessoas/paulo.md",
    r"\b(matheus|filhote)\b": "pessoas/matheus_filhote.md",
    r"\b(comida|pizza|comer|fome|alergia)\b": "preferencias/comida.md",
    r"\b(jogo|jogar|dbd|game)\b": "preferencias/jogos.md",
    r"\b(trabalho|chefe|empresa)\b": "rotina/trabalho.md"
}

def recuperar_memoria_nuclear(mensagem_usuario: str) -> str:
    contexto_injetado = []

    # 1. Ler todos os arquivos gravados pelo memorizar_informacao (.vault/Memorias/)
    memorias_path = os.path.join(VAULT_BASE_PATH, "Memorias")
    if os.path.isdir(memorias_path):
        for nome_arquivo in sorted(os.listdir(memorias_path)):
            if not nome_arquivo.endswith(".md"):
                continue
            caminho_completo = os.path.join(memorias_path, nome_arquivo)
            try:
                with open(caminho_completo, "r", encoding="utf-8") as f:
                    conteudo = f.read().strip()
                    if conteudo:
                        nome_entidade = nome_arquivo.replace(".md", "").upper()
                        contexto_injetado.append(f"--- Fatos sobre {nome_entidade} ---\n{conteudo}")
            except (OSError, UnicodeDecodeError):
                continue

    # 2. ENTIDADES_MAP: arquivos específicos filtrados por keyword na mensagem
    mensagem_lower = mensagem_usuario.lower()
    arquivos_mapa = set()
    for padrao, caminho_arquivo in ENTIDADES_MAP.items():
        if re.search(padrao, mensagem_lower):
            arquivos_mapa.add(caminho_arquivo)

    for caminho_relativo in arquivos_mapa:
        caminho_completo = os.path.join(VAULT_BASE_PATH, caminho_relativo)
        try:
            with open(caminho_completo, "r", encoding="utf-8") as f:
                nome_entidade = os.path.basename(caminho_relativo).replace(".md", "").upper()
                bloco = f"--- Fatos sobre {nome_entidade} ---\n{f.read().strip()}"
                if bloco not in contexto_injetado:
                    contexto_injetado.append(bloco)
        except FileNotFoundError:
            continue

    if contexto_injetado:
        return "MEMORIA NUCLEAR (Fatos Criticos):\n" + "\n\n".join(contexto_injetado)

    return ""


def recuperar_memoria_diaria() -> str:
    """Recupera o arquivo de contexto volátil do dia atual."""
    import datetime
    hoje = datetime.date.today().isoformat()
    caminho_diario = f"./data/memoria_curto_prazo_{hoje}.txt"

    if os.path.exists(caminho_diario):
        with open(caminho_diario, "r", encoding="utf-8") as f:
            conteudo = f.read().strip()
            if conteudo:
                return f"CONTEXTO EFÊMERO (Acontecimentos de Hoje):\n{conteudo}"
    return ""


def anotar_memoria_diaria(fato: str) -> str:
    """Anexa um fato volátil do dia ao arquivo de memória de curto prazo."""
    import datetime
    hoje = datetime.date.today().isoformat()
    agora = datetime.datetime.now().strftime("%H:%M:%S")
    pasta = "./data"
    os.makedirs(pasta, exist_ok=True)
    caminho_diario = os.path.join(pasta, f"memoria_curto_prazo_{hoje}.txt")

    with open(caminho_diario, "a", encoding="utf-8") as f:
        f.write(f"[{agora}] {fato.strip()}\n")

    return f"Fato volátil anotado em {caminho_diario}"

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

