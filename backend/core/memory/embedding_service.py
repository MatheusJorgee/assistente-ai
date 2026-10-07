"""
EmbeddingService — memória que entende SIGNIFICADO, não só palavras.

Cada memória (semântica ou episódica relevante) ganha um vetor de embedding
(Gemini gemini-embedding-001, 768 dims). Na hora de lembrar, a pergunta vira
vetor também e a busca é por similaridade de cosseno — "o que eu gosto de
ouvir?" acha "ele ouve PiuTrap no Brave" mesmo sem nenhuma palavra em comum.

Design:
  - Tabela própria (memory_vectors) no SQLite canônico — nada muda nas
    tabelas existentes.
  - Gravação best-effort: se a API de embedding falhar, a memória é salva
    normal e o vetor fica pra próxima rodada de backfill.
  - Backfill no startup cobre memórias antigas (e as que falharam).
  - Tipos ruidosos (habit_sample, music_sample) ficam FORA do índice.
"""

from __future__ import annotations

import asyncio
import time
from array import array
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..logger import get_logger
    from ..database import get_database
except ImportError:
    from ..logger import get_logger
    from ..database import get_database

logger = get_logger(__name__)

_MODEL = "gemini-embedding-001"
_DIM = 768

# Episódicos que não valem indexação (telemetria, não conhecimento)
_EVENT_TYPES_IGNORADOS = {"habit_sample", "music_sample"}


def _to_blob(vec: List[float]) -> bytes:
    return array("f", vec).tobytes()


def _from_blob(blob: bytes) -> array:
    a = array("f")
    a.frombytes(blob)
    return a


def _cosine(a: array, b: array) -> float:
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


