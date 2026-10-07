"""
Cotações em tempo real, SEM chave de API.

  - Cripto  → Binance público (BTCUSDT, ETHUSDT, ...)
  - Moedas  → AwesomeAPI (USD-BRL, EUR-BRL, ...)

`cotar(nome)` aceita linguagem natural ("bitcoin", "dólar", "ethereum") e
devolve um dicionário normalizado com preço e variação 24h.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import requests

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

# Nome natural → (tipo, símbolo)
_CRIPTO = {
    "btc": "BTCUSDT", "bitcoin": "BTCUSDT",
    "eth": "ETHUSDT", "ethereum": "ETHUSDT", "ether": "ETHUSDT",
    "sol": "SOLUSDT", "solana": "SOLUSDT",
    "bnb": "BNBUSDT", "xrp": "XRPUSDT", "ripple": "XRPUSDT",
    "ada": "ADAUSDT", "cardano": "ADAUSDT",
    "doge": "DOGEUSDT", "dogecoin": "DOGEUSDT",
    "matic": "MATICUSDT", "polygon": "MATICUSDT",
    "ltc": "LTCUSDT", "litecoin": "LTCUSDT",
    "link": "LINKUSDT", "chainlink": "LINKUSDT",
    "avax": "AVAXUSDT", "avalanche": "AVAXUSDT",
}
_MOEDA = {
    "dolar": "USD-BRL", "dólar": "USD-BRL", "usd": "USD-BRL", "dollar": "USD-BRL",
    "euro": "EUR-BRL", "eur": "EUR-BRL",
    "libra": "GBP-BRL", "gbp": "GBP-BRL",
    "bitcoin-real": "BTC-BRL", "btc-brl": "BTC-BRL",
    "peso": "ARS-BRL", "iene": "JPY-BRL",
}

_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _resolver(nome: str) -> Optional[Dict[str, str]]:
    n = (nome or "").strip().lower()
    if n in _CRIPTO:
        return {"tipo": "cripto", "simbolo": _CRIPTO[n], "nome": nome.strip()}
    if n in _MOEDA:
        return {"tipo": "moeda", "simbolo": _MOEDA[n], "nome": nome.strip()}
    # já veio como símbolo Binance (ex: BTCUSDT) ou par AwesomeAPI (USD-BRL)
    nu = n.upper()
    if nu.endswith("USDT"):
        return {"tipo": "cripto", "simbolo": nu, "nome": nome.strip()}
    if "-" in nu and len(nu) == 7:
        return {"tipo": "moeda", "simbolo": nu, "nome": nome.strip()}
    return None


def _cotar_cripto_sync(simbolo: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": simbolo}, headers=_HEADERS, timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        return {
            "preco": float(d["lastPrice"]),
            "var_pct": float(d["priceChangePercent"]),
            "moeda": "USD",
        }
    except Exception as exc:
        logger.debug(f"[FINANCAS] Binance falhou ({simbolo}): {exc}")
        return None


def _cotar_moeda_sync(simbolo: str) -> Optional[Dict[str, Any]]:
    try:
        cod = simbolo.replace("-", "")
        r = requests.get(
            f"https://economia.awesomeapi.com.br/json/last/{simbolo}",
            headers=_HEADERS, timeout=10,
        )
        r.raise_for_status()
        d = r.json()[cod]
        return {
            "preco": float(d["bid"]),
            "var_pct": float(d["pctChange"]),
            "moeda": "BRL",
        }
    except Exception as exc:
        logger.debug(f"[FINANCAS] AwesomeAPI falhou ({simbolo}): {exc}")
        return None


async def cotar(nome: str) -> Optional[Dict[str, Any]]:
    """Cotação normalizada de um ativo por nome natural. None se desconhecido/falhou."""
    info = _resolver(nome)
    if not info:
        return None
    if info["tipo"] == "cripto":
        dados = await asyncio.to_thread(_cotar_cripto_sync, info["simbolo"])
    else:
        dados = await asyncio.to_thread(_cotar_moeda_sync, info["simbolo"])
    if not dados:
        return None
    return {**info, **dados}


def formatar(cot: Dict[str, Any]) -> str:
    """Linha legível: 'Bitcoin: US$ 63.618,00 (-0,18% em 24h)'."""
    preco = cot["preco"]
    moeda = cot.get("moeda", "")
    simbolo_moeda = "US$" if moeda == "USD" else ("R$" if moeda == "BRL" else "")
    if preco >= 100:
        preco_str = f"{preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        preco_str = f"{preco:.4f}".replace(".", ",")
    var = cot["var_pct"]
    seta = "▲" if var > 0 else ("▼" if var < 0 else "—")
    return f"{cot['nome']}: {simbolo_moeda} {preco_str} ({seta} {var:+.2f}% em 24h)"


def conhece(nome: str) -> bool:
    return _resolver(nome) is not None
