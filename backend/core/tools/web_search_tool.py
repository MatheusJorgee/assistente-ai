"""
WebSearchTool — busca factual em tempo real (clima, notícias, fatos, status).

Leve por design: usa o endpoint HTML do DuckDuckGo via `requests` (em thread),
SEM navegador/Playwright. Isso evita o custo de CPU de lançar Chromium e a
fragilidade de subprocessos no Windows. Retorna os resultados como contexto
para o LLM compor a resposta.
"""

from __future__ import annotations

import asyncio
import html as _html
import re
from typing import List, Dict
from urllib.parse import unquote

import requests

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger, get_config
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger, get_config

logger = get_logger(__name__)

_DDG_HTML = "https://html.duckduckgo.com/html/"
_TAVILY_URL = "https://api.tavily.com/search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def _buscar_tavily(pergunta: str, limit: int, api_key: str) -> List[Dict[str, str]]:
    """Busca via Tavily (confiável, feita para IA). Requer chave."""
    payload = {
        "query": pergunta,
        "max_results": limit,
        "search_depth": "basic",
    }
    # Tavily usa autenticação via header Bearer (padrão atual). Mantemos também
    # api_key no body por compatibilidade com versões antigas da API.
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(_TAVILY_URL, json={**payload, "api_key": api_key}, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    resultados: List[Dict[str, str]] = []
    for item in data.get("results", [])[:limit]:
        resultados.append(
            {
                "titulo": (item.get("title") or "").strip(),
                "descricao": (item.get("content") or "").strip(),
                "url": item.get("url") or "",
            }
        )
    return resultados


def _strip_tags(s: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _parse_results(html_text: str, limit: int) -> List[Dict[str, str]]:
    """Extrai título/descrição/url dos blocos de resultado, ignorando anúncios."""
    resultados: List[Dict[str, str]] = []

    # Cada resultado começa com <div class="result ...">; anúncios têm "result--ad".
    blocos = re.split(r'<div class="result\b', html_text)
    for bloco in blocos[1:]:
        classe = bloco[: bloco.find('"')] if '"' in bloco else ""
        if "result--ad" in classe or "result--more" in classe:
            continue

        m_titulo = re.search(r'class="result__a"[^>]*>(.*?)</a>', bloco, re.DOTALL)
        if not m_titulo:
            continue
        titulo = _strip_tags(m_titulo.group(1))
        if not titulo:
            continue

        m_snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', bloco, re.DOTALL)
        descricao = _strip_tags(m_snip.group(1)) if m_snip else ""

        url = ""
        m_url = re.search(r'class="result__a"[^>]*href="(.*?)"', bloco)
        if m_url:
            url = _html.unescape(m_url.group(1))
            m_uddg = re.search(r"uddg=([^&]+)", url)  # DDG embrulha a URL real
            if m_uddg:
                url = unquote(m_uddg.group(1))

        resultados.append({"titulo": titulo, "descricao": descricao, "url": url})
        if len(resultados) >= limit:
            break

    return resultados


class _RateLimited(Exception):
    """DuckDuckGo respondeu com página de desafio anti-bot."""


def _buscar_ddgs_lib(pergunta: str, limit: int) -> List[Dict[str, str]]:
    """Busca via biblioteca ddgs (rotaciona endpoints — resiste muito mais a
    bloqueio que o scraping direto do html.duckduckgo.com)."""
    from ddgs import DDGS

    out: List[Dict[str, str]] = []
    for r in DDGS().text(pergunta, max_results=limit, region="br-pt"):
        out.append(
            {
                "titulo": (r.get("title") or "").strip(),
                "descricao": (r.get("body") or "").strip(),
                "url": r.get("href") or "",
            }
        )
    return out


def _buscar_ddg_scrape(pergunta: str, limit: int) -> List[Dict[str, str]]:
    resp = requests.post(_DDG_HTML, data={"q": pergunta}, headers=_HEADERS, timeout=10)
    # 202 ou página de "anomaly"/challenge = bloqueio anti-bot
    if resp.status_code == 202 or "anomaly" in resp.text.lower() or "challenge-form" in resp.text:
        raise _RateLimited()
    resp.raise_for_status()
    return _parse_results(resp.text, limit)


def _buscar_ddg(pergunta: str, limit: int) -> List[Dict[str, str]]:
    """Cadeia DuckDuckGo: biblioteca ddgs primeiro, scraping HTML como reserva."""
    try:
        resultados = _buscar_ddgs_lib(pergunta, limit)
        if resultados:
            return resultados
    except Exception as exc:
        logger.debug(f"[WEBSEARCH] ddgs lib falhou: {exc}")
    return _buscar_ddg_scrape(pergunta, limit)


class WebSearchTool(MotorTool):
    """Busca factual em tempo real na web (clima, notícias, status, fatos atuais)."""

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="pesquisar_informacao_online",
                description=(
                    "Busca informações factuais em tempo real na web (DuckDuckGo). "
                    "Use SEMPRE que precisar de dados atuais: clima, notícias, cotações, "
                    "status de serviços (AWS, etc.), eventos recentes ou qualquer fato que "
                    "mude com o tempo. NÃO use para abrir aplicativos locais."
                ),
                category="web",
                parameters=[
                    ToolParameter(
                        name="pergunta",
                        type="string",
                        description="A pergunta ou termo a pesquisar (ex: 'clima em Sao Paulo hoje').",
                        required=True,
                    ),
                    ToolParameter(
                        name="limite",
                        type="int",
                        description="Número máximo de resultados (padrão: 4).",
                        required=False,
                        default=4,
                    ),
                ],
                examples=[
                    "pergunta=clima em Sao Paulo hoje",
                    "pergunta=cotacao do dolar hoje",
                    "pergunta=ultimas noticias sobre IA",
                ],
                security_level=SecurityLevel.LOW,
                tags=["web", "search", "real-time", "information"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        pergunta = kwargs.get("pergunta") or kwargs.get("query")
        return isinstance(pergunta, str) and bool(pergunta.strip())

    @staticmethod
    def _is_news_query(q: str) -> bool:
        ql = q.lower()
        termos = ["noticia", "notícia", "manchete", "novidade", "acontecendo",
                  "headlines", "jornal", "ultimas noticias", "últimas notícias"]
        return any(t in ql for t in termos)

    async def _buscar_noticias_rss(self, limite: int) -> List[Dict[str, str]]:
        """Manchetes via G1 RSS (confiável, sem chave, com resumo) — alinhado ao visor."""
        try:
            from ..briefing.news import get_top_news_rich, get_top_news
            ricas = await get_top_news_rich(limit=limite)
            if ricas:
                return [{"titulo": a["titulo"], "descricao": a.get("resumo", ""), "url": a.get("url", "")} for a in ricas]
            # fallback: manchetes simples do Google News
            titulos = await get_top_news(limit=limite)
            return [{"titulo": t, "descricao": "", "url": ""} for t in titulos]
        except Exception as exc:
            logger.warning(f"[WEBSEARCH] RSS falhou: {exc}")
            return []

    async def execute(self, **kwargs) -> str:
        pergunta = str(kwargs.get("pergunta") or kwargs.get("query") or "").strip()
        if not pergunta:
            return "[ERRO] Pergunta não fornecida."

        limite = int(kwargs.get("limite", 4) or 4)

        # NOTÍCIAS: usar RSS (estável, sem chave) como fonte primária.
        if self._is_news_query(pergunta):
            logger.info(f"[WEBSEARCH] Noticia detectada -> RSS: {pergunta!r}")
            resultados = await self._buscar_noticias_rss(max(limite, 5))
            if resultados:
                linhas = ["MANCHETES DO DIA (use a primeira no visor como tipo='noticia'):"]
                for i, r in enumerate(resultados, 1):
                    linhas.append(f"[{i}] {r['titulo']}")
                logger.info(f"[WEBSEARCH] {len(resultados)} manchetes via RSS")
                return "\n".join(linhas)
            # se RSS falhar, segue para a busca normal abaixo

        api_key = get_config().TAVILY_API_KEY
        provedor = "Tavily" if api_key else "DuckDuckGo"
        logger.info(f"[WEBSEARCH] Pesquisando ({provedor}): {pergunta!r}")

        resultados = []
        try:
            if api_key:
                try:
                    resultados = await asyncio.to_thread(_buscar_tavily, pergunta, limite, api_key)
                except Exception as tav_exc:
                    # Chave inválida/expirada ou erro da Tavily → cai para o DuckDuckGo
                    logger.warning(f"[WEBSEARCH] Tavily falhou ({tav_exc}); usando DuckDuckGo")
                    resultados = await asyncio.to_thread(_buscar_ddg, pergunta, limite)
            else:
                resultados = await asyncio.to_thread(_buscar_ddg, pergunta, limite)
        except _RateLimited:
            logger.warning("[WEBSEARCH] DuckDuckGo bloqueou (anti-bot)")
            # Última tentativa: manchetes RSS, úteis mesmo fora de contexto de notícia
            rss = await self._buscar_noticias_rss(5)
            if rss:
                linhas = ["Busca direta indisponível; trago as manchetes do momento:"]
                linhas += [f"[{i}] {r['titulo']}" for i, r in enumerate(rss, 1)]
                return "\n".join(linhas)
            return (
                "A busca gratuita (DuckDuckGo) está temporariamente bloqueada por excesso "
                "de requisições. Para busca confiável, configure TAVILY_API_KEY no .env."
            )
        except Exception as exc:
            logger.warning(f"[WEBSEARCH] Falha: {type(exc).__name__}: {exc}")
            return (
                "Não consegui acessar a busca online agora. "
                "Pode ser instabilidade de rede; tente de novo em instantes."
            )

        if not resultados:
            return f"Nenhum resultado encontrado para '{pergunta}'."

        linhas = ["RESULTADOS DA PESQUISA ONLINE:"]
        for i, r in enumerate(resultados, 1):
            linhas.append(f"[{i}] {r['titulo']}")
            if r["descricao"]:
                linhas.append(f"    {r['descricao']}")
            if r["url"]:
                linhas.append(f"    Fonte: {r['url']}")
        logger.info(f"[WEBSEARCH] {len(resultados)} resultados para {pergunta!r}")
        return "\n".join(linhas)