class EmbeddingService:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None
        self._initialized = False
        # cache de embeddings de QUERY (mensagens repetidas no chat são comuns)
        self._query_cache: Dict[str, Tuple[float, List[float]]] = {}

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def initialize(self) -> None:
        if self._initialized:
            return
        db = await get_database()
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type TEXT NOT NULL,
                memory_id INTEGER NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(memory_type, memory_id)
            )
            """
        )
        self._initialized = True

    # ── embedding bruto ──────────────────────────────────────────────────────
    async def _embed(self, texts: List[str], task_type: str) -> List[List[float]]:
        from google.genai import types as gtypes

        client = self._get_client()
        resp = await client.aio.models.embed_content(
            model=_MODEL,
            contents=texts,
            config=gtypes.EmbedContentConfig(
                task_type=task_type, output_dimensionality=_DIM
            ),
        )
        return [list(e.values) for e in resp.embeddings]

    async def embed_query(self, text: str, timeout: float = 3.0) -> Optional[List[float]]:
        """Embedding de pergunta, com cache (10 min) e timeout curto."""
        text = (text or "").strip()
        if not text:
            return None
        agora = time.time()
        hit = self._query_cache.get(text)
        if hit and agora - hit[0] < 600:
            return hit[1]
        try:
            vecs = await asyncio.wait_for(
                self._embed([text[:1500]], "RETRIEVAL_QUERY"), timeout=timeout
            )
            self._query_cache[text] = (agora, vecs[0])
            if len(self._query_cache) > 64:
                mais_velho = min(self._query_cache, key=lambda k: self._query_cache[k][0])
                del self._query_cache[mais_velho]
            return vecs[0]
        except Exception as exc:
            logger.debug(f"[EMBED] query falhou: {exc}")
            return None

    # ── indexação ────────────────────────────────────────────────────────────
    async def index_memory(self, memory_type: str, memory_id: int, text: str) -> bool:
        """Indexa (ou reindexa) uma memória. Best-effort: False se falhar."""
        text = (text or "").strip()
        if not text or memory_id is None:
            return False
        try:
            await self.initialize()
            vecs = await self._embed([text[:1500]], "RETRIEVAL_DOCUMENT")
            db = await get_database()
            from datetime import datetime

            now = datetime.utcnow().isoformat() + "Z"
            await db.execute(
                """
                INSERT INTO memory_vectors (memory_type, memory_id, dim, vector, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(memory_type, memory_id)
                DO UPDATE SET vector = excluded.vector, dim = excluded.dim,
                              updated_at = excluded.updated_at
                """,
                (memory_type, int(memory_id), _DIM, _to_blob(vecs[0]), now),
            )
            return True
        except Exception as exc:
            logger.debug(f"[EMBED] indexação falhou ({memory_type}#{memory_id}): {exc}")
            return False

    def index_memory_background(self, memory_type: str, memory_id: int, text: str) -> None:
        """Dispara a indexação sem bloquear quem salvou a memória."""
        try:
            asyncio.get_running_loop().create_task(
                self.index_memory(memory_type, memory_id, text)
            )
        except RuntimeError:
            pass  # sem loop (contexto sync) — backfill cobre depois

    # ── busca semântica ──────────────────────────────────────────────────────
    async def search(
        self, query: str, top_k: int = 8, min_score: float = 0.45
    ) -> List[Dict[str, Any]]:
        """
        Busca por similaridade. Retorna [{memory_type, memory_id, score, texto,
        category}] já com o conteúdo da memória resolvido.
        """
        qvec_list = await self.embed_query(query)
        if not qvec_list:
            return []
        qvec = array("f", qvec_list)

        await self.initialize()
        db = await get_database()
        rows = await db.query_all(
            "SELECT memory_type, memory_id, vector FROM memory_vectors", ()
        )
        pontuados: List[Tuple[float, str, int]] = []
        for r in rows:
            try:
                score = _cosine(qvec, _from_blob(r["vector"]))
                if score >= min_score:
                    pontuados.append((score, r["memory_type"], int(r["memory_id"])))
            except Exception:
                continue
        pontuados.sort(reverse=True)
        top = pontuados[:top_k]
        if not top:
            return []

        out: List[Dict[str, Any]] = []
        sem_ids = [mid for _, mt, mid in top if mt == "semantic"]
        epi_ids = [mid for _, mt, mid in top if mt == "episodic"]
        sem_map: Dict[int, Dict[str, Any]] = {}
        epi_map: Dict[int, Dict[str, Any]] = {}
        if sem_ids:
            marks = ",".join("?" * len(sem_ids))
            for r in await db.query_all(
                f"SELECT id, category, value FROM semantic_memories WHERE id IN ({marks})",
                tuple(sem_ids),
            ):
                sem_map[int(r["id"])] = r
        if epi_ids:
            marks = ",".join("?" * len(epi_ids))
            for r in await db.query_all(
                f"SELECT id, event_type, summary FROM episodic_memories WHERE id IN ({marks})",
                tuple(epi_ids),
            ):
                epi_map[int(r["id"])] = r

        for score, mt, mid in top:
            if mt == "semantic" and mid in sem_map:
                r = sem_map[mid]
                out.append(
                    {
                        "memory_type": mt, "memory_id": mid, "score": round(score, 3),
                        "category": r.get("category", ""), "texto": r.get("value", ""),
                    }
                )
            elif mt == "episodic" and mid in epi_map:
                r = epi_map[mid]
                out.append(
                    {
                        "memory_type": mt, "memory_id": mid, "score": round(score, 3),
                        "category": r.get("event_type", ""), "texto": r.get("summary", ""),
                    }
                )
        return out

    # ── backfill ─────────────────────────────────────────────────────────────
    async def backfill(self, batch: int = 16, max_total: int = 200) -> int:
        """Indexa memórias que ainda não têm vetor (antigas ou falhas). Lento e
        educado de propósito (pausa entre lotes) pra não brigar com o chat."""
        try:
            await self.initialize()
            db = await get_database()

            pendentes: List[Tuple[str, int, str]] = []
            for r in await db.query_all(
                """
                SELECT s.id, s.category, s.value FROM semantic_memories s
                LEFT JOIN memory_vectors v
                    ON v.memory_type = 'semantic' AND v.memory_id = s.id
                WHERE v.id IS NULL LIMIT ?
                """,
                (max_total,),
            ):
                pendentes.append(("semantic", int(r["id"]), str(r["value"] or "")))

            tipos_ignorados = ",".join("?" * len(_EVENT_TYPES_IGNORADOS))
            for r in await db.query_all(
                f"""
                SELECT e.id, e.summary FROM episodic_memories e
                LEFT JOIN memory_vectors v
                    ON v.memory_type = 'episodic' AND v.memory_id = e.id
                WHERE v.id IS NULL AND e.event_type NOT IN ({tipos_ignorados})
                LIMIT ?
                """,
                (*tuple(_EVENT_TYPES_IGNORADOS), max_total),
            ):
                pendentes.append(("episodic", int(r["id"]), str(r["summary"] or "")))

            feitos = 0
            for i in range(0, len(pendentes), batch):
                lote = pendentes[i : i + batch]
                textos = [t[:1500] for _, _, t in lote if t.strip()]
                itens = [(mt, mid) for mt, mid, t in lote if t.strip()]
                if not textos:
                    continue
                try:
                    vecs = await self._embed(textos, "RETRIEVAL_DOCUMENT")
                except Exception as exc:
                    logger.warning(f"[EMBED] backfill lote falhou: {exc}")
                    break
                from datetime import datetime

                now = datetime.utcnow().isoformat() + "Z"
                for (mt, mid), vec in zip(itens, vecs):
                    await db.execute(
                        """
                        INSERT INTO memory_vectors (memory_type, memory_id, dim, vector, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(memory_type, memory_id)
                        DO UPDATE SET vector = excluded.vector, dim = excluded.dim,
                                      updated_at = excluded.updated_at
                        """,
                        (mt, mid, _DIM, _to_blob(vec), now),
                    )
                    feitos += 1
                await asyncio.sleep(1.0)

            if feitos:
                logger.info(f"[EMBED] Backfill: {feitos} memória(s) indexada(s)")
            return feitos
        except Exception as exc:
            logger.warning(f"[EMBED] Backfill falhou: {exc}")
            return 0


# Singleton do processo
_instance: Optional[EmbeddingService] = None


def get_embedding_service() -> Optional[EmbeddingService]:
    """Singleton; None se desabilitado ou sem chave."""
    global _instance
    if _instance is None:
        try:
            try:
                from .. import get_config
            except ImportError:
                from .. import get_config
            config = get_config()
            if not bool(getattr(config, "EMBEDDINGS_ENABLED", True)):
                return None
            api_key = getattr(config, "GEMINI_API_KEY", "") or ""
            if not api_key:
                return None
            _instance = EmbeddingService(api_key)
        except Exception as exc:
            logger.debug(f"[EMBED] indisponível: {exc}")
            return None
    return _instance
