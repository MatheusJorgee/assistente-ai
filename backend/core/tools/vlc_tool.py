"""
VLCTool — controla o VLC Media Player via HTTP API (rede local).

Diferença em relação ao MediaTool existente:
  - MediaTool usa simulação de teclas (win32/sendkeys) — frágil, local only
  - VLCTool usa HTTP API do VLC — robusto, funciona em LAN e loopback

Pré-requisito no VLC:
  Ferramentas → Preferências → Tudo → Interface → Main interfaces → Web
  Porta padrão: 8080. Definir senha em: Interface → Main interfaces → Lua → Password

Instalar dependência: pip install aiohttp
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Optional

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Adapter de backend — permite trocar a implementação sem mudar a tool
# ---------------------------------------------------------------------------

class VLCBackend(ABC):
    @abstractmethod
    async def request(self, cmd: Optional[str], extra_params: dict) -> dict: ...


class VLCHttpBackend(VLCBackend):
    """Comunica com VLC via HTTP API JSON (localhost ou LAN)."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        password: str = "",
    ) -> None:
        self._url = f"http://{host}:{port}/requests/status.json"
        self._auth = ("", password)

    async def request(self, cmd: Optional[str], extra_params: dict) -> dict:
        try:
            import aiohttp
        except ImportError:
            return {"error": "aiohttp não instalado; execute: pip install aiohttp"}

        params: dict = {}
        if cmd:
            params["command"] = cmd
        params.update(extra_params)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self._url,
                    params=params,
                    auth=aiohttp.BasicAuth(*self._auth),
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    return await resp.json()
        except Exception as exc:
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class VLCTool(MotorTool):
    """Controla o VLC via HTTP API — funciona local e via LAN."""

    _CMD_MAP = {
        "play":     "pl_play",
        "pause":    "pl_pause",
        "next":     "pl_next",
        "previous": "pl_previous",
    }

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        password: str = "",
    ) -> None:
        self._backend: VLCBackend = VLCHttpBackend(host, port, password)
        super().__init__(
            metadata=ToolMetadata(
                name="vlc_control",
                description=(
                    "Controla o VLC Media Player via HTTP API na rede local. "
                    "Suporta play, pause, próxima faixa, faixa anterior, volume e status."
                ),
                category="media",
                parameters=[
                    ToolParameter(
                        name="action",
                        type="string",
                        description=(
                            "Ação a executar: play, pause, next, previous, "
                            "volume_set ou get_status."
                        ),
                        required=True,
                        choices=["play", "pause", "next", "previous", "volume_set", "get_status"],
                    ),
                    ToolParameter(
                        name="value",
                        type="int",
                        description="Para volume_set: valor entre 0 e 100.",
                        required=False,
                        default=None,
                    ),
                ],
                examples=[
                    'action="play"',
                    'action="volume_set", value=60',
                    'action="get_status"',
                ],
                security_level=SecurityLevel.LOW,
                tags=["media", "vlc", "network", "local"],
            )
        )

    def inject_backend(self, backend: VLCBackend) -> None:
        """Permite substituir o backend (útil em testes)."""
        self._backend = backend

    def validate_input(self, **kwargs) -> bool:
        action = str(kwargs.get("action", "")).lower()
        valid = {"play", "pause", "next", "previous", "volume_set", "get_status"}
        if action not in valid:
            return False
        if action == "volume_set":
            v = kwargs.get("value")
            return isinstance(v, (int, float)) and 0 <= int(v) <= 100
        return True

    async def execute(self, **kwargs) -> str:
        action = str(kwargs["action"]).lower()

        if action == "get_status":
            data = await self._backend.request(cmd=None, extra_params={})
            return json.dumps(self._parse_status(data), ensure_ascii=False)

        if action == "volume_set":
            # VLC usa escala 0–512 (256 = 100%)
            vlc_val = int(int(kwargs["value"]) * 2.56)
            data = await self._backend.request(cmd="volume", extra_params={"val": vlc_val})
        elif action in self._CMD_MAP:
            data = await self._backend.request(cmd=self._CMD_MAP[action], extra_params={})
        else:
            return json.dumps({"ok": False, "error": f"Ação desconhecida: {action}"})

        if "error" in data:
            logger.warning("[VLC] Erro na API: %s", data["error"])
            return json.dumps({"ok": False, "error": data["error"]})

        logger.info("[VLC] Ação executada: %s", action)
        return json.dumps({"ok": True, "action": action, **self._parse_status(data)})

    @staticmethod
    def _parse_status(data: dict) -> dict:
        if "error" in data:
            return {"error": data["error"]}
        return {
            "state": data.get("state", "unknown"),
            "volume": round(data.get("volume", 0) / 2.56),
            "title": (
                data.get("information", {})
                    .get("category", {})
                    .get("meta", {})
                    .get("title", "")
            ),
        }
