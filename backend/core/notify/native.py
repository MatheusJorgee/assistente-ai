"""
Notificação nativa do Windows (toast) — a Quinta-Feira alcança o Matheus mesmo
com o navegador fechado. Best-effort: se winotify não estiver disponível, não faz
nada (o aviso continua na fila do app/voz).
"""

from __future__ import annotations

import asyncio

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)


def _toast_sync(titulo: str, mensagem: str) -> None:
    try:
        from winotify import Notification
        t = Notification(
            app_id="Quinta-Feira",
            title=titulo,
            msg=mensagem[:250],
            duration="short",
        )
        t.show()
    except Exception as exc:
        logger.debug(f"[NOTIFY] toast falhou: {exc}")


async def notificar(titulo: str, mensagem: str) -> None:
    """Mostra um toast nativo do Windows (não bloqueia o event loop)."""
    if not (mensagem or "").strip():
        return
    await asyncio.to_thread(_toast_sync, titulo, mensagem)
