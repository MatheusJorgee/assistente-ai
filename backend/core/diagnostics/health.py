"""
Health — auto-diagnóstico das integrações da Quinta-Feira.

Checa, sob demanda, se cada subsistema externo está de pé: Gemini (chave +
cliente), WhatsApp (Edge CDP + sessão logada), embeddings, cotações financeiras,
agenda iCal. A ideia é que falha NUNCA seja silenciosa — quando algo quebra
(como o WhatsApp quando o site muda o DOM), isso fica VISÍVEL aqui e o monitor
pode avisar o Matheus.

Cada check retorna: {ok, estado, detalhe}. estado ∈ ok|atencao|erro|desligado.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Any, Dict

try:
    from .. import get_logger, get_config
except ImportError:
    from .. import get_logger, get_config

logger = get_logger(__name__)


def _porta_aberta(host: str, porta: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except Exception:
        return False


async def _check_gemini(config: Any) -> Dict[str, Any]:
    key = getattr(config, "GEMINI_API_KEY", "")
    if not key:
        return {"ok": False, "estado": "erro", "detalhe": "GEMINI_API_KEY ausente no .env"}
    return {"ok": True, "estado": "ok", "detalhe": "Chave presente."}


async def _check_whatsapp() -> Dict[str, Any]:
    if not await asyncio.to_thread(_porta_aberta, "127.0.0.1", 9222):
        return {"ok": False, "estado": "desligado", "detalhe": "Edge (porta 9222) fechado — WhatsApp indisponível até abrir."}
    try:
        from ..tools.whatsapp_tool import _status_whatsapp
        import json as _json
        raw = await asyncio.wait_for(_status_whatsapp(), timeout=30)
        d = _json.loads(raw)
        estado = d.get("estado")
        if estado == "logado":
            return {"ok": True, "estado": "ok", "detalhe": "Sessão logada."}
        if estado == "qr":
            return {"ok": False, "estado": "atencao", "detalhe": "Deslogado — precisa escanear o QR no Edge."}
        return {"ok": False, "estado": "atencao", "detalhe": d.get("detalhe", "Sincronizando.")}
    except Exception as exc:
        return {"ok": False, "estado": "erro", "detalhe": f"Falha ao checar: {str(exc)[:80]}"}


async def _check_embeddings(config: Any) -> Dict[str, Any]:
    if not bool(getattr(config, "EMBEDDINGS_ENABLED", True)):
        return {"ok": True, "estado": "desligado", "detalhe": "Desabilitado por config."}
    try:
        from ..memory.embedding_service import get_embedding_service
        svc = get_embedding_service()
        if not svc:
            return {"ok": False, "estado": "atencao", "detalhe": "Serviço indisponível (sem chave?)."}
        vec = await asyncio.wait_for(svc.embed_query("teste de saúde"), timeout=10)
        if vec:
            return {"ok": True, "estado": "ok", "detalhe": f"Embeddings respondendo ({len(vec)} dims)."}
        return {"ok": False, "estado": "atencao", "detalhe": "Embedding voltou vazio."}
    except Exception as exc:
        return {"ok": False, "estado": "erro", "detalhe": f"Falha: {str(exc)[:80]}"}


async def _check_financas() -> Dict[str, Any]:
    try:
        from ..finance import cotar
        c = await asyncio.wait_for(cotar("bitcoin"), timeout=20)
        if c and c.get("preco"):
            return {"ok": True, "estado": "ok", "detalhe": "Cotações respondendo (Binance)."}
        return {"ok": False, "estado": "atencao", "detalhe": "Cotação voltou vazia."}
    except asyncio.TimeoutError:
        return {"ok": False, "estado": "atencao", "detalhe": "Binance lento agora (>20s) — pode ser rede."}
    except Exception as exc:
        return {"ok": False, "estado": "erro", "detalhe": f"Falha: {str(exc)[:80] or type(exc).__name__}"}


async def _check_agenda(config: Any) -> Dict[str, Any]:
    url = getattr(config, "CALENDAR_ICS_URL", "")
    if not url:
        return {"ok": True, "estado": "desligado", "detalhe": "CALENDAR_ICS_URL não configurada."}
    try:
        from ..calendar import proximos_eventos
        await asyncio.wait_for(proximos_eventos(url, dias=1, limite=1), timeout=12)
        return {"ok": True, "estado": "ok", "detalhe": "iCal acessível."}
    except Exception as exc:
        return {"ok": False, "estado": "erro", "detalhe": f"Falha no iCal: {str(exc)[:80]}"}


async def diagnostico_completo() -> Dict[str, Any]:
    """Roda todos os checks em paralelo e resume."""
    config = get_config()
    nomes = ["gemini", "whatsapp", "embeddings", "financas", "agenda"]
    resultados = await asyncio.gather(
        _check_gemini(config),
        _check_whatsapp(),
        _check_embeddings(config),
        _check_financas(),
        _check_agenda(config),
        return_exceptions=True,
    )
    checks: Dict[str, Any] = {}
    problemas = []
    for nome, res in zip(nomes, resultados):
        if isinstance(res, Exception):
            res = {"ok": False, "estado": "erro", "detalhe": str(res)[:80]}
        checks[nome] = res
        if res.get("estado") in ("erro", "atencao"):
            problemas.append(f"{nome}: {res.get('detalhe', '')}")
    return {
        "ok": all(c.get("ok") for c in checks.values()),
        "checks": checks,
        "problemas": problemas,
    }
