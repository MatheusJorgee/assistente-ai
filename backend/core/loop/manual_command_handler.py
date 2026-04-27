from __future__ import annotations

from typing import Any

from .event_bus import AsyncEventBus, LoopEvent

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)


class ManualCommandHandler:
    """
    Escuta manual_command_requested, chama o Brain e publica manual_command_completed.
    Desacopla o ws_router de qualquer conhecimento sobre a IA.
    """

    def __init__(self, *, event_bus: AsyncEventBus, brain: Any) -> None:
        self._bus = event_bus
        self._brain = brain
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._bus.subscribe("manual_command_requested", self._on_manual_command)
        logger.info("[ManualCommandHandler] Iniciado")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._bus.unsubscribe("manual_command_requested", self._on_manual_command)
        logger.info("[ManualCommandHandler] Encerrado")

    async def _on_manual_command(self, event: LoopEvent) -> None:
        if not self._running:
            return

        payload = event.payload or {}
        command = str(payload.get("command", "")).strip()
        client_id = str(payload.get("client_id", ""))
        request_id = str(payload.get("request_id", ""))

        if not command:
            return

        try:
            response = await self._brain.ask(command, include_vision=False)
            response_text = (response.text or "").strip()

            await self._bus.publish(
                LoopEvent(
                    type="manual_command_completed",
                    payload={
                        "command": command,
                        "response": response_text,
                        "client_id": client_id,
                        "request_id": request_id,
                    },
                    source="manual_command_handler",
                )
            )

        except Exception as exc:
            logger.warning(f"[ManualCommandHandler] Falha ao processar comando: {exc}")
            await self._bus.publish(
                LoopEvent(
                    type="manual_command_failed",
                    payload={
                        "command": command,
                        "error": str(exc),
                        "client_id": client_id,
                        "request_id": request_id,
                    },
                    source="manual_command_handler",
                )
            )
