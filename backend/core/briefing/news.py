"""
Manchetes via RSS do Google News (pt-BR) — leve, sem navegador nem chave.

Optamos por RSS em vez de scraping com Playwright: estável (formato XML fixo),
sem custo de CPU (não abre Chromium) e sem chave de API.

Usa `requests` em thread (asyncio.to_thread): no Windows o aiohttp trava neste
endpoint específico, e por ser chamada única no startup o custo é irrelevante.
"""

from __future__ import annotations

import asyncio
import re
from typing import List, Dict
import xml.etree.ElementTree as ET

import requests

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419"
# G1 RSS inclui imagem (media:content) + resumo + URL real do artigo.
_G1_RSS = "https://g1.globo.com/rss/g1/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (QuintaFeira Briefing)"}


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _fetch_rich_sync(limit: int) -> List[Dict[str, str]]:
    """Notícias ricas (título + resumo + url + imagem) via G1 RSS."""
    resp = requests.get(_G1_RSS, headers=_HEADERS, timeout=10)
    if resp.status_code != 200:
        logger.warning(f"[NEWS] G1 HTTP {resp.status_code}")
        return []

    root = ET.fromstring(resp.text)
    noticias: List[Dict[str, str]] = []
    for item in root.findall(".//item"):
        titulo = resumo = url = imagem = ""
        for child in item:
            nome = _local(child.tag)
            if nome == "title":
                titulo = (child.text or "").strip()
            elif nome == "subtitle":
                resumo = (child.text or "").strip()
            elif nome == "link":
                url = (child.text or "").strip()
            elif nome == "content" and child.get("url") and not imagem:
                # media:content
                if (child.get("medium") == "image") or re.search(r"\.(jpg|jpeg|png|webp)", child.get("url", ""), re.I):
                    imagem = child.get("url", "")
            elif nome == "description" and not imagem:
                m = re.search(r'<img[^>]+src="([^"]+)"', child.text or "")
                if m:
                    imagem = m.group(1)

        if titulo:
            noticias.append({"titulo": titulo, "resumo": resumo, "url": url, "imagem": imagem})
        if len(noticias) >= limit:
            break
    return noticias


async def get_top_news_rich(limit: int = 5) -> List[Dict[str, str]]:
    """Notícias com título, resumo, URL e imagem (para o visor). Lista vazia em falha."""
    try:
        return await asyncio.to_thread(_fetch_rich_sync, limit)
    except Exception as exc:
        logger.warning(f"[NEWS] erro ao consultar G1 RSS: {type(exc).__name__}: {exc}")
        return []


def _fetch_sync(limit: int) -> List[str]:
    headers = {"User-Agent": "Mozilla/5.0 (QuintaFeira Briefing)"}
    resp = requests.get(_GOOGLE_NEWS_RSS, headers=headers, timeout=10)
    if resp.status_code != 200:
        logger.warning(f"[NEWS] HTTP {resp.status_code}")
        return []

    root = ET.fromstring(resp.text)
    titulos: List[str] = []
    for item in root.findall(".//item"):
        titulo = item.findtext("title")
        if titulo and titulo.strip():
            # Google News anexa " - Fonte" ao título; mantemos só a manchete.
            limpo = titulo.rsplit(" - ", 1)[0].strip()
            titulos.append(limpo)
        if len(titulos) >= limit:
            break
    return titulos


async def get_top_news(limit: int = 5) -> List[str]:
    """
    Retorna as principais manchetes do momento (pt-BR).

    Args:
        limit: Número máximo de manchetes.

    Returns:
        Lista de títulos. Lista vazia em caso de falha.
    """
    try:
        return await asyncio.to_thread(_fetch_sync, limit)
    except Exception as exc:
        logger.warning(f"[NEWS] erro ao consultar RSS: {type(exc).__name__}: {exc}")
        return []
