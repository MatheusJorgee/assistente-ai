"""
BRAIN ROUTER - WebSocket /ws/quinta
===================================

REGRA DE OURO: Este arquivo contém APENAS transporte. Zero lógica de negócio.

Fluxo (sem bloqueios):
1. Receber JSON do cliente
2. Validar e parsear para DTO
3. Despachar task assíncrona para Brain.ask()
4. Enquanto Brain processa, emitir status intermediário
5. Retornar resultado final

Desacoplamento Crítico:
- Brain não sabe que existe WebSocket
- Brain não sabe que existe Frontend
- Apenas: dados entram → função assíncrona → resultado sai
- Todas as comunicações são via MessageEnvelope (DTOs)

Por que sem bloqueios?
- Python asyncio tem UM event loop por thread
- Se uma coroutine bloqueia (sleep, file read, network), TODA a app bloqueia
- Solução: TUDO tem que ser await-able
  - Brain.ask() → retorna Task[BrainResponse] (não bloqueia)
  - Não fazemos: result = brain.ask() # bloqueia!
  - Fazemos: result = await brain.ask() # não bloqueia, event loop executa outras tasks

Comentários no código mostram como evitar bloqueios.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

try:
    from .dtos import (
        MessageEnvelope,
        MessageType,
        MessageFactory,
        ErrorCode,
        validate_message_envelope,
        validate_user_message_input,
    )
    from .connection_manager import get_connection_manager
except ImportError:
    from .dtos import (
        MessageEnvelope,
        MessageType,
        MessageFactory,
        ErrorCode,
        validate_message_envelope,
        validate_user_message_input,
    )
    from .connection_manager import get_connection_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["Brain Communication"])


# ===== HELPERS SEM LÓGICA DE NEGÓCIO =====

async def emit_status(
    manager,
    session_id: str,
    step: str,
    progress: float = 0.0,
    request_id: Optional[str] = None,
) -> None:
    """
    Helper para enviar status intermediário sem lógica.
    
    Por que helper?
    - Reutilizável entre múltiplas rotas
    - Centraliza a formatação de status
    - Facilita testes
    """
    status_msg = MessageFactory.create_intermediate_status(
        step=step,
        progress=progress,
        request_id=request_id,
    )
    
    # Sem await! emit_status é assíncrono mas chamador não bloqueado
    await manager.send_to_client(session_id, status_msg.dict())


async def emit_error(
    manager,
    session_id: str,
    error_code: ErrorCode,
    message: str,
    request_id: Optional[str] = None,
) -> None:
    """Helper para enviar erro sem lógica."""
    error_msg = MessageFactory.create_error(
        error_code=error_code,
        message=message,
        request_id=request_id,
    )
    
    await manager.send_to_client(session_id, error_msg.dict())


# ===== ROTA PRINCIPAL: /ws/quinta =====

@router.websocket("/quinta")
async def websocket_brain_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint para comunicação com Brain.
    
    REGRA DE OURO: Este handler deve focar APENAS em:
    1. Aceitar conexão
    2. Receber JSON em loop
    3. Validar e parsear para DTO
    4. Chamar Brain.ask() via await (NÃO bloqueia)
    5. Emitir status intermediário
    6. Retornar resultado
    7. Tratar desconexões
    
    NÃO DEVE:
    - Conter lógica de IA ou tomada de decisão
    - Fazer I/O bloqueante (file read, network call síncrono)
    - Transformar dados (isso é responsabilidade do Brain)
    - Validação complexa (DTOs fazem isso)
    
    ===== POR QUE NEM SEMPRE TEMOS await? =====
    Em Python async/await, nem toda função precisa de await:
    - await: aguarda resultado (libera event loop)
    - send_json(): método assíncrono do WebSocket, SEMPRE precisa await
    - receive_json(): método assíncrono do WebSocket, SEMPRE precisa await
    - manager.send_to_client(): assíncrono, SEMPRE precisa await
    - brain.ask(): função assíncrona, SEMPRE precisa await (se retorna coroutine)
    
    Regra simples: se é uma função assíncrona (async def), precisa await.
    """
    
    # 1. Obter dependências da aplicação
    manager = get_connection_manager()
    brain = getattr(websocket.app.state, "brain", None)
    event_bus = getattr(websocket.app.state, "autonomous_event_bus", None)
    
    # 2. Validação: Brain deve estar disponível
    if not brain:
        await websocket.accept()
        await emit_error(
            manager,
            "unknown",  # Ainda não temos session_id
            ErrorCode.SERVICE_UNAVAILABLE,
            "Brain não disponível no servidor",
        )
        await websocket.close(code=1011)
        return
    
    # 3. Registrar clientes e obter session_id
    session_id = await manager.connect(websocket, tags={"brain_command"})
    logger.info(f"[Brain Router] Cliente {session_id} conectado à rota /ws/quinta")
    
    try:
        # 4. LOOP PRINCIPAL: receber e processar mensagens
        while True:
            # RECEIVE (bloqueia até mensagem chegar, mas libera event loop)
            # Não é um "bloqueio negativo": o event loop executa outras tasks
            raw_json = await websocket.receive_json()
            
            # PARSE E VALIDAÇÃO (SEM LÓGICA DE IA)
            try:
                envelope = validate_message_envelope(raw_json)
            except ValueError as e:
                await emit_error(
                    manager,
                    session_id,
                    ErrorCode.JSON_PARSE_ERROR,
                    f"JSON inválido: {str(e)}",
                )
                continue
            
            # REQUEST_ID para correlacionar request/response
            request_id = envelope.request_id
            
            # ===== DESPACHO POR TIPO DE MENSAGEM (NEM SEMPRE CHAMA BRAIN) =====
            
            if envelope.type == MessageType.PING:
                # PING/PONG: Sem lógica, apenas reflexo
                pong_msg = MessageFactory.create_pong(request_id=request_id)
                await manager.send_to_client(session_id, pong_msg.dict())
                continue
            
            elif envelope.type == MessageType.USER_MESSAGE:
                # MENSAGEM DO USUÁRIO: Processa com Brain
                
                try:
                    user_input = validate_user_message_input(envelope)
                except ValueError as e:
                    await emit_error(
                        manager,
                        session_id,
                        ErrorCode.INVALID_INPUT,
                        f"Payload inválido: {str(e)}",
                        request_id=request_id,
                    )
                    continue
                
                # ===== EMITIR STATUS: "PENSANDO" =====
                # Sem await aqui? Errado! É assíncrono, sempre precisa await!
                await emit_status(
                    manager,
                    session_id,
                    step="thinking",
                    progress=0.0,
                    request_id=request_id,
                )
                
                # ===== CHAMAR BRAIN (ASSÍNCRONO, SEM BLOQUEIO) =====
                # Importante: brain.ask() é async def, retorna coroutine
                # asyncio.create_task() empacota em Task (não bloqueia)
                # await espera resultado (libera event loop para outras tasks)
                try:
                    # Publicar evento de comando manual no EventBus (se disponível)
                    if event_bus:
                        await event_bus.publish({
                            "type": "manual_command_requested",
                            "payload": {"text": user_input.text},
                            "source": "frontend_websocket",
                        })
                    
                    # ===== AWAITAR BRAIN (PONTO CRÍTICO) =====
                    # Por QUE await? brain.ask() retorna uma coroutine que:
                    # 1. Pode fazer chamadas assíncronas (network, file, etc)
                    # 2. Pode ser cancelada
                    # 3. Precisa de controle de timeouts
                    # await brain.ask() não bloqueia! O event loop executa outras tasks
                    brain_response = await brain.ask(
                        message=user_input.text,
                        image_data=None,
                        include_vision=False
                    )
                    
                    # ===== EMITIR STATUS: "PROCESSADO" =====
                    await emit_status(
                        manager,
                        session_id,
                        step="processing",
                        progress=0.5,
                        request_id=request_id,
                    )
                    
                    # ===== RETORNAR RESPOSTA DO BRAIN =====
                    # brain_response é um BrainResponse object, não dict
                    response_msg = MessageFactory.create_brain_response(
                        text=brain_response.text,
                        tools_used=[],
                        execution_time_ms=0,
                        request_id=request_id,
                    )
                    
                    await manager.send_to_client(session_id, response_msg.dict())
                    
                    logger.info(
                        f"[Brain Router] Resposta enviada para {session_id} "
                        f"({len(response_msg.payload.get('text', ''))} chars)"
                    )
                    
                except asyncio.TimeoutError:
                    await emit_error(
                        manager,
                        session_id,
                        ErrorCode.TIMEOUT,
                        "Brain demorou muito tempo para responder",
                        request_id=request_id,
                    )
                
                except Exception as e:
                    logger.error(f"[Brain Router] Erro ao processar: {e}", exc_info=True)
                    await emit_error(
                        manager,
                        session_id,
                        ErrorCode.INTERNAL_ERROR,
                        f"Erro interno: {str(e)[:100]}",
                        request_id=request_id,
                    )
            
            else:
                # Tipo de mensagem desconhecido
                await emit_error(
                    manager,
                    session_id,
                    ErrorCode.UNKNOWN_MESSAGE_TYPE,
                    f"Tipo de mensagem não suportado: {envelope.type}",
                    request_id=request_id,
                )
    
    except WebSocketDisconnect:
        logger.info(f"[Brain Router] Cliente {session_id} desconectou normalmente")
        await manager.disconnect(session_id)
    
    except Exception as e:
        logger.error(
            f"[Brain Router] Erro não tratado para {session_id}: {e}",
            exc_info=True
        )
        await manager.disconnect(session_id)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass  # WebSocket já pode estar fechado


# ===== ROTAS AUXILIARES (NÃO SÃO WebSocket) =====

@router.get("/health")
async def health_check():
    """
    Verifica saúde do Brain Router.
    
    Retorna:
    - WebSocket connections ativas
    - Status do Brain
    """
    manager = get_connection_manager()
    brain = None  # Pega de app.state se necessário
    
    stats = await manager.get_stats()
    
    return {
        "service": "brain_router",
        "status": "healthy",
        "websocket_connections": stats["active_clients"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/stats")
async def connection_stats():
    """Retorna estatísticas de conexão."""
    manager = get_connection_manager()
    stats = await manager.get_stats()
    return stats
