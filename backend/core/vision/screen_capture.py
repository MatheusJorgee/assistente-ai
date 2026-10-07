"""
Captura de tela REAL para a visão da Quinta-Feira.

pyautogui tira o print (instantâneo, invisível); PIL reduz pra no máximo 1600px
de largura e comprime em JPEG — o suficiente pra ela LER a tela (texto, menus,
erros) sem estourar o orçamento de tokens do Gemini.

Retorna bytes JPEG prontos pra ir como imagem inline no prompt.
"""

from __future__ import annotations

import asyncio
import io
from typing import Optional, Tuple

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_MAX_LARGURA = 1600
_JPEG_QUALITY = 70


def _capturar_sync() -> Optional[bytes]:
    try:
        import pyautogui
        from PIL import Image
    except Exception as exc:
        logger.warning(f"[VISÃO] pyautogui/PIL indisponível: {exc}")
        return None

    try:
        img = pyautogui.screenshot()
        if img.width > _MAX_LARGURA:
            nova_alt = int(img.height * _MAX_LARGURA / img.width)
            img = img.resize((_MAX_LARGURA, nova_alt), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
        return buf.getvalue()
    except Exception as exc:
        logger.warning(f"[VISÃO] Falha ao capturar tela: {exc}")
        return None


def _capturar_area_sync(x: int, y: int, largura: int, altura: int) -> Optional[bytes]:
    try:
        import pyautogui
        from PIL import Image  # noqa: F401
    except Exception as exc:
        logger.warning(f"[VISÃO] pyautogui/PIL indisponível: {exc}")
        return None
    try:
        img = pyautogui.screenshot(region=(x, y, largura, altura))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
        return buf.getvalue()
    except Exception as exc:
        logger.warning(f"[VISÃO] Falha ao capturar a área: {exc}")
        return None


async def capturar_area(x: int, y: int, largura: int, altura: int) -> Optional[bytes]:
    """Screenshot de uma região da tela (pixels reais) como JPEG, ou None se falhar."""
    return await asyncio.to_thread(_capturar_area_sync, x, y, largura, altura)


async def capturar_tela() -> Optional[bytes]:
    """Screenshot da tela inteira como JPEG (bytes), ou None se falhar."""
    return await asyncio.to_thread(_capturar_sync)
