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
    
    # ===== FILA DE MENSAGENS (fora do loop de recepcao) =====
    # O brain.ask pode ficar minutos esperando o Matheus aprovar uma acao critica. Se o
    # loop de recepcao estivesse preso nele, a resposta da aprovacao nunca seria lida.
    # Entao: o loop so RECEBE e enfileira; um trabalhador processa uma mensagem por vez,
    # na ordem (mesma semantica de antes), e o loop segue livre p/ ping e approval_response.
    from ..policy.approvals import com_origem, get_broker

    broker = get_broker()
    for _ev in broker.eventos_pendentes():  # tela que reconecta ve os pedidos ainda abertos
        await manager.send_to_client(session_id, _ev)

    fila_mensagens: asyncio.Queue = asyncio.Queue()

    async def _processar(request_id, user_input) -> None:
        """Processa UMA mensagem do usuario (roda no trabalhador)."""
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
            # Telemetria: registra o comando no EventBus como LoopEvent.
            # NÃO usamos "manual_command_requested" aqui porque esta rota já
            # chama brain.ask() diretamente abaixo — reusar aquele tipo causaria
            # processamento duplicado (ManualCommandHandler chamaria o brain de novo).
            if event_bus:
                try:
                    from ..loop import LoopEvent
                    await event_bus.publish(
                        LoopEvent(
                            type="frontend_message_received",
                            payload={"text": user_input.text},
                            source="frontend_websocket",
                        )
                    )
                except Exception:
                    pass  # telemetria não pode quebrar o fluxo principal

            # ===== AWAITAR BRAIN (PONTO CRÍTICO) =====
            # Por QUE await? brain.ask() retorna uma coroutine que:
            # 1. Pode fazer chamadas assíncronas (network, file, etc)
            # 2. Pode ser cancelada
            # 3. Precisa de controle de timeouts
            # await brain.ask() não bloqueia! O event loop executa outras tasks
            # Timeout: sem ele, um pedido travado deixava o chat pendurado para sempre
            # (o `except asyncio.TimeoutError` abaixo nunca disparava). 300s dá folga ao modo
            # agente (até 16 voltas de tool) E às aprovações (até 60s cada, esperando o Matheus);
            # ajuste em WS_BRAIN_TIMEOUT_SECONDS.
            try:
                from ..config import get_config as _get_config
                _timeout_brain = float(getattr(_get_config(), "WS_BRAIN_TIMEOUT_SECONDS", 300.0))
            except Exception:
                _timeout_brain = 300.0
            # Progresso em tempo real (0.6): o brain avisa "usando X" e "terminei X"; aqui
            # isso vira mensagem para a tela e alimenta `tools_used` da resposta final.
            import time as _t
            from ..runtime_progress import com_progresso

            usadas: list = []
            inicio = _t.time()
            from ..telemetry.traces import Trace
            trace = Trace(request_id)  # B11: tempo por etapa

            async def _progresso(tipo: str, dados: dict) -> None:
                if tipo == "tool_call_start":
                    trace.ferramenta(str(dados.get("tool") or ""))
                elif tipo == "text_delta":
                    trace.marca("primeiro_texto")
                if tipo == "tool_call_start" and dados.get("tool") not in usadas:
                    usadas.append(dados.get("tool"))
                await manager.send_to_client(session_id, {
                    "type": tipo,
                    "payload": dados,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "request_id": request_id,
                })

            with com_progresso(_progresso):
                brain_response = await asyncio.wait_for(
                    brain.ask(
                        message=user_input.text,
                        image_data=None,
                        include_vision=False
                    ),
                    timeout=_timeout_brain,
                )
            
            trace.marca("resposta_final")
            trace.gravar(ok=True)

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
                tools_used=usadas,
                execution_time_ms=int((_t.time() - inicio) * 1000),
                request_id=request_id,
                visor=getattr(brain_response, "visor", None),
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
    

    # PARAR (0.7): `stop` cancela a execucao atual e descarta a fila. A execucao roda numa task
    # propria (`tarefa`) para poder ser cancelada sem derrubar o trabalhador nem a conexao.
    estado_exec: dict = {"task": None, "parar": False}

    async def _executar(request_id, user_input) -> None:
        with com_origem("chat"):
            await _processar(request_id, user_input)

    async def _avisar_parada(descartadas: int) -> None:
        await manager.send_to_client(session_id, {
            "type": "run_cancelled",
            "payload": {"descartadas": descartadas},
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request_id": "stop",
        })

    async def _trabalhador() -> None:
        while True:
            request_id, user_input = await fila_mensagens.get()
            estado_exec["parar"] = False
            tarefa = asyncio.create_task(_executar(request_id, user_input))
            estado_exec["task"] = tarefa
            try:
                await tarefa
            except asyncio.CancelledError:
                if estado_exec["parar"]:
                    # Foi um PARAR do usuario (nao o fim da conexao): avisa a tela e segue.
                    await _avisar_parada(int(estado_exec.get("descartadas", 0)))
                else:
                    tarefa.cancel()
                    raise
            except Exception as exc:
                logger.error(f"[Brain Router] Falha no trabalhador: {exc}", exc_info=True)
            finally:
                estado_exec["task"] = None
                fila_mensagens.task_done()

    trabalhador = asyncio.create_task(_trabalhador())

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
            
            elif envelope.type == MessageType.STOP:
                # PARAR: descarta o que ainda esta na fila E cancela o que esta rodando.
                # Cancelar derruba o brain.ask e qualquer aprovacao pendente (o cartao fecha).
                # Limite honesto: uma tool que JA comecou num thread (ex.: enviar WhatsApp) nao
                # e desfeita; o que para e tudo que viria depois dela.
                descartadas = 0
                while not fila_mensagens.empty():
                    try:
                        fila_mensagens.get_nowait()
                        fila_mensagens.task_done()
                        descartadas += 1
                    except asyncio.QueueEmpty:
                        break
                tarefa_atual = estado_exec["task"]
                if tarefa_atual is not None and not tarefa_atual.done():
                    estado_exec["parar"] = True
                    estado_exec["descartadas"] = descartadas
                    tarefa_atual.cancel()
                else:
                    await _avisar_parada(descartadas)  # nada rodando: a tela so limpa o estado
                logger.info(f"[Brain Router] PARAR pedido por {session_id} (fila descartada: {descartadas})")
                continue

            elif envelope.type == MessageType.VOICE_TRACE:
                # B11: a tela mede quando o 1º audio comecou a tocar
                try:
                    from ..telemetry.traces import registrar_cliente
                    registrar_cliente(str((envelope.payload or {}).get("request_id") or request_id), envelope.payload or {})
                except Exception as exc:
                    logger.debug(f"[Brain Router] voice_trace ignorado: {exc}")
                continue

            elif envelope.type == MessageType.SPOKEN_REPORT:
                # B5: ela foi interrompida; o historico passa a dizer so o que foi falado.
                try:
                    falado = str((envelope.payload or {}).get("falado") or "")[:4000]
                    b = getattr(websocket.app.state, "brain", None)
                    hist = getattr(b, "message_history", None)
                    if hist is not None:
                        hist.registrar_fala_interrompida(falado)
                except Exception as exc:
                    logger.debug(f"[Brain Router] spoken_report ignorado: {exc}")
                continue

            elif envelope.type == MessageType.APPROVAL_RESPONSE:
                # Resposta ao cartao de aprovacao: destrava o gate que esta esperando
                dados = envelope.payload or {}
                if not broker.responder(str(dados.get("approval_id", "")), bool(dados.get("permitido"))):
                    logger.info("[Brain Router] Resposta de aprovacao sem pedido aberto (expirou?)")
                continue

            elif envelope.type == MessageType.USER_MESSAGE:
                # MENSAGEM DO USUÁRIO: Processa com Brain

                # Aprendizado: as falas espontâneas recentes contam como RESPONDIDAS
                try:
                    from ..proactive.reacao import get_reacao
                    get_reacao().usuario_falou()
                except Exception:
                    pass

                # Registra atividade do usuário (usado pelo monitor proativo p/ "pausa")
                try:
                    import time as _time
                    websocket.app.state.last_user_activity = _time.time()
                except Exception:
                    pass

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
                
                # Enfileira: o trabalhador processa em ordem, e este loop continua livre
                # para receber approval_response/ping enquanto o brain espera a aprovacao.
                fila_mensagens.put_nowait((request_id, user_input))
                continue

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
    finally:
        trabalhador.cancel()  # solta o brain e qualquer aprovacao pendente desta sessao


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
