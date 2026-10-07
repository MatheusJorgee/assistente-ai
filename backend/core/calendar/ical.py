"""
Leitura da Google Agenda via endereço iCal privado (sem OAuth).

O usuário copia o "endereço secreto no formato iCal" das configurações da agenda
(Google Agenda → Configurações da agenda → Integrar agenda) e põe em
CALENDAR_ICS_URL no .env. A partir daí ela LÊ os compromissos — zero OAuth.

Parser leve de VEVENT (sem dependência externa): extrai SUMMARY, DTSTART, DTEND,
LOCATION. Datas convertidas best-effort para horário local.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

import requests

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)


def _unfold(texto: str) -> str:
    """ICS quebra linhas longas com CRLF + espaço — junta de volta."""
    return texto.replace("\r\n ", "").replace("\n ", "").replace("\r\n", "\n")


def _parse_dt(valor: str) -> Optional[datetime]:
    valor = valor.strip()
    try:
        if valor.endswith("Z"):  # UTC → converte pra local
            dt = datetime.strptime(valor, "%Y%m%dT%H%M%SZ")
            # offset local aproximado
            return dt + (datetime.now() - datetime.utcnow())
        if "T" in valor:
            return datetime.strptime(valor[:15], "%Y%m%dT%H%M%S")
        return datetime.strptime(valor[:8], "%Y%m%d")  # só data
    except Exception:
        return None


def _parse_eventos(ics: str) -> List[Dict[str, Any]]:
    texto = _unfold(ics)
    eventos: List[Dict[str, Any]] = []
    for bloco in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", texto, re.DOTALL):
        ev: Dict[str, Any] = {}
        for linha in bloco.splitlines():
            if linha.startswith("SUMMARY"):
                ev["titulo"] = linha.split(":", 1)[-1].strip()
            elif linha.startswith("LOCATION"):
                ev["local"] = linha.split(":", 1)[-1].strip()
            elif linha.startswith("DTSTART"):
                ev["inicio"] = _parse_dt(linha.split(":", 1)[-1])
            elif linha.startswith("DTEND"):
                ev["fim"] = _parse_dt(linha.split(":", 1)[-1])
        if ev.get("titulo") and ev.get("inicio"):
            eventos.append(ev)
    return eventos


def _fetch_sync(url: str) -> str:
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text


async def proximos_eventos(url: str, dias: int = 7, limite: int = 12) -> List[Dict[str, Any]]:
    """Eventos a partir de agora, dentro de `dias`, ordenados."""
    try:
        ics = await asyncio.to_thread(_fetch_sync, url)
    except Exception as exc:
        logger.warning(f"[AGENDA] Falha ao baixar iCal: {exc}")
        return []
    agora = datetime.now()
    limite_dt = agora + timedelta(days=dias)
    futuros = [
        e for e in _parse_eventos(ics)
        if e["inicio"] and agora - timedelta(hours=12) <= e["inicio"] <= limite_dt
    ]
    futuros.sort(key=lambda e: e["inicio"])
    return futuros[:limite]


async def eventos_de_hoje(url: str) -> List[Dict[str, Any]]:
    hoje = date.today()
    todos = await proximos_eventos(url, dias=1, limite=20)
    return [e for e in todos if e["inicio"].date() == hoje]


def formatar(ev: Dict[str, Any]) -> str:
    ini = ev["inicio"]
    quando = ini.strftime("%d/%m %H:%M") if ini.hour or ini.minute else ini.strftime("%d/%m (dia todo)")
    local = f" @ {ev['local']}" if ev.get("local") else ""
    return f"{quando} — {ev['titulo']}{local}"
