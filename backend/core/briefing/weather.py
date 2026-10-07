"""
Cliente OpenWeather (clima atual) — leve, chamada única no startup.

Usa `requests` em thread (asyncio.to_thread) por consistência e confiabilidade
com o restante do briefing no Windows.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Dict, Any

import requests

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def _fetch_sync(city: str, api_key: str) -> Optional[Dict[str, Any]]:
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric",
        "lang": "pt_br",
    }
    resp = requests.get(_OPENWEATHER_URL, params=params, timeout=10)
    if resp.status_code != 200:
        logger.warning(f"[WEATHER] HTTP {resp.status_code}: {resp.text[:120]}")
        return None

    data = resp.json()
    main = data.get("main", {})
    weather_list = data.get("weather", [])
    descricao = weather_list[0].get("description", "") if weather_list else ""

    return {
        "cidade": data.get("name", city),
        "temp": round(main.get("temp", 0)),
        "sensacao": round(main.get("feels_like", 0)),
        "min": round(main.get("temp_min", 0)),
        "max": round(main.get("temp_max", 0)),
        "descricao": descricao,
        "umidade": main.get("humidity", 0),
    }


async def get_weather(city: str, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Busca o clima atual de uma cidade via OpenWeather.

    Args:
        city: Cidade (ex.: "Sao Paulo,BR")
        api_key: Chave da API OpenWeather

    Returns:
        dict com temp/sensacao/min/max/descricao/umidade, ou None em falha.
    """
    if not api_key:
        logger.warning("[WEATHER] OPENWEATHER_API_KEY ausente — clima indisponível")
        return None

    try:
        return await asyncio.to_thread(_fetch_sync, city, api_key)
    except Exception as exc:
        logger.warning(f"[WEATHER] erro ao consultar OpenWeather: {type(exc).__name__}: {exc}")
        return None
