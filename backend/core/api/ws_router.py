"""
Router WebSocket de observabilidade em tempo real.

Transmite eventos do AsyncEventBus para clientes conectados.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any, Awaitable, Callable, Dict

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
try:
    from core import get_logger
except ImportError:
    from core import get_logger
try:
    from core.loop import AsyncEventBus, LoopEvent
except ImportError:
    from core.loop import AsyncEventBus, LoopEvent


EventHandler = Callable[[LoopEvent], Awaitable[None] | None]
logger = get_logger(__name__)


class ConnectionManager:
    """Gerencia mÃºltiplas conexÃµes WebSocket de observabilidade."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def send_json(self, websocket: WebSocket, payload: Dict[str, Any]) -> None:
        await websocket.send_json(payload)

    async def active_count(self) -> int:
        async with self._lock:
            return len(self._connections)


router = APIRouter(prefix="/runtime/events", tags=["Observability"])
manager = ConnectionManager()


class AutonomousControlRequest(BaseModel):
    paused: bool


@router.post("/autonomous/control")
async def control_autonomous_loop(payload: AutonomousControlRequest, request: Request):
    app_state = getattr(request.app, "state", None)
    worker = getattr(app_state, "autonomous_worker", None) if app_state else None
    if not worker:
        raise HTTPException(status_code=503, detail="Autonomous worker indisponÃ­vel")

    if payload.paused:
        await worker.pause()
    else:
        await worker.resume()

    return {"ok": True, "paused": bool(getattr(worker, "is_paused", False))}


@router.websocket("/ws")
async def events_websocket(websocket: WebSocket) -> None:
    event_bus = getattr(websocket.app.state, "autonomous_event_bus", None)
    brain = getattr(websocket.app.state, "brain", None)
    worker = getattr(websocket.app.state, "autonomous_worker", None)
    if not isinstance(event_bus, AsyncEventBus):
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "message": "Event bus nÃ£o inicializado",
            }
        )
        await websocket.close(code=1011)
        return

    await manager.connect(websocket)

    async def forward_event(event: LoopEvent) -> None:
        payload = {
            "type": "runtime_event",
            "event": asdict(event),
        }
        try:
            await manager.send_json(websocket, payload)
        except Exception:
            # DesconexÃ£o serÃ¡ tratada no finally
            pass

    event_bus.subscribe("*", forward_event)
    in_flight_commands: set[asyncio.Task[Any]] = set()

    async def handle_manual_command(command: str) -> None:
        command = command.strip()
        if not command:
            await manager.send_json(websocket, {"type": "error", "message": "Comando vazio"})
            return

        await event_bus.publish(
            LoopEvent(
                type="manual_command_requested",
                payload={"command": command},
                source="frontend_terminal",
            )
        )

        if not brain:
            await manager.send_json(websocket, {"type": "error", "message": "Brain indisponÃ­vel"})
            return

        try:
            response = await brain.ask(command, include_vision=False)
            response_text = (response.text or "").strip()

            await event_bus.publish(
                LoopEvent(
                    type="manual_command_completed",
                    payload={
                        "command": command,
                        "response": response_text,
                    },
                    source="frontend_terminal",
                )
            )
            await manager.send_json(
                websocket,
                {
                    "type": "command_result",
                    "command": command,
                    "response": response_text,
                },
            )
        except Exception as exc:
            logger.warning(f"[OBS_WS] Falha em comando manual: {exc}")
            await event_bus.publish(
                LoopEvent(
                    type="manual_command_failed",
                    payload={"command": command, "error": str(exc)},
                    source="frontend_terminal",
                )
            )
            await manager.send_json(
                websocket,
                {
                    "type": "error",
                    "message": f"Falha ao executar comando manual: {exc}",
                },
            )

    try:
        await manager.send_json(
            websocket,
            {
                "type": "connection",
                "status": "connected",
                "channel": "runtime_events",
                "active_clients": await manager.active_count(),
                "autonomous_paused": bool(getattr(worker, "is_paused", False)),
            },
        )

        # MantÃ©m conexÃ£o viva e recebe comandos do frontend.
        while True:
            raw_message = await websocket.receive_text()
            if not raw_message:
                continue

            if raw_message.lower() == "ping":
                await manager.send_json(websocket, {"type": "pong"})
                continue

            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await manager.send_json(websocket, {"type": "error", "message": "JSON invÃ¡lido"})
                continue

            msg_type = str(message.get("type", "")).strip()

            if msg_type == "manual_command":
                command_text = str(message.get("command", "")).strip()
                task = asyncio.create_task(handle_manual_command(command_text))
                in_flight_commands.add(task)
                task.add_done_callback(in_flight_commands.discard)
                continue

            if msg_type == "autonomous_control":
                should_pause = bool(message.get("paused", False))
                if worker is None:
                    await manager.send_json(websocket, {"type": "error", "message": "Autonomous worker indisponÃ­vel"})
                    continue

                if should_pause:
                    await worker.pause()
                else:
                    await worker.resume()

                await event_bus.publish(
                    LoopEvent(
                        type="autonomous_control_changed",
                        payload={"paused": bool(getattr(worker, "is_paused", False))},
                        source="frontend_terminal",
                    )
                )
                await manager.send_json(
                    websocket,
                    {
                        "type": "autonomous_control_ack",
                        "paused": bool(getattr(worker, "is_paused", False)),
                    },
                )
                continue

            await manager.send_json(websocket, {"type": "error", "message": "Tipo de mensagem nÃ£o suportado"})
    except WebSocketDisconnect:
        pass
    finally:
        if in_flight_commands:
            await asyncio.gather(*in_flight_commands, return_exceptions=True)
        event_bus.unsubscribe("*", forward_event)
        await manager.disconnect(websocket)

