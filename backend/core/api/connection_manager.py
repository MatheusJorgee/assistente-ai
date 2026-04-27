"""
CONNECTION MANAGER (Singleton) - WebSocket Connection Pool
==========================================================

Gerencia TODAS as conexões WebSocket ativas com:
- Tracking de conexões por session_id
- Lidar com desconexões abruptas
- Broadcasting de mensagens para múltiplos clientes
- Sincronização thread-safe via asyncio.Lock

Padrão: Singleton Pattern
- Uma única instância global durante a vida da aplicação
- Inicializado em lifespan do FastAPI
- Acessível via get_connection_manager()

IMPORTANTE: Este é o ÚNICO lugar onde WebSocket connections são gerenciadas.
Não crie novo ConnectionManager em cada rota - use a instância global.
"""

import asyncio
from typing import Dict, Set, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime
from dataclasses import dataclass

from fastapi import WebSocket

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)


@dataclass
class ClientSession:
    """Metadados de uma sessão cliente WebSocket."""
    session_id: str
    websocket: WebSocket
    connected_at: str
    tags: Set[str] = None  # Tags para filtrar broadcasts (ex: {"audio", "commands"})

    def __post_init__(self):
        if self.tags is None:
            self.tags = set()


class ConnectionManager:
    """
    Singleton: gerencia TODAS as conexões WebSocket ativas.
    
    Thread-safety: Usa asyncio.Lock para operações concorrentes.
    
    Responsabilidades:
    1. Registrar novo cliente (connect)
    2. Desregistrar cliente (disconnect)
    3. Enviar mensagem para um cliente específico (send_to_client)
    4. Enviar mensagem para TODOS os clientes (broadcast)
    5. Enviar mensagem para clientes com tags específicas (broadcast_tagged)
    6. Lidar com desconexões abruptas (graceful degradation)
    
    Exemplo de uso:
    ```python
    manager = ConnectionManager()
    
    # Na rota do WebSocket
    try:
        session_id = await manager.connect(websocket)
        while True:
            data = await websocket.receive_json()
            await manager.broadcast({"type": "message", "data": data})
    finally:
        await manager.disconnect(session_id)
    ```
    """

    def __init__(self):
        self._clients: Dict[str, ClientSession] = {}
        self._lock = asyncio.Lock()
        self._stats_connected_total = 0  # Métrica: total histórico de conexões
        self._stats_disconnected_total = 0

    async def connect(self, websocket: WebSocket, tags: Optional[Set[str]] = None) -> str:
        """
        Registra uma nova conexão WebSocket.
        
        Args:
            websocket: Instância WebSocket do FastAPI
            tags: Tags opcionais para categorizar este cliente
                  Ex: {"audio_streaming", "commands"} significam que este cliente
                  recebe eventos com essas tags em broadcasts
        
        Returns:
            session_id (UUID str) do cliente registrado
        
        Side effects:
            - Aceita a conexão WebSocket
            - Registra em _clients
            - Incrementa _stats_connected_total
        """
        await websocket.accept()
        
        session_id = str(uuid4())
        client = ClientSession(
            session_id=session_id,
            websocket=websocket,
            connected_at=datetime.utcnow().isoformat() + "Z",
            tags=tags or set(),
        )
        
        async with self._lock:
            self._clients[session_id] = client
            self._stats_connected_total += 1
        
        logger.info(
            f"[ConnectionManager] Cliente conectado: {session_id} "
            f"(tags: {client.tags}, total: {len(self._clients)})"
        )
        
        return session_id

    async def disconnect(self, session_id: str) -> bool:
        """
        Remove uma conexão WebSocket ativa.
        
        Args:
            session_id: UUID da sessão a desconectar
        
        Returns:
            True se foi desconectado, False se já estava desconectado
        
        Side effects:
            - Remove de _clients
            - Incrementa _stats_disconnected_total
            - Log de desconexão
        """
        async with self._lock:
            if session_id not in self._clients:
                return False
            
            del self._clients[session_id]
            self._stats_disconnected_total += 1
        
        logger.info(
            f"[ConnectionManager] Cliente desconectado: {session_id} "
            f"(total ativo: {len(self._clients)})"
        )
        
        return True

    async def send_to_client(
        self,
        session_id: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Envia mensagem JSON para um cliente específico.
        
        Args:
            session_id: UUID do cliente
            payload: Dict Python (será serializado para JSON)
        
        Returns:
            True se enviado com sucesso, False se cliente não encontrado ou erro
        
        Comportamento em caso de erro:
            - Se websocket.send_json() falhar, desconecta o cliente automaticamente
            - Log de erro (não levanta exceção)
        """
        async with self._lock:
            if session_id not in self._clients:
                logger.warning(
                    f"[ConnectionManager] Tentativa de envio para cliente "
                    f"inexistente: {session_id}"
                )
                return False
            
            client = self._clients[session_id]
        
        try:
            await client.websocket.send_json(payload)
            return True
        except Exception as e:
            # WebSocket foi desconectado ou erro de envio
            logger.warning(
                f"[ConnectionManager] Erro ao enviar para {session_id}: {e}. "
                f"Desconectando."
            )
            await self.disconnect(session_id)
            return False

    async def broadcast(self, payload: Dict[str, Any]) -> int:
        """
        Envia mensagem para TODOS os clientes conectados.
        
        Args:
            payload: Dict Python
        
        Returns:
            Número de clientes que receberam a mensagem com sucesso
        
        Behavior:
            - Itera sobre um snapshot de _clients (thread-safe)
            - Se um cliente falhar, é removido automaticamente
            - Não levanta exceção, mesmo que todos falhem
        """
        # Snapshot para evitar modificação durante iteração
        async with self._lock:
            clients_snapshot = list(self._clients.items())
        
        sent_count = 0
        for session_id, client in clients_snapshot:
            success = await self.send_to_client(session_id, payload)
            if success:
                sent_count += 1
        
        return sent_count

    async def broadcast_tagged(
        self,
        payload: Dict[str, Any],
        tags: Set[str],
        match_all: bool = False,
    ) -> int:
        """
        Envia mensagem apenas para clientes com tags específicas.
        
        Args:
            payload: Dict Python
            tags: Tags para filtrar
            match_all: Se True, cliente deve ter TODAS as tags.
                      Se False, cliente precisa de QUALQUER uma.
        
        Returns:
            Número de clientes que receberam
        
        Exemplo:
            # Enviar apenas para clientes que escutam áudio
            await manager.broadcast_tagged(
                {"type": "audio_event", "data": ...},
                tags={"audio"},
                match_all=False
            )
            
            # Enviar apenas para clientes com AMBOS os tags
            await manager.broadcast_tagged(
                {"type": "special_command"},
                tags={"commands", "admin"},
                match_all=True
            )
        """
        async with self._lock:
            clients_snapshot = list(self._clients.items())
        
        sent_count = 0
        for session_id, client in clients_snapshot:
            # Decidir se cliente deve receber baseado em tags
            if match_all:
                # Cliente precisa ter TODAS as tags da query
                matches = tags.issubset(client.tags)
            else:
                # Cliente precisa ter QUALQUER tag da query
                matches = bool(tags & client.tags)
            
            if matches:
                success = await self.send_to_client(session_id, payload)
                if success:
                    sent_count += 1
        
        return sent_count

    async def get_active_clients(self) -> int:
        """Retorna número de clientes ativos."""
        async with self._lock:
            return len(self._clients)

    async def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de conexão."""
        async with self._lock:
            return {
                "active_clients": len(self._clients),
                "total_connected": self._stats_connected_total,
                "total_disconnected": self._stats_disconnected_total,
            }

    async def close_all(self) -> None:
        """
        Fecha todas as conexões (usado no shutdown da aplicação).
        
        Itera sobre clientes e fecha cada WebSocket gracefully.
        """
        async with self._lock:
            clients_snapshot = list(self._clients.items())
        
        logger.info(f"[ConnectionManager] Fechando {len(clients_snapshot)} conexões...")
        
        for session_id, client in clients_snapshot:
            try:
                await client.websocket.close(code=1001, reason="Server shutdown")
            except Exception as e:
                logger.warning(f"Erro ao fechar {session_id}: {e}")
            finally:
                await self.disconnect(session_id)


# ===== SINGLETON GLOBAL =====
_global_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """
    Retorna a instância GLOBAL do ConnectionManager (Singleton).
    
    IMPORTANTE: Se não foi inicializado, cria uma nova instância.
    Em produção, deve ser chamado APENAS após lifespan.start() do FastAPI.
    """
    global _global_connection_manager
    if _global_connection_manager is None:
        _global_connection_manager = ConnectionManager()
        logger.info("[ConnectionManager] Singleton inicializado")
    return _global_connection_manager


def init_connection_manager() -> ConnectionManager:
    """
    Força inicialização do ConnectionManager Singleton.
    Chamar uma vez em FastAPI lifespan.
    """
    global _global_connection_manager
    _global_connection_manager = ConnectionManager()
    logger.info("[ConnectionManager] Singleton inicializado via init_connection_manager()")
    return _global_connection_manager
