"""
CuriosityService — a Quinta-Feira aprendendo com a INTERNET, por conta própria.

De tempos em tempos ela olha o que sabe do Matheus (perfil, projetos, hábitos,
assuntos recentes) e decide O QUE gostaria de pesquisar na web pra ficar mais
útil e mais interessante — sem ninguém pedir. Cada query passa pelo SearchGuard
(temas vetados, PII removida, cota diária) antes de tocar a rede.

O que ela acha vira:
  - memórias semânticas (source="curiosidade") → entram no auto-recall;
  - uma "descoberta" episódica no tom dela → o pulso de presença pode
    comentar espontaneamente ("li uma coisa hoje que você ia gostar...").

É o ciclo de um organismo que não fica parado esperando input: percebe,
se interessa, vai atrás, aprende e traz pra conversa.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

from .search_guard import SearchGuard

logger = get_logger(__name__)


class CuriosityService:
    def __init__(
        self,
        *,
        brain: Any,
        memory_manager: Any,
        config: Any,
        interval_hours: float = 3.0,
        first_run_delay_seconds: int = 900,
    ) -> None:
        self._brain = brain
        self._memory = memory_manager
        self._config = config
        self._interval = max(0.5, interval_hours) * 3600
        self._first_delay = max(30, first_run_delay_seconds)

        runtime_dir = Path(__file__).resolve().parents[2] / ".runtime"
        self._guard = SearchGuard(
            runtime_dir=runtime_dir,
            max_por_rodada=int(getattr(config, "CURIOSITY_MAX_PER_RUN", 3)),
            max_por_dia=int(getattr(config, "CURIOSITY_MAX_PER_DAY", 12)),
        )

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self.last_run_ts: float = 0.0
        self.last_descoberta: str = ""
        self._ultimos_temas: List[str] = []  # anti-repetição entre rodadas

    # ── ciclo de vida ────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="curiosity_service")
        logger.info("[CURIOSIDADE] Aprendizado via internet iniciado")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[CURIOSIDADE] Encerrado")

    async def _loop(self) -> None:
        await asyncio.sleep(self._first_delay)
        while self._running:
            try:
                await self.explorar()
            except Exception as exc:
                logger.warning(f"[CURIOSIDADE] Falha na rodada: {exc}")
            await asyncio.sleep(self._interval)

    # ── matéria-prima: o que ela sabe ────────────────────────────────────────
    async def _montar_contexto(self) -> str:
        partes: List[str] = []
        try:
            perfil = await self._memory.retrieve_memory(memory_type="semantic", limit=20)
            linhas = []
            for m in perfil.get("semantic", []):
                val = str(m.get("value", "")).strip()
                cat = str(m.get("category", "")).strip()
                if val and cat != "aprendizado":  # aprendizados dela não realimentam a escolha
                    linhas.append(f"- ({cat}) {val}")
            if linhas:
                partes.append("O QUE VOCÊ SABE DO MATHEUS:\n" + "\n".join(linhas[:16]))
        except Exception:
            pass

        try:
            res = await self._memory.search_memory(
                query="descoberta", memory_type="episodic", limit=8
            )
            descobertas = [
                str(e.get("summary") or e.get("content") or "").strip()
                for e in res.get("episodic", [])
                if e.get("event_type") == "descoberta"
            ]
            if descobertas:
                partes.append(
                    "DESCOBERTAS RECENTES (NÃO repita estes temas):\n- "
                    + "\n- ".join(d[:120] for d in descobertas[:6])
                )
        except Exception:
            pass

        if self._ultimos_temas:
            partes.append(
                "TEMAS JÁ PESQUISADOS HOJE (evite): " + "; ".join(self._ultimos_temas[-8:])
            )
        return "\n\n".join(partes)

    # ── uma rodada de curiosidade ────────────────────────────────────────────
    async def explorar(self) -> Dict[str, Any]:
        cota = self._guard.cota_disponivel()
        if cota <= 0:
            logger.info("[CURIOSIDADE] Cota diária esgotada — rodada pulada")
            self.last_run_ts = time.time()
            return {"pesquisas": 0, "motivo": "cota esgotada"}

        contexto = await self._montar_contexto()
        queries = await self._escolher_pesquisas(contexto, cota)
        if not queries:
            logger.info("[CURIOSIDADE] Nada despertou curiosidade nesta rodada")
            self.last_run_ts = time.time()
            return {"pesquisas": 0}

        # Pesquisa com guarda — temas vetados caem aqui, PII é raspada
        materiais: List[str] = []
        feitas: List[str] = []
        for q in queries:
            permitida, q_limpa = self._guard.validar_query(q)
            if not permitida:
                logger.info(f"[CURIOSIDADE] Query barrada ({q_limpa}): {q!r}")
                continue
            resultados = await self._pesquisar(q_limpa)
            resultados = self._guard.filtrar_resultados(resultados)
            self._guard.consumir_cota(1)
            feitas.append(q_limpa)
            if resultados:
                bloco = "\n".join(
                    f"- {r['titulo']}: {r['descricao'][:220]}" for r in resultados[:4]
                )
                materiais.append(f"PESQUISA: {q_limpa}\n{bloco}")

        self._ultimos_temas.extend(feitas)
        self._ultimos_temas = self._ultimos_temas[-16:]

        if not materiais:
            self.last_run_ts = time.time()
            return {"pesquisas": len(feitas), "aprendizados": 0}

        aprendidos, descoberta = await self._destilar(materiais)
        self.last_run_ts = time.time()
        if descoberta:
            self.last_descoberta = descoberta
        logger.info(
            f"[CURIOSIDADE] Rodada: {len(feitas)} pesquisa(s), "
            f"{aprendidos} aprendizado(s). Descoberta: {descoberta[:80]!r}"
        )
        return {"pesquisas": len(feitas), "aprendizados": aprendidos, "descoberta": descoberta}

    async def _escolher_pesquisas(self, contexto: str, cota: int) -> List[str]:
        """Ela decide o que quer saber — no máximo `cota` queries específicas."""
        try:
            from core.llm_provider import Message
        except ImportError:
            from ..llm_provider import Message

        system = (
            "Você é a Quinta-Feira no seu momento de curiosidade: vai pesquisar na "
            "internet POR CONTA PRÓPRIA algo que te deixe mais útil e mais interessante "
            "pro Matheus. Olhe o que você sabe dele (interesses, projetos, jogos, rotina) "
            "e escolha até " + str(cota) + " pesquisas ESPECÍFICAS que valham a pena AGORA "
            "(novidade de um jogo que ele joga, técnica útil pro projeto dele, algo do dia "
            "a dia dele que você pode melhorar, um assunto que ele comentou). Seja concreta "
            "e específica — nada genérico tipo 'novidades de tecnologia'. Se nada parecer "
            "genuinamente útil, devolva lista vazia.\n"
            'Responda APENAS JSON: {"pesquisas": ["query 1", "query 2"]}'
        )
        try:
            resp = await self._brain.llm_provider.generate(
                messages=[
                    Message(role="system", content=system),
                    Message(role="user", content=contexto or "Você ainda sabe pouco sobre ele."),
                ],
                tools=None,
                temperature=0.8,
                max_tokens=2048,
            )
            data = self._parse_json(resp.text or "")
            queries = [str(q).strip() for q in (data.get("pesquisas") or []) if str(q).strip()]
            return queries[:cota]
        except Exception as exc:
            logger.warning(f"[CURIOSIDADE] Falha ao escolher pesquisas: {exc}")
            return []

    async def _pesquisar(self, query: str) -> List[Dict[str, str]]:
        """Cadeia de busca: Tavily (se chave) → DuckDuckGo (ddgs+scrape) → Google News RSS."""
        try:
            from core.tools.web_search_tool import _buscar_tavily, _buscar_ddg
        except ImportError:
            from ..tools.web_search_tool import _buscar_tavily, _buscar_ddg

        api_key = getattr(self._config, "TAVILY_API_KEY", "")
        if api_key:
            try:
                resultados = await asyncio.to_thread(_buscar_tavily, query, 5, api_key)
                if resultados:
                    return resultados
            except Exception:
                pass
        try:
            resultados = await asyncio.to_thread(_buscar_ddg, query, 5)
            if resultados:
                return resultados
        except Exception as exc:
            logger.debug(f"[CURIOSIDADE] DDG falhou ({query!r}): {exc}")
        return await asyncio.to_thread(self._buscar_google_news_rss, query, 5)

    @staticmethod
    def _buscar_google_news_rss(query: str, limit: int) -> List[Dict[str, str]]:
        """Último recurso keyless: busca por tópico no RSS do Google News.
        (requests síncrono de propósito — aiohttp trava em news.google.com no Windows)"""
        import re as _re
        import urllib.parse as _up

        import requests as _rq

        try:
            url = (
                "https://news.google.com/rss/search?q="
                + _up.quote(query)
                + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
            )
            resp = _rq.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            itens = _re.findall(
                r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>", resp.text, _re.DOTALL
            )
            out = []
            for titulo, link in itens[:limit]:
                titulo = _re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", titulo).strip()
                out.append({"titulo": titulo, "descricao": "", "url": link.strip()})
            return out
        except Exception as exc:
            logger.debug(f"[CURIOSIDADE] Google News RSS falhou: {exc}")
            return []

    async def _destilar(self, materiais: List[str]) -> tuple:
        """Transforma os resultados em aprendizados + uma descoberta no tom dela."""
        try:
            from core.llm_provider import Message
        except ImportError:
            from ..llm_provider import Message

        system = (
            "Você é a Quinta-Feira digerindo o que acabou de ler na internet (pesquisas "
            "que VOCÊ quis fazer). Extraia só o que vale guardar:\n"
            "1) até 4 aprendizados FACTUAIS e estáveis (uma frase cada, com o essencial);\n"
            "2) UMA 'descoberta' pra contar pro Matheus depois, NO SEU TOM (1-2 frases "
            "faladas, espontâneas, como quem chega com novidade — sem 'pesquisei na "
            "internet', sem markdown). Se nada prestou, campos vazios.\n"
            'Responda APENAS JSON: {"aprendizados": [{"chave": "id-curto", "valor": "fato"}], '
            '"descoberta": "fala"}'
        )
        try:
            resp = await self._brain.llm_provider.generate(
                messages=[
                    Message(role="system", content=system),
                    Message(role="user", content="\n\n".join(materiais)[:14000]),
                ],
                tools=None,
                temperature=0.6,
                max_tokens=3072,
            )
            data = self._parse_json(resp.text or "")
        except Exception as exc:
            logger.warning(f"[CURIOSIDADE] Falha ao destilar: {exc}")
            return 0, ""

        salvos = 0
        for ap in (data.get("aprendizados") or [])[:4]:
            chave = str(ap.get("chave", "")).strip()[:80]
            valor = str(ap.get("valor", "")).strip()
            if not chave or not valor:
                continue
            try:
                await self._memory.save_memory(
                    memory_type="semantic",
                    content=valor,
                    key=chave,
                    category="aprendizado",
                    confidence=0.6,
                    source="curiosidade",
                )
                salvos += 1
            except Exception as exc:
                logger.debug(f"[CURIOSIDADE] Falha ao salvar aprendizado: {exc}")

        descoberta = str(data.get("descoberta", "")).strip()
        if descoberta:
            try:
                await self._memory.save_memory(
                    memory_type="episodic",
                    content=descoberta,
                    event_type="descoberta",
                    importance=0.6,
                    tags=["curiosidade", "descoberta"],
                )
            except Exception:
                pass
            # Marco do dia: o estado interno passa a saber que ela aprendeu algo
            try:
                from ..proactive.internal_state import get_internal_state
                get_internal_state().registrar_marco("você aprendeu algo novo na internet")
            except Exception:
                pass
        return salvos, descoberta

    @staticmethod
    def _parse_json(txt: str) -> Dict[str, Any]:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
