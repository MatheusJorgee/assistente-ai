"""
Memory Manager (Long-Term Memory): episódica + semântica.

Persistência usa o SQLite canônico do Core.
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
    """Gerenciador de memória de longo prazo."""

    # Episódicos de telemetria: não entram no índice vetorial
    _EVENT_TYPES_SEM_INDICE = {"habit_sample", "music_sample"}

    def __init__(self) -> None:
        self._initialized = False

    def _index_async(self, memory_type: str, memory_id: Any, texto: str, event_type: str = "") -> None:
        """Indexação vetorial em background (best-effort; backfill cobre falhas)."""
        if event_type in self._EVENT_TYPES_SEM_INDICE:
            return
        try:
            from .embedding_service import get_embedding_service
            svc = get_embedding_service()
            if svc and memory_id is not None:
                svc.index_memory_background(memory_type, int(memory_id), texto)
        except Exception:
            pass

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
        # Histórico: o que valia ANTES de ser substituído, e propostas bloqueadas (ex.: a reflexão tentando
        # sobrescrever o que você corrigiu). Nada some sem deixar rastro.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                valor TEXT NOT NULL,
                fonte TEXT,
                confianca REAL,
                motivo TEXT NOT NULL,
                quando TEXT NOT NULL,
                resolvido INTEGER DEFAULT 0
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
            self._index_async("episodic", row_id, content, event_type=event_type)
            return {"ok": True, "memory_type": "episodic", "id": row_id}

        if normalized == "semantic":
            from .qualidade import canonicalizar_categoria, mesmo_valor, rank_da_fonte
            category = canonicalizar_categoria(category)
            semantic_key = (key or content[:120]).strip() or "fact"
            confianca = float(max(0.0, min(1.0, confidence)))
            existing = await db.query_all(
                "SELECT id, value, confidence, source FROM semantic_memories WHERE category = ? AND key = ? LIMIT 1",
                (category, semantic_key),
            )
            if existing:
                e = existing[0]
                eid = int(e["id"])
                # Mesmo fato visto de novo: REFORÇA (confiança sobe um pouco; a fonte de maior autoridade fica).
                if mesmo_valor(e["value"], content):
                    nova = min(0.95, max(float(e["confidence"] or 0.0), confianca) + 0.05)
                    fonte_final = source if rank_da_fonte(source) > rank_da_fonte(e["source"]) else (e["source"] or source)
                    await db.execute(
                        "UPDATE semantic_memories SET confidence = ?, source = ?, updated_at = ? WHERE id = ?",
                        (nova, fonte_final, now, eid),
                    )
                    return {"ok": True, "memory_type": "semantic", "id": eid, "updated": True, "reforcado": True}
                # Valor diferente: quem tem MENOS autoridade não sobrescreve (fica só como proposta).
                if rank_da_fonte(source) < rank_da_fonte(e["source"]):
                    await db.execute(
                        "INSERT INTO semantic_history (memory_id, valor, fonte, confianca, motivo, quando) VALUES (?, ?, ?, ?, ?, ?)",
                        (eid, content, source, confianca, "proposta_bloqueada", now),
                    )
                    return {"ok": True, "memory_type": "semantic", "id": eid, "updated": False, "protegido": True}
                await db.execute(
                    "INSERT INTO semantic_history (memory_id, valor, fonte, confianca, motivo, quando, resolvido) VALUES (?, ?, ?, ?, ?, ?, 1)",
                    (eid, e["value"], e["source"], e["confidence"], "substituido", now),
                )
                await db.execute(
                    "UPDATE semantic_memories SET value = ?, confidence = ?, source = ?, updated_at = ? WHERE id = ?",
                    (content, confianca, source, now, eid),
                )
                self._index_async("semantic", eid, f"({category}) {content}")
                return {"ok": True, "memory_type": "semantic", "id": eid, "updated": True}

            row_id = await db.execute(
                """
                INSERT INTO semantic_memories
                (category, key, value, confidence, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (category, semantic_key, content, confianca, source, now, now),
            )
            self._index_async("semantic", row_id, f"({category}) {content}")
            return {"ok": True, "memory_type": "semantic", "id": row_id, "updated": False}

        return {"ok": False, "error": "memory_type inválido. Use 'episodic' ou 'semantic'."}

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

    async def resumo_categorias(self, limite: int = 8) -> List[Dict[str, Any]]:
        """Categorias de fatos guardados, com contagem (A7): o modelo passa a saber O QUE pode buscar."""
        await self.initialize()
        db = await get_database()
        return await db.query_all(
            """
            SELECT category, COUNT(*) AS n FROM semantic_memories
            GROUP BY category ORDER BY n DESC, category ASC LIMIT ?
            """,
            (max(1, min(int(limite), 30)),),
        )

    async def delete_semantic(self, mem_id: int) -> bool:
        """Remove um fato semântico por id (usado na consolidação)."""
        await self.initialize()
        db = await get_database()
        try:
            await db.execute("DELETE FROM semantic_memories WHERE id = ?", (int(mem_id),))
            try:
                await db.execute(
                    "DELETE FROM memory_vectors WHERE memory_type='semantic' AND memory_id = ?",
                    (int(mem_id),),
                )
            except Exception:
                pass
            return True
        except Exception as exc:
            logger.debug(f"[MEMORY] delete_semantic falhou: {exc}")
            return False

    async def update_semantic_value(self, mem_id: int, value: str, fonte: Optional[str] = "usuario") -> bool:
        """Reescreve o valor de um fato por id + reindexa embedding.

        `fonte="usuario"` (padrão, edição feita por VOCÊ na tela): o fato passa a ter a maior autoridade
        (a próxima reflexão não o sobrescreve) e o valor anterior vai para o histórico. `fonte=None` mantém
        a fonte atual (usado pela faxina automática, que não pode se passar por você)."""
        await self.initialize()
        db = await get_database()
        now = datetime.utcnow().isoformat() + "Z"
        try:
            atual = await db.query_all(
                "SELECT category, value, source, confidence FROM semantic_memories WHERE id = ? LIMIT 1", (int(mem_id),)
            )
            if not atual:
                return False
            a0 = atual[0]
            if str(a0["value"]).strip() != value.strip():
                await db.execute(
                    "INSERT INTO semantic_history (memory_id, valor, fonte, confianca, motivo, quando, resolvido) VALUES (?, ?, ?, ?, ?, ?, 1)",
                    (int(mem_id), a0["value"], a0["source"], a0["confidence"], "edicao" if fonte else "faxina", now),
                )
            if fonte:
                await db.execute(
                    "UPDATE semantic_memories SET value = ?, source = ?, confidence = ?, updated_at = ? WHERE id = ?",
                    (value, fonte, 0.95, now, int(mem_id)),
                )
            else:
                await db.execute(
                    "UPDATE semantic_memories SET value = ?, updated_at = ? WHERE id = ?",
                    (value, now, int(mem_id)),
                )
            self._index_async("semantic", int(mem_id), f"({a0['category']}) {value}")
            return True
        except Exception as exc:
            logger.debug(f"[MEMORY] update_semantic_value falhou: {exc}")
            return False

    # ── memória v2: perfil essencial, uso, categorias, conflitos, saúde ─────────────
    _COLUNAS_SEM = "id, category, key, value, confidence, source, created_at, updated_at, last_accessed_at, access_count"

    async def perfil_essencial(self, limite: int = 8) -> List[Dict[str, Any]]:
        """Os fatos que entram em TODA resposta: pontuados (categoria x confiança x uso), sem curiosidade do mundo."""
        from .qualidade import escolher_perfil
        await self.initialize()
        db = await get_database()
        linhas = await db.query_all(f"SELECT {self._COLUNAS_SEM} FROM semantic_memories", ())
        return escolher_perfil(linhas, limite)

    async def registrar_acesso(self, ids: Any) -> None:
        """Conta o uso: alimenta ranking e envelhecimento. Um UPDATE só (barato)."""
        lista = [int(i) for i in list(ids)[:50] if str(i).lstrip("-").isdigit()]
        if not lista:
            return
        await self.initialize()
        db = await get_database()
        marks = ",".join("?" * len(lista))
        try:
            await db.execute(
                f"UPDATE semantic_memories SET access_count = COALESCE(access_count, 0) + 1, last_accessed_at = ? WHERE id IN ({marks})",
                (datetime.utcnow().isoformat() + "Z", *lista),
            )
        except Exception as exc:
            logger.debug(f"[MEMORY] registrar_acesso falhou: {exc}")

    async def normalizar_categorias(self) -> Dict[str, Any]:
        """Junta categorias fragmentadas ('habito|pessoa', 'traço-humor'...). Idempotente. Guarda uma cópia
        (pré-imagem) antes de mexer; se dois fatos colidem, fica o de maior autoridade/confiança."""
        from .origem import salvar_preimagem
        from .qualidade import canonicalizar_categoria, rank_da_fonte
        await self.initialize()
        db = await get_database()
        fatos = await db.query_all(f"SELECT {self._COLUNAS_SEM} FROM semantic_memories", ())
        mudar = [(f, canonicalizar_categoria(f["category"])) for f in fatos if canonicalizar_categoria(f["category"]) != f["category"]]
        if not mudar:
            return {"alteradas": 0, "fundidas": 0}
        salvar_preimagem(fatos)
        agora = datetime.utcnow().isoformat() + "Z"
        alteradas = fundidas = 0
        for f, canon in mudar:
            colisao = await db.query_all(
                "SELECT id, value, source, confidence FROM semantic_memories WHERE category = ? AND key = ? AND id != ? LIMIT 1",
                (canon, f["key"], f["id"]),
            )
            if colisao:
                c = colisao[0]
                # fica quem tem mais autoridade; empate: maior confiança
                perde_f = (rank_da_fonte(f["source"]), float(f["confidence"] or 0)) < (rank_da_fonte(c["source"]), float(c["confidence"] or 0))
                sai_id, sai_val, sai_src, sai_conf, fica_id = (
                    (f["id"], f["value"], f["source"], f["confidence"], c["id"]) if perde_f else (c["id"], c["value"], c["source"], c["confidence"], f["id"])
                )
                await db.execute(
                    "INSERT INTO semantic_history (memory_id, valor, fonte, confianca, motivo, quando, resolvido) VALUES (?, ?, ?, ?, ?, ?, 1)",
                    (fica_id, sai_val, sai_src, sai_conf, "fundida_na_normalizacao", agora),
                )
                await db.execute("DELETE FROM semantic_memories WHERE id = ?", (sai_id,))
                try:  # a tabela de vetores só existe se o serviço de embeddings já rodou
                    await db.execute("DELETE FROM memory_vectors WHERE memory_type='semantic' AND memory_id = ?", (sai_id,))
                except Exception:
                    pass
                if not perde_f:
                    await db.execute("UPDATE semantic_memories SET category = ? WHERE id = ?", (canon, f["id"]))
                fundidas += 1
            else:
                await db.execute("UPDATE semantic_memories SET category = ? WHERE id = ?", (canon, f["id"]))
            alteradas += 1
        return {"alteradas": alteradas, "fundidas": fundidas}

    async def esqueciveis(self) -> List[Dict[str, Any]]:
        from .qualidade import esqueciveis
        await self.initialize()
        db = await get_database()
        return esqueciveis(await db.query_all(f"SELECT {self._COLUNAS_SEM} FROM semantic_memories", ()))

    async def conflitos(self, limite: int = 20) -> List[Dict[str, Any]]:
        """Propostas que NÃO foram aplicadas porque o fato atual tem mais autoridade (ex.: algo que você corrigiu)."""
        await self.initialize()
        db = await get_database()
        return await db.query_all(
            """
            SELECT h.id, h.memory_id, h.valor AS proposto, h.fonte AS proposto_por, h.quando,
                   s.value AS atual, s.category, s.key, s.source AS atual_por
            FROM semantic_history h JOIN semantic_memories s ON s.id = h.memory_id
            WHERE h.motivo = 'proposta_bloqueada' AND h.resolvido = 0
            ORDER BY h.quando DESC LIMIT ?
            """,
            (max(1, min(int(limite), 100)),),
        )

    async def resolver_conflito(self, hid: int, aceitar: bool) -> bool:
        """Você decide: aceitar (o valor proposto vira o fato, com a sua autoridade) ou manter o atual."""
        await self.initialize()
        db = await get_database()
        linha = await db.query_all(
            "SELECT id, memory_id, valor FROM semantic_history WHERE id = ? AND motivo = 'proposta_bloqueada' AND resolvido = 0",
            (int(hid),),
        )
        if not linha:
            return False
        if aceitar:
            await self.update_semantic_value(int(linha[0]["memory_id"]), str(linha[0]["valor"]), fonte="usuario")
        await db.execute("UPDATE semantic_history SET resolvido = 1 WHERE id = ?", (int(hid),))
        return True

    async def podar_telemetria(self, habito_dias: int = 30, musica_dias: int = 90) -> Dict[str, int]:
        """Amostras de hábito/música são telemetria, não conhecimento: envelhecem e saem."""
        await self.initialize()
        db = await get_database()
        saida = {}
        for tipo, dias in (("habit_sample", habito_dias), ("music_sample", musica_dias)):
            n = (await db.query_all(
                "SELECT COUNT(*) AS n FROM episodic_memories WHERE event_type = ? AND datetime(created_at) < datetime('now', ?)",
                (tipo, f"-{int(dias)} days"),
            ))[0]["n"]
            if n:
                await db.execute(
                    "DELETE FROM episodic_memories WHERE event_type = ? AND datetime(created_at) < datetime('now', ?)",
                    (tipo, f"-{int(dias)} days"),
                )
            saida[tipo] = int(n)
        return saida

    async def saude(self) -> Dict[str, Any]:
        from .qualidade import esqueciveis
        await self.initialize()
        db = await get_database()
        fatos = await db.query_all(f"SELECT {self._COLUNAS_SEM} FROM semantic_memories", ())
        por_fonte: Dict[str, int] = {}
        por_cat: Dict[str, int] = {}
        for f in fatos:
            por_fonte[str(f["source"] or "?")] = por_fonte.get(str(f["source"] or "?"), 0) + 1
            por_cat[str(f["category"])] = por_cat.get(str(f["category"]), 0) + 1
        return {
            "fatos": len(fatos), "por_fonte": por_fonte, "por_categoria": por_cat,
            "nunca_usados": sum(1 for f in fatos if not int(f["access_count"] or 0)),
            "esqueciveis": len(esqueciveis(fatos)),
            "conflitos": len(await self.conflitos(100)),
            "do_mundo": por_cat.get("aprendizado", 0),
        }

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

