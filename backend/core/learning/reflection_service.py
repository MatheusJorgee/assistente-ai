"""
ReflectionService — a Quinta-Feira aprendendo sozinha.

De tempos em tempos (e uma vez logo após ligar), ela relê o que aconteceu:
as conversas do dia, a memória diária e as amostras de hábito coletadas pelo
monitor proativo. Uma chamada de LLM destila isso em FATOS ESTÁVEIS (perfil,
preferências, pessoas, hábitos) que vão pra memória semântica — e num resumo
do dia que vira memória episódica. Ninguém pede: ela faz por conta própria.

O resultado alimenta o auto-recall do cérebro: a cada resposta, ela "lembra"
do que sabe sobre o Matheus sem precisar de tool call.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

# Prompts internos do sistema que não são conversa de verdade
_PREFIXOS_IGNORADOS = ("[AUTONOMOUS_LOOP_INVISIBLE_PROMPT]", "[HIDDEN_", "[SISTEMA]")


class ReflectionService:
    def __init__(
        self,
        *,
        brain: Any,
        memory_manager: Any,
        chat_db_path: str,
        interval_hours: float = 6.0,
        first_run_delay_seconds: int = 600,
    ) -> None:
        self._brain = brain
        self._memory = memory_manager
        self._chat_db_path = chat_db_path
        self._interval = max(1.0, interval_hours) * 3600
        self._first_delay = max(30, first_run_delay_seconds)

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self.last_run_ts: float = 0.0
        self.last_facts_count: int = 0

    # ── ciclo de vida ────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="reflection_service")
        logger.info("[REFLEXAO] Serviço de aprendizado iniciado")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[REFLEXAO] Serviço de aprendizado encerrado")

    async def _loop(self) -> None:
        await asyncio.sleep(self._first_delay)
        while self._running:
            try:
                await self.refletir()
            except Exception as exc:
                logger.warning(f"[REFLEXAO] Falha no ciclo: {exc}")
            await asyncio.sleep(self._interval)

    # ── coleta de matéria-prima ──────────────────────────────────────────────
    def _read_chat_sync(self, hours: int = 24, limit: int = 160) -> List[Dict[str, str]]:
        """Lê as conversas recentes do banco de chat (somente leitura)."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        try:
            conn = sqlite3.connect(self._chat_db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                """
                SELECT role, content, timestamp FROM messages
                WHERE timestamp >= ? ORDER BY id DESC LIMIT ?
                """,
                (cutoff, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
        except Exception as exc:
            logger.debug(f"[REFLEXAO] Sem acesso ao chat: {exc}")
            return []

        rows.reverse()  # ordem cronológica
        out = []
        for r in rows:
            content = (r.get("content") or "").strip()
            if not content or any(content.startswith(p) for p in _PREFIXOS_IGNORADOS):
                continue
            out.append({"role": r.get("role", ""), "content": content[:400]})
        return out

    async def _habit_digest(self, hours: int = 48) -> str:
        """Agrega as amostras de hábito (episódicas) em linhas de padrão."""
        try:
            res = await self._memory.search_memory(
                query="habit_sample", memory_type="episodic", limit=100
            )
        except Exception:
            return ""

        jogos: Counter = Counter()
        focos: Counter = Counter()
        horas_ativas: Counter = Counter()
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        for ep in res.get("episodic", []):
            try:
                if ep.get("event_type") != "habit_sample":
                    continue
                created = str(ep.get("created_at", "")).rstrip("Z")
                if created and datetime.fromisoformat(created) < cutoff:
                    continue
                payload = json.loads(ep.get("payload_json") or "{}")
                hora = payload.get("hora", "")
                if payload.get("jogo"):
                    jogos[payload["jogo"]] += 1
                if payload.get("foco"):
                    focos[payload["foco"]] += 1
                if payload.get("ativo") and hora:
                    horas_ativas[hora.split(":")[0] + "h"] += 1
            except Exception:
                continue

        linhas = []
        if jogos:
            linhas.append("Jogos vistos rodando: " + ", ".join(f"{j} ({n}x)" for j, n in jogos.most_common(4)))
        if focos:
            linhas.append("Apps mais usados: " + ", ".join(f"{a} ({n}x)" for a, n in focos.most_common(5)))
        if horas_ativas:
            linhas.append("Horários em que esteve ativo: " + ", ".join(h for h, _ in horas_ativas.most_common(6)))

        musica = await self._music_digest(hours)
        if musica:
            linhas.append(musica)
        return "\n".join(linhas)

    async def _music_digest(self, hours: int = 48) -> str:
        """Agrega o que ele andou OUVINDO (amostras do ouvido musical do monitor)."""
        try:
            res = await self._memory.search_memory(
                query="music_sample", memory_type="episodic", limit=120
            )
        except Exception:
            return ""

        faixas: Counter = Counter()
        artistas: Counter = Counter()
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        for ep in res.get("episodic", []):
            try:
                if ep.get("event_type") != "music_sample":
                    continue
                created = str(ep.get("created_at", "")).rstrip("Z")
                if created and datetime.fromisoformat(created) < cutoff:
                    continue
                payload = json.loads(ep.get("payload_json") or "{}")
                titulo = (payload.get("titulo") or "").strip()
                artista = (payload.get("artista") or "").strip()
                if titulo:
                    faixas[f"{titulo}" + (f" — {artista}" if artista else "")] += 1
                if artista:
                    artistas[artista] += 1
            except Exception:
                continue

        linhas = []
        if faixas:
            linhas.append(
                "Músicas que ele ouviu: " + ", ".join(f"{t} ({n}x)" for t, n in faixas.most_common(6))
            )
        if artistas:
            linhas.append(
                "Artistas mais ouvidos: " + ", ".join(f"{a} ({n}x)" for a, n in artistas.most_common(5))
            )
        return "\n".join(linhas)

    # ── o ato de refletir ────────────────────────────────────────────────────
    async def refletir(self) -> Dict[str, Any]:
        """Uma rodada de aprendizado. Retorna o que foi aprendido."""
        conversas = await asyncio.to_thread(self._read_chat_sync)
        # B10: não aprende com texto de terceiros (WhatsApp/web/documento) que passou pela conversa
        from ..memory.origem import sem_conteudo_externo
        limpas = []
        for m in conversas:
            texto, n = sem_conteudo_externo(m.get("content", ""))
            if n:
                logger.debug(f"[REFLEXAO] {n} bloco(s) de conteúdo externo ficaram de fora do aprendizado")
            if texto.strip() and texto.strip() != "[conteúdo externo omitido]":
                limpas.append(dict(m, content=texto))
        conversas = limpas
        habitos = await self._habit_digest()

        memoria_diaria = ""
        try:
            from ..memory.memory_manager import recuperar_memoria_diaria
            memoria_diaria = recuperar_memoria_diaria()
        except Exception:
            pass

        if not conversas and not habitos and not memoria_diaria:
            logger.info("[REFLEXAO] Nada novo pra aprender nesta rodada")
            self.last_run_ts = time.time()
            return {"fatos": 0}

        partes = []
        if conversas:
            chat_txt = "\n".join(f"[{m['role']}] {m['content']}" for m in conversas[-80:])
            partes.append(f"CONVERSAS RECENTES COM O MATHEUS:\n{chat_txt}")
        if memoria_diaria:
            partes.append(memoria_diaria)
        if habitos:
            partes.append(f"PADRÕES DE USO OBSERVADOS NO PC:\n{habitos}")

        system = (
            "Você é a Quinta-Feira no seu momento de reflexão privada: ninguém está lendo, "
            "você está organizando o que aprendeu sobre o Matheus hoje pra ficar mais esperta. "
            "Do material abaixo, extraia APENAS fatos ESTÁVEIS e úteis no futuro — preferências "
            "(inclusive GOSTO MUSICAL, se houver dados do que ele ouviu), pessoas da vida dele, "
            "hábitos e rotinas, projetos em andamento, traços de humor. "
            "NÃO inclua trivialidades de momento (ex: 'pediu uma música às 15h'), nem nada que "
            "você inventou — só o que está sustentado no material. Poucos fatos bons valem mais "
            "que muitos rasos (máximo 8). Escreva também um resumo do dia em 1-2 frases, no seu tom.\n\n"
            "AUTOAVALIAÇÃO DE ESTILO: releia as SUAS falas nas conversas e as reações dele logo "
            "depois. O que funcionou (ele engajou, riu, continuou)? O que não colou (ignorou, "
            "respondeu seco, reclamou, mandou parar)? Destile até 2 diretrizes CONCRETAS e "
            "acionáveis de como ajustar seu jeito de falar com ele (ex: 'quando ele está jogando, "
            "responda em uma frase', 'ele gosta quando você provoca sobre o DBD'). Se as conversas "
            "não derem evidência clara, devolva lista vazia — NÃO invente.\n"
            "PENDÊNCIAS: coisas que ELE disse que quer fazer, decidir ou resolver e que ficaram EM ABERTO "
            "(viagem a planejar, decisão, projeto travado). Até 3; cada uma com 'proximo_passo' = algo útil que "
            "você poderia fazer por ele (ex.: 'pesquisar hospedagens'). Só o que ELE disse; lista vazia se não houver.\n"
            'Responda APENAS um JSON válido: {"fatos": [{"categoria": "perfil|preferencia|pessoa|habito|projeto", '
            '"chave": "identificador-curto", "valor": "o fato em uma frase"}], "resumo_do_dia": "...", '
            '"pendencias": [{"texto": "...", "proximo_passo": "..."}], "estilo": ["diretriz 1", "diretriz 2"]}'
        )

        try:
            from core.llm_provider import Message
        except ImportError:
            from ..llm_provider import Message

        try:
            resp = await self._brain.llm_provider.generate(
                messages=[
                    Message(role="system", content=system),
                    Message(role="user", content="\n\n".join(partes)[:18000]),
                ],
                tools=None,
                temperature=0.3,
                # Gemini 2.5: thinking dinâmico consome o teto de output — sem
                # folga, o JSON volta vazio em material longo.
                max_tokens=4096,
            )
            data = self._parse_json(resp.text or "")
            if not data:
                logger.warning(
                    f"[REFLEXAO] LLM não devolveu JSON parseável "
                    f"(len={len(resp.text or '')}). Head: {(resp.text or '')[:200]!r}"
                )
        except Exception as exc:
            logger.warning(f"[REFLEXAO] LLM falhou: {exc}")
            return {"fatos": 0, "erro": str(exc)}

        fatos = data.get("fatos") or []
        salvos = 0
        for fato in fatos[:8]:
            try:
                categoria = str(fato.get("categoria", "perfil")).strip().lower() or "perfil"
                chave = str(fato.get("chave", "")).strip()[:80]
                valor = str(fato.get("valor", "")).strip()
                if not chave or not valor:
                    continue
                await self._memory.save_memory(
                    memory_type="semantic",
                    content=valor,
                    key=chave,
                    category=categoria,
                    confidence=0.75,
                    source="reflexao",
                )
                salvos += 1
            except Exception as exc:
                logger.debug(f"[REFLEXAO] Falha ao salvar fato: {exc}")

        # Pendências em aberto (sem chamada extra: vieram no mesmo JSON da reflexão)
        try:
            from .pendencias import get_pendencias
            for pend in (data.get("pendencias") or [])[:3]:
                if isinstance(pend, dict):
                    get_pendencias().adicionar(pend.get("texto", ""), pend.get("proximo_passo", ""))
        except Exception as exc:
            logger.debug(f"[REFLEXAO] pendências não salvas: {exc}")

        resumo = str(data.get("resumo_do_dia", "")).strip()
        if resumo:
            try:
                await self._memory.save_memory(
                    memory_type="episodic",
                    content=resumo,
                    event_type="diario",
                    importance=0.7,
                    tags=["reflexao", "diario"],
                )
            except Exception:
                pass

        # Autoavaliação: diretrizes de COMO falar com ele (perfil de estilo vivo)
        estilo_novas = 0
        try:
            estilo = [str(s).strip() for s in (data.get("estilo") or []) if str(s).strip()]
            if estilo:
                from .style_profile import get_style_profile
                estilo_novas = get_style_profile().add_many(estilo[:2])
        except Exception as exc:
            logger.debug(f"[REFLEXAO] estilo não salvo: {exc}")

        self.last_run_ts = time.time()
        self.last_facts_count = salvos

        # Faxina da memória, no máximo 1x/dia: funde fatos duplicados acumulados.
        try:
            if time.time() - getattr(self, "_last_consolida_ts", 0) > 86400:
                from .memory_consolidation import MemoryConsolidation
                r = await MemoryConsolidation(brain=self._brain, memory_manager=self._memory).consolidar()
                self._last_consolida_ts = time.time()
                if r.get("fundidos"):
                    logger.info(f"[REFLEXAO] Consolidação fundiu {r['fundidos']} duplicata(s)")
        except Exception as exc:
            logger.debug(f"[REFLEXAO] consolidação falhou: {exc}")

        logger.info(
            f"[REFLEXAO] Aprendi {salvos} fato(s) novo(s), {estilo_novas} diretriz(es) "
            f"de estilo. Resumo: {resumo[:80]}"
        )
        return {"fatos": salvos, "resumo": resumo, "estilo": estilo_novas}

    @staticmethod
    def _parse_json(txt: str) -> Dict[str, Any]:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
