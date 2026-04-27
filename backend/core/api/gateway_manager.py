"""
WebSocket Pub/Sub Bridge Gateway - Padrão Observer para real-time frontend.

Desacopla a lógica de negócio (Brain, ActionOrchestrator, PolicyEngine) 
do transporte de comunicação com o frontend (WebSocket).

Fluxo de eventos:
  [Brain/ActionOrchestrator] → AsyncEventBus.publish(event)
                                    ↓
                         EventFilter.should_send(event)
                                    ↓
                         EventPayloadFormatter.format(event)
                                    ↓
                         ConnectionManager.broadcast_json(payload)
                                    ↓
                         [Next.js Frontend] recebe JSON

Padrões utilizados:
  - Observer: ConnectionManager subscriber do AsyncEventBus
  - Adapter: EventPayloadFormatter traduz LoopEvent → WebSocket JSON
  - Chain of Responsibility: EventFilter decide quais eventos enviar
  - Broadcaster: ConnectionManager gerencia múltiplas WebSocket connections
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Set
from datetime import datetime, timezone
import uuid

from fastapi import WebSocket

from ..loop import AsyncEventBus, LoopEvent
from .. import get_logger

logger = get_logger(__name__)


@dataclass
class WebSocketClientMetadata:
    """Metadados de um cliente WebSocket conectado."""

    websocket: WebSocket
    client_id: str = ""  # Identificador único do cliente
    connected_at: str = ""
    subscriptions: Set[str] = None  # Tipos de eventos que este cliente recebe

    def __post_init__(self):
        if not self.client_id:
            self.client_id = str(uuid.uuid4())
        if not self.connected_at:
            self.connected_at = datetime.now(timezone.utc).isoformat()
        if self.subscriptions is None:
            # Por padrão (antes de v2), todos os clientes recebem todos os eventos
            self.subscriptions = set()


class EventFilter:
    """
    Define quais eventos importam para o frontend.

    Reduz ruído: não envia todos os eventos, apenas os críticos.
    Pode ser estendido para filtros por cliente (alguns clientes só querem erros, etc).
    """

    # Eventos considerados "críticos" que sempre vão para o frontend
    ESSENTIAL_EVENTS = {
        # Decisões autônomas
        "autonomous_decision",
        "autonomous_started",
        "autonomous_stopped",
        "autonomous_paused",

        # Resultados de ações
        "action_completed",
        "action_failed",
        "action_started",

        # Violações de segurança/política
        "policy_violation",
        "security_alert",

        # Comandos do terminal remoto
        "manual_command_requested",
        "manual_command_completed",
        "manual_command_failed",

        # Controle do worker autônomo
        "autonomous_control_changed",

        # Observabilidade
        "brain_started_thinking",
        "brain_finished_thinking",

        # Conexão/Desconexão
        "client_connected",
        "client_disconnected",
        "event_bus_error",

        # Mídia delegada ao cliente (YouTube/Audio) - Zero-Trace
        "media_playback_requested",
        "media_playback_stopped",
    }

    @staticmethod
    def should_send(event: LoopEvent, client_subscriptions: Set[str] = None) -> bool:
        """
        Decide se um evento deve ser enviado para o frontend.

        Args:
            event: LoopEvent para avaliar
            client_subscriptions: Se vazio/None, envia eventos essenciais.
                                  Se preenchido, respeita subscrições do cliente.

        Returns:
            True se o evento deve ser enviado, False caso contrário.
        """
        # Se o cliente não tem subscrições explícitas, usa essenciais
        if not client_subscriptions:
            return event.type in EventFilter.ESSENTIAL_EVENTS

        # Caso contrário, verifica se cliente subscreveu a este tipo
        return event.type in client_subscriptions or "*" in client_subscriptions

    @staticmethod
    def get_event_priority(event: LoopEvent) -> int:
        """
        Retorna prioridade de um evento (maior = mais importante).

        Usado para ordenar na fila ou decidir descartar se muitos pendentes.
        """
        priorities = {
            "policy_violation": 100,
            "security_alert": 100,
            "action_failed": 80,
            "autonomous_decision": 70,
            "action_completed": 60,
            "manual_command_*": 50,
            "brain_started_thinking": 40,
            "action_started": 30,
        }

        for pattern, priority in priorities.items():
            if pattern.endswith("*"):
                if event.type.startswith(pattern[:-1]):
                    return priority
            elif event.type == pattern:
                return priority

        return 10  # Prioridade padrão para eventos não-críticos


class EventPayloadFormatter:
    """
    Padroniza LoopEvent → WebSocket JSON.

    Cada tipo de evento tem sua própria formatação, mas todos seguem
    um padrão base:
    {
        "type": "runtime_event",       # Sempre "runtime_event" para diferençar de pings, erros, etc
        "event_type": "autonomous_decision",  # O tipo real do evento
        "event_id": "uuid",            # Para rastreabilidade
        "request_id": "uuid (opcional)",     # Se foi disparado por um comando manual
        "timestamp": "ISO8601",        # Quando aconteceu
        "data": { ... },               # Payload específico do evento
        "source": "system/frontend_terminal/etc",
    }
    """

    @staticmethod
    def format_event(
        event: LoopEvent,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Formata um LoopEvent para envio via WebSocket.

        Args:
            event: LoopEvent a formatar
            request_id: ID do comando que disparou este evento (se aplicável)

        Returns:
            DAta JSON-serializável pronta para websocket.send_json()
        """
        base_payload = {
            "type": "runtime_event",
            "event_type": event.type,
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "source": event.source,
            "priority": EventFilter.get_event_priority(event),
        }

        if request_id:
            base_payload["request_id"] = request_id

        # Adiciona payload específico do evento
        if event.payload:
            base_payload["data"] = event.payload
        else:
            base_payload["data"] = {}

        return base_payload

    @staticmethod
    def format_error(
        message: str,
        error_code: str = "INTERNAL_ERROR",
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Formata uma mensagem de erro para o frontend."""
        return {
            "type": "error",
            "message": message,
            "error_code": error_code,
            "event_id": event_id or str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def format_connection_status(
        status: str,  # "connected" | "disconnected"
        client_id: str,
        active_clients: int,
        autonomous_paused: bool = False,
    ) -> Dict[str, Any]:
        """Formata status de conexão."""
        return {
            "type": "connection",
            "status": status,
            "client_id": client_id,
            "active_clients": active_clients,
            "autonomous_paused": autonomous_paused,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def format_pong() -> Dict[str, Any]:
        """Formata resposta a ping."""
        return {
            "type": "pong",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class EnhancedConnectionManager:
    """
    Gerencia múltiplas conexões WebSocket com suporte a:
    - Metadados por cliente
    - Filtros de evento por cliente (v2+: subscrições)
    - Broadcasting com isolamento de erro (um cliente queue não afeta outros)
    - Correlação request/response via event_id
    """

    def __init__(self) -> None:
        self._clients: Dict[str, WebSocketClientMetadata] = {}
        self._lock = asyncio.Lock()
        self._pending_responses: Dict[str, asyncio.Event] = {}
        self._response_cache: Dict[str, Any] = {}

    async def connect(self, websocket: WebSocket) -> str:
        """
        Registra novo cliente conectado.

        Returns:
            client_id (UUID) do cliente registrado
        """
        await websocket.accept()

        client_meta = WebSocketClientMetadata(websocket=websocket)
        async with self._lock:
            self._clients[client_meta.client_id] = client_meta

        logger.info(f"[WS] Cliente conectado: {client_meta.client_id} (total: {len(self._clients)})")
        return client_meta.client_id

    async def disconnect(self, client_id: str) -> None:
        """Remove cliente desconectado."""
        async with self._lock:
            if client_id in self._clients:
                del self._clients[client_id]

        logger.info(f"[WS] Cliente desconectado: {client_id} (total: {len(self._clients)})")

    async def subscribe_client(self, client_id: str, event_types: Set[str]) -> None:
        """
        Define quais tipos de eventos um cliente recebe.

        Se event_types estiver vazio, cliente recebe apenas ESSENTIAL_EVENTS.
        Se "*" em event_types, cliente recebe todos.
        """
        async with self._lock:
            if client_id in self._clients:
                self._clients[client_id].subscriptions = event_types

    async def send_json(
        self,
        client_id: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Envia JSON para um cliente específico.

        Returns:
            True se enviado, False se cliente desconectou ou erro.
        """
        async with self._lock:
            if client_id not in self._clients:
                return False
            websocket = self._clients[client_id].websocket

        try:
            await websocket.send_json(payload)
            return True
        except RuntimeError as e:
            # Conexão já fechada
            logger.debug(f"[WS] Erro ao enviar para {client_id}: {e}")
            await self.disconnect(client_id)
            return False
        except Exception as e:
            logger.warning(f"[WS] Erro inesperado enviando para {client_id}: {e}")
            return False

    async def broadcast_json(
        self,
        payload: Dict[str, Any],
        exclude_client_id: Optional[str] = None,
    ) -> int:
        """
        Envia JSON para todos os clientes conectados.

        O error de um cliente (desconexão, exception) não afeta outros.

        Args:
            payload: Dados JSON a enviar
            exclude_client_id: Se fornecido, não envia para este cliente

        Returns:
            Número de clientes que receberam a mensagem com sucesso.
        """
        async with self._lock:
            client_ids = [
                cid for cid in self._clients.keys()
                if cid != exclude_client_id
            ]

        sent_count = 0
        for client_id in client_ids:
            if await self.send_json(client_id, payload):
                sent_count += 1

        return sent_count

    async def broadcast_event(
        self,
        event: LoopEvent,
        request_id: Optional[str] = None,
    ) -> int:
        """
        Converte LoopEvent → JSON formatado e faz broadcast respeitando filtros.

        Args:
            event: LoopEvent a transmitir
            request_id: ID do comando (para correlação request/response)

        Returns:
            Número de clientes que receberam a mensagem.
        """
        # Formata evento
        payload = EventPayloadFormatter.format_event(event, request_id=request_id)

        # Faz broadcast para todos que subscrevem este tipo
        sent_count = 0
        for client_id in list(self._clients.keys()):
            subscriptions = self._clients[client_id].subscriptions
            if EventFilter.should_send(event, subscriptions):
                if await self.send_json(client_id, payload):
                    sent_count += 1

        return sent_count

    async def active_count(self) -> int:
        """Retorna número de clientes conectados."""
        async with self._lock:
            return len(self._clients)

    async def get_client_ids(self) -> list[str]:
        """Retorna lista de IDs dos clientes conectados."""
        async with self._lock:
            return list(self._clients.keys())


class WebSocketEventBridge:
    """
    Orquestra a conexão entre AsyncEventBus (interno) e múltiplos clientes WebSocket.

    Responsabilidades:
    - Subscrever em eventos críticos do AsyncEventBus
    - Formatar eventos com EventPayloadFormatter
    - Filtrar eventos com EventFilter
    - Fazer broadcast com EnhancedConnectionManager
    - Correlacionar comandos → respostas

    Uso:
        event_bus = AsyncEventBus()
        bridge = WebSocketEventBridge(event_bus)
        await bridge.start()

        # No handler WebSocket:
        client_id = await bridge.manager.connect(websocket)
        # ... handler code ...
        await bridge.manager.disconnect(client_id)
    """

    def __init__(self, event_bus: AsyncEventBus, manager: Optional[EnhancedConnectionManager] = None) -> None:
        self.event_bus = event_bus
        self.manager = manager or EnhancedConnectionManager()
        self._bridge_tasks: Set[asyncio.Task[Any]] = set()

    async def start(self) -> None:
        """
        Inicia o bridge: inscreve em eventos do AsyncEventBus.

        Chame uma vez ao iniciar a aplicação (após event_bus.start()).
        """
        if not self.event_bus.is_running:
            logger.warning("[Bridge] AsyncEventBus não está rodando!")
            return

        # Inscreve em eventos críticos
        for event_type in EventFilter.ESSENTIAL_EVENTS:
            self.event_bus.subscribe(
                event_type,
                self._on_event,
            )

        logger.info("[Bridge] WebSocket bridge iniciado")

    async def stop(self) -> None:
        """Para o bridge e remove subscrições."""
        for event_type in EventFilter.ESSENTIAL_EVENTS:
            self.event_bus.unsubscribe(event_type, self._on_event)

        # Aguarda tasks pendentes
        if self._bridge_tasks:
            await asyncio.gather(*self._bridge_tasks, return_exceptions=True)

        logger.info("[Bridge] WebSocket bridge parado")

    async def _on_event(self, event: LoopEvent) -> None:
        """
        Callback chamado quando um evento é publicado no AsyncEventBus.

        Aqui fazemos o formato → broadcast.
        """
        try:
            # Se evento foi disparado por comando manual, extrai o request_id
            request_id = event.payload.get("request_id")

            # Faz broadcast
            sent = await self.manager.broadcast_event(event, request_id=request_id)

            if sent == 0:
                logger.debug(f"[Bridge] Evento {event.type} - nenhum cliente conectado")
            else:
                logger.debug(f"[Bridge] Evento {event.type} enviado para {sent} cliente(s)")

        except Exception as e:
            logger.error(f"[Bridge] Erro ao processar evento {event.type}: {e}")

    async def subscribe_to_additional_events(self, event_types: list[str]) -> None:
        """
        Permite adicionar mais eventos além dos ESSENTIAL_EVENTS.

        Útil para observabilidade customizada em algumas deployments.
        """
        for event_type in event_types:
            if event_type not in EventFilter.ESSENTIAL_EVENTS:
                self.event_bus.subscribe(event_type, self._on_event)
                logger.info(f"[Bridge] Subscrito a evento adicional: {event_type}")
