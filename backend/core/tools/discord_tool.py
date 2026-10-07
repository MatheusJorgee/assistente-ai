"""
DiscordTool — triagem leve do Discord.

O app de desktop do Discord (e a aba no navegador) coloca um contador entre
parênteses no TÍTULO da janela quando há menções ou DMs não lidas — ex.:
"(3) Discord | #geral". Lemos esse contador via EnumWindows (ctypes), o que
funciona com o app desktop SEM precisar de bot token, scraping de DOM ou CDP.

Não lê conteúdo de mensagem — só sinaliza QUANTAS notificações diretas
(menções/DMs) estão pendentes, que é o que importa pra triagem.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import re
import sys
from typing import Any, Dict, List

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

logger = get_logger(__name__)


def _janelas_discord_sync() -> List[Dict[str, Any]]:
    """Enumera janelas do Discord e extrai título + contador de notificações."""
    if sys.platform != "win32":
        return []

    user32 = ctypes.windll.user32
    resultados: List[Dict[str, Any]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            titulo = buf.value or ""
            # Janela do Discord tem "Discord" no título (app e web na maioria dos casos)
            if "discord" not in titulo.lower():
                return True
            m = re.match(r"^\((\d+)\)", titulo.strip())
            contador = int(m.group(1)) if m else 0
            resultados.append({"titulo": titulo, "nao_lidas": contador})
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(_callback), 0)
    except Exception as exc:
        logger.debug(f"[DISCORD] EnumWindows falhou: {exc}")
    return resultados


class DiscordTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="discord",
                description=(
                    "Triagem do Discord: diz se há menções ou DMs não lidas esperando "
                    "(lê o contador de notificações da janela do Discord). Use quando ele "
                    "perguntar se tem algo no Discord, ou pra checar pendências. Não lê o "
                    "conteúdo das mensagens — só sinaliza quantas notificações diretas há. "
                    "Requer o Discord aberto (app ou aba)."
                ),
                category="communication",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="Apenas 'verificar' (checa notificações pendentes).",
                        required=False,
                        default="verificar",
                        choices=["verificar"],
                    ),
                ],
                examples=["acao=verificar"],
                security_level=SecurityLevel.LOW,
                tags=["discord", "triagem", "notificacoes"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        janelas = await asyncio.to_thread(_janelas_discord_sync)
        if not janelas:
            return json.dumps(
                {"ok": True, "aberto": False, "msg": "O Discord não está aberto agora (nenhuma janela encontrada)."},
                ensure_ascii=False,
            )
        total = max((j["nao_lidas"] for j in janelas), default=0)
        if total <= 0:
            return json.dumps(
                {"ok": True, "aberto": True, "nao_lidas": 0, "msg": "Discord aberto, mas sem menções ou DMs pendentes."},
                ensure_ascii=False,
            )
        return json.dumps(
            {"ok": True, "aberto": True, "nao_lidas": total,
             "msg": f"Tem {total} notificação(ões) direta(s) (menção/DM) te esperando no Discord."},
            ensure_ascii=False,
        )
