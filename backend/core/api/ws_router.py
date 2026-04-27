"""
Router WebSocket de observabilidade em tempo real.

Implementa o padrao WebSocket Pub/Sub Bridge (Observer Pattern):

  [Brain/ActionOrchestrator] -> AsyncEventBus
                                    |
                       gateway_manager.WebSocketEventBridge
                       (converte LoopEvent -> JSON formatado)
                                    |
                       EnhancedConnectionManager
                       (filtra + broadcast para clientes)
                                    |
                             [Next.js Frontend]

O desacoplamento e fundamental:
- Brain nao sabe que existe frontend
- ActionOrchestrator nao sabe que existe WebSocket
- WebSocket nao conhece a logica de negocio
- Toda comunicacao e via AsyncEventBus (Pub/Sub puro)

IMPORTANTE: Use EnhancedConnectionManager do gateway_manager!
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
try:
    from .. import get_logger
except ImportError:
    from .. import get_logger
try:
    from ..loop import AsyncEventBus, LoopEvent
except ImportError:
    from ..loop import AsyncEventBus, LoopEvent

from .gateway_manager import (
    EnhancedConnectionManager,
    EventPayloadFormatter,
    EventFilter,
    WebSocketEventBridge,
)

EventHandler = Callable[[LoopEvent], Awaitable[None] | None]
logger = get_logger(__name__)


class ConnectionManager:
    """Gerencia múltiplas conexões WebSocket de observabilidade."""

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
manager = EnhancedConnectionManager()  # EnhancedConnectionManager do gateway_manager

# Sera inicializado em main.py quando FastAPI app inicia
ws_bridge: Optional[WebSocketEventBridge] = None


def get_ws_bridge() -> Optional[WebSocketEventBridge]:
    """Retorna a instancia global do bridge WebSocket (None se nao inicializado)."""
    return ws_bridge


async def init_ws_bridge(event_bus: AsyncEventBus) -> None:
    """Inicializa o bridge WebSocket (chamar uma vez ao iniciar)."""
    global ws_bridge
    ws_bridge = WebSocketEventBridge(event_bus, manager=manager)
    await ws_bridge.start()
    logger.info("[WS Router] Bridge WebSocket inicializado")


async def stop_ws_bridge() -> None:
    """Para o bridge WebSocket (chamar no shutdown)."""
    global ws_bridge
    if ws_bridge:
        await ws_bridge.stop()
        ws_bridge = None
        logger.info("[WS Router] Bridge WebSocket parado")


class AutonomousControlRequest(BaseModel):
    paused: bool


@router.post("/autonomous/control")
async def control_autonomous_loop(payload: AutonomousControlRequest, request: Request):
    app_state = getattr(request.app, "state", None)
    worker = getattr(app_state, "autonomous_worker", None) if app_state else None
    if not worker:
        raise HTTPException(status_code=503, detail="Autonomous worker indisponível")

    if payload.paused:
        await worker.pause()
    else:
        await worker.resume()

    return {"ok": True, "paused": bool(getattr(worker, "is_paused", False))}


@router.websocket("/ws")
async def events_websocket(websocket: WebSocket) -> None:
    """
    WebSocket handler para observabilidade em tempo real.

    O cliente se conecta e recebe eventos do AsyncEventBus formatados como JSON.
    Tambem pode enviar comandos manuais (manual_command) ou controlar o loop autonomo.

    Protocolos aceitos:
    - Entrada do cliente:
      {"type": "manual_command", "command": "texto do comando"}
      {"type": "autonomous_control", "paused": true/false}
      "ping"

    - Saida para cliente:
      Eventos do EventBus formatados por EventPayloadFormatter
      {"type": "error", ...}
      {"type": "connection", "status": "connected", ...}
      {"type": "pong"}
    """
    # Resolve dependencias da app
    event_bus = getattr(websocket.app.state, "autonomous_event_bus", None)
    worker = getattr(websocket.app.state, "autonomous_worker", None)

    # Validacao: event_bus deve estar inicializado
    if not isinstance(event_bus, AsyncEventBus):
        await websocket.accept()
        error_payload = EventPayloadFormatter.format_error(
            "Event bus nao inicializado",
            error_code="SERVICE_UNAVAILABLE",
        )
        await websocket.send_json(error_payload)
        await websocket.close(code=1011)
        return

    # Registra cliente no manager
    client_id = await manager.connect(websocket)
    logger.info(f"[WS] Cliente {client_id} conectado")

    # Rastreia tarefas em voo (comandos em processamento)
    in_flight_commands: set[asyncio.Task[Any]] = set()

    async def handle_manual_command(command: str, request_id: str) -> None:
        """Publica manual_command_requested no barramento e finaliza."""
        command = command.strip()
        if not command:
            await manager.send_json(
                client_id,
                EventPayloadFormatter.format_error(
                    "Comando vazio",
                    error_code="INVALID_INPUT",
                    event_id=request_id,
                ),
            )
            return

        await event_bus.publish(
            LoopEvent(
                type="manual_command_requested",
                payload={"command": command, "client_id": client_id, "request_id": request_id},
                source="frontend_terminal",
            )
        )

    try:
        # Envia status de conexao
        connection_status = EventPayloadFormatter.format_connection_status(
            status="connected",
            client_id=client_id,
            active_clients=await manager.active_count(),
            autonomous_paused=bool(getattr(worker, "is_paused", False)),
        )
        await manager.send_json(client_id, connection_status)

        # Loop principal: recebe mensagens do cliente
        while True:
            raw_message = await websocket.receive_text()
            if not raw_message:
                continue

            # Ping/Pong keep-alive
            if raw_message.lower() == "ping":
                pong_payload = EventPayloadFormatter.format_pong()
                await manager.send_json(client_id, pong_payload)
                continue

            # Parse JSON
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                error_payload = EventPayloadFormatter.format_error(
                    "JSON invalido",
                    error_code="PARSE_ERROR",
                )
                await manager.send_json(client_id, error_payload)
                continue

            msg_type = str(message.get("type", "")).strip()

            # Comando manual do frontend
            if msg_type == "manual_command":
                command_text = str(message.get("command", "")).strip()
                request_id = str(message.get("request_id", str(uuid.uuid4())))

                task = asyncio.create_task(
                    handle_manual_command(command_text, request_id)
                )
                in_flight_commands.add(task)
                task.add_done_callback(in_flight_commands.discard)
                continue

            # Controle do worker autonomo
            if msg_type == "autonomous_control":
                should_pause = bool(message.get("paused", False))
                if worker is None:
                    error_payload = EventPayloadFormatter.format_error(
                        "Autonomous worker indisponivel",
                        error_code="SERVICE_UNAVAILABLE",
                    )
                    await manager.send_json(client_id, error_payload)
                    continue

                try:
                    if should_pause:
                        await worker.pause()
                    else:
                        await worker.resume()

                    # Publica evento
                    await event_bus.publish(
                        LoopEvent(
                            type="autonomous_control_changed",
                            payload={
                                "paused": bool(getattr(worker, "is_paused", False))
                            },
                            source="frontend_terminal",
                        )
                    )

                    # Confirmacao
                    ack_payload = EventPayloadFormatter.format_event(
                        LoopEvent(
                            type="autonomous_control_ack",
                            payload={
                                "paused": bool(getattr(worker, "is_paused", False))
                            },
                        )
                    )
                    await manager.send_json(client_id, ack_payload)
                except Exception as exc:
                    logger.warning(f"[WS] Erro ao controlar worker: {exc}")
                    error_payload = EventPayloadFormatter.format_error(
                        f"Erro ao controlar worker: {exc}",
                        error_code="CONTROL_ERROR",
                    )
                    await manager.send_json(client_id, error_payload)
                continue

            # Tipo de mensagem nao suportado
            error_payload = EventPayloadFormatter.format_error(
                f"Tipo de mensagem nao suportado: {msg_type}",
                error_code="UNSUPPORTED_MESSAGE",
            )
            await manager.send_json(client_id, error_payload)

    except WebSocketDisconnect:
        logger.debug(f"[WS] Cliente {client_id} desconectado (WebSocketDisconnect)")
    except Exception as exc:
        logger.warning(f"[WS] Erro inesperado para cliente {client_id}: {exc}")
    finally:
        # Aguarda tarefas em voo
        if in_flight_commands:
            logger.debug(f"[WS] Aguardando {len(in_flight_commands)} tarefas em voo para {client_id}")
            await asyncio.gather(*in_flight_commands, return_exceptions=True)

        # Remove cliente do manager
        await manager.disconnect(client_id)
        logger.info(f"[WS] Cliente {client_id} removing completo")


