"""
MAIN.PY - Tronco EncefÃ¡lico (Gateway FastAPI)
==============================================

Responsabilidade ÃšNICA:
- Roteador HTTP/WebSocket
- NÃ£o contÃ©m lÃ³gica de IA, visÃ£o ou automaÃ§Ã£o
- Interface entre Frontend (Next.js) e CÃ©rebro (brain/)

PadrÃ£o: Facade (simplifica comunicaÃ§Ã£o)

NÃƒO IMPORTA:
- brain.py / LLM adapters
- automaÃ§Ã£o / tools
- visÃ£o / processamento de imagens
- bancos de dados

IMPORTA APENAS:
- backend.core (config, logger, errors)
- fastapi (web framework)
"""

import asyncio
import sys
import json
import traceback
from typing import Optional, Dict, Any, Set, List
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path

# ===== CONFIGURAÇÃO CRÍTICA: Event Loop no Windows para Playwright =====
# Forçar o Event Loop correto no Windows para suportar subprocessos do Playwright
# Sem isto, Uvicorn força SelectorEventLoop que não suporta subprocess no Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print("[SISTEMA] Windows detectado: PolicyEventLoop ajustado para ProactorEventLoopPolicy")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ===== IMPORTAÃ‡Ã•ES RESILIENTES (funciona de qualquer cwd) =====
try:
    # Tentar importaÃ§Ã£o absoluta (uvicorn backend.main:app do pai)
    from core import (
        ActionOrchestrator,
        AudioAdapter,
        AsyncEventBus,
        AutonomousWorker,
        LoopEvent,
        VoiceCommandOrchestrator,
        WakeWordListener,
        get_config,
        get_logger,
        configure_logging,
        QuintaFeirError,
    )
    from core.memory import MemoryManager
    from brain import QuintaFeiraBrain, BrainResponse
    from core.api import ws_observability_router
    from core.tools import inicializar_ferramentas
    from services import get_database, get_voice_manager
except ImportError:
    # Fallback: importaÃ§Ã£o relativa (uvicorn main:app do backend/)
    from core import (
        ActionOrchestrator,
        AudioAdapter,
        AsyncEventBus,
        AutonomousWorker,
        LoopEvent,
        VoiceCommandOrchestrator,
        WakeWordListener,
        get_config,
        get_logger,
        configure_logging,
        QuintaFeirError,
    )
    from core.memory import MemoryManager
    from brain import QuintaFeiraBrain, BrainResponse
    from core.api import ws_observability_router
    from core.tools import inicializar_ferramentas
    from services import get_database, get_voice_manager

# ===== INICIALIZAR LOGGING E CONFIG =====
config = get_config()
configure_logging(log_level=config.LOG_LEVEL)
logger = get_logger(__name__)

logger.info(f"[GATEWAY] Iniciando Quinta-Feira Gateway v1.0")
logger.info(f"[GATEWAY] Modo: {config.SECURITY_PROFILE}")


# ===== DEPENDÃŠNCIAS GLOBAIS =====
"""
Singletons que serÃ£o inicializados na startup:
- brain: QuintaFeiraBrain (LLM + funcionalidades)
- motor: ToolRegistry (automaÃ§Ã£o)
- database: PersistÃªncia
- voice_manager: SÃ­ntese de voz
"""
brain = None
motor = None
database = None
voice_manager = None
memory_manager = None
autonomous_event_bus = None
autonomous_worker = None
action_orchestrator = None
audio_adapter = None
wake_word_listener = None
voice_command_orchestrator = None


# ===== ESTADO GLOBAL =====
"""
Nota sobre State Management em FastAPI + Async:

O FastAPI roda em uvicorn com mÃºltiplos workers (por padrÃ£o 4).
Cada worker tem seu prÃ³prio event loop e estado Python separado.

Para rastrear sessÃµes WebSocket, usamos:
1. active_sessions: Dict[session_id] â†’ WebSocket connection
2. Lock assÃ­ncrono: para operaÃ§Ãµes thread-safe

Em produÃ§Ã£o com mÃºltiplos workers, considerarÃ­amos:
- Redis para sessÃµes compartilhadas
- Ou um Ãºnico worker mode (--workers 1) para desenvolvimento

Para agora (desenvolvimento local), usamos Dict simples com async Lock.
"""

active_sessions: Dict[str, WebSocket] = {}  # session_id â†’ WebSocket
sessions_lock = asyncio.Lock()  # Protege acesso a active_sessions


# ===== APLICAÃ‡ÃƒO FASTAPI =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia ciclo de vida da aplicaÃ§Ã£o (startup/shutdown).
    
    Context Manager assÃ­ncrono:
    - yield: tudo antes roda na startup
    - tudo depois roda na shutdown
    
    BenefÃ­cio: Garantido executar cleanup mesmo com exceÃ§Ãµes
    """
    global brain, motor, database, voice_manager, memory_manager, autonomous_event_bus, autonomous_worker, action_orchestrator, audio_adapter, wake_word_listener, voice_command_orchestrator
    
    # ===== STARTUP =====
    logger.info("[STARTUP] Quinta-Feira Gateway carregando...")
    logger.info(f"[STARTUP] Frontend esperado em: {config.FRONTEND_URL}")
    logger.info(f"[STARTUP] Security profile: {config.SECURITY_PROFILE}")
    
    try:
        # 1. Inicializar EventBus cedo para receber telemetria desde o bootstrap
        logger.info("[STARTUP] Inicializando EventBus...")
        autonomous_event_bus = AsyncEventBus()
        await autonomous_event_bus.start()
        app.state.autonomous_event_bus = autonomous_event_bus

        def publish_runtime_event(payload: Dict[str, Any]) -> None:
            if autonomous_event_bus and autonomous_event_bus.is_running:
                asyncio.create_task(
                    autonomous_event_bus.publish(
                        LoopEvent(
                            type=str(payload.get("type", "runtime_event")),
                            payload=payload,
                            source="telemetry",
                        )
                    )
                )

        # 2. Inicializar Motor (automaÃ§Ã£o)
        logger.info("[STARTUP] Inicializando Motor...")
        motor = inicializar_ferramentas(event_publisher=publish_runtime_event)
        ferramentas = motor.list_tools()
        logger.info(f"[STARTUP] Motor: {len(ferramentas)} ferramentas registradas")
        
        # 3. Inicializar Database
        logger.info("[STARTUP] Inicializando Database...")
        database = await get_database()
        stats = await database.get_stats()
        logger.info(f"[STARTUP] Database: {stats}")
        
        # 4. Inicializar Voice Manager
        logger.info("[STARTUP] Inicializando Voice Manager...")
        voice_manager = await get_voice_manager()
        logger.info(f"[STARTUP] Voice: {voice_manager.get_active_provider()}")

        # 4.1 Inicializar Memory Manager (longo prazo)
        logger.info("[STARTUP] Inicializando Memory Manager...")
        memory_manager = MemoryManager()
        await memory_manager.initialize()
        app.state.memory_manager = memory_manager
        
        # 5. Inicializar Brain (CORE)
        logger.info("[STARTUP] Inicializando Brain...")
        try:
            from core.gemini_provider import GeminiAdapter
        except ImportError:
            from core.gemini_provider import GeminiAdapter
        brain = QuintaFeiraBrain(
            llm_provider=GeminiAdapter(),
            tool_registry=motor
        )
        app.state.brain = brain
        logger.info(f"[STARTUP] Brain inicializado com LLM: Gemini")

        # 6. Inicializar runtime autÃ´nomo
        logger.info("[STARTUP] Inicializando EventBus + AutonomousWorker...")
        autonomous_worker = AutonomousWorker(
            event_bus=autonomous_event_bus,
            brain=brain,
            memory_manager=memory_manager,
            audit_file=".runtime/audit/host_audit.jsonl",
            tick_interval_seconds=20,
            max_audit_lines=10,
        )
        await autonomous_worker.start()
        app.state.autonomous_worker = autonomous_worker

        action_orchestrator = ActionOrchestrator(
            event_bus=autonomous_event_bus,
            tool_registry=motor,
            brain=brain,
            max_steps=3,
        )
        await action_orchestrator.start()

        # 7. Inicializar stack de Ã¡udio (wake word + voz)
        logger.info("[STARTUP] Inicializando Audio Adapter + Wake Word...")
        audio_adapter = AudioAdapter()
        wake_word_listener = WakeWordListener(
            event_bus=autonomous_event_bus,
            audio_adapter=audio_adapter,
        )
        await wake_word_listener.start()

        voice_command_orchestrator = VoiceCommandOrchestrator(
            event_bus=autonomous_event_bus,
            brain=brain,
            audio_adapter=audio_adapter,
        )
        await voice_command_orchestrator.start()
        app.state.audio_adapter = audio_adapter
        app.state.wake_word_listener = wake_word_listener
        app.state.voice_command_orchestrator = voice_command_orchestrator
        logger.info("[STARTUP] Runtime autÃ´nomo ativo")
        
        logger.info("[STARTUP] âœ“ Gateway PRONTO (Fase 3-6 integrada!)")
    
    except Exception as e:
        logger.error(f"[STARTUP] Erro: {e}", exc_info=True)
        raise
    
    yield  # AplicaÃ§Ã£o roda aqui
    
    # ===== SHUTDOWN =====
    logger.info("[SHUTDOWN] Encerrando Gateway...")

    # Parar runtime autÃ´nomo primeiro (graceful shutdown)
    if autonomous_worker:
        try:
            await autonomous_worker.stop()
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Erro ao parar autonomous worker: {e}")

    if action_orchestrator:
        try:
            await action_orchestrator.stop()
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Erro ao parar action orchestrator: {e}")

    if voice_command_orchestrator:
        try:
            await voice_command_orchestrator.stop()
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Erro ao parar voice orchestrator: {e}")

    if wake_word_listener:
        try:
            await wake_word_listener.stop()
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Erro ao parar wake word listener: {e}")

    if autonomous_event_bus:
        try:
            await autonomous_event_bus.stop()
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Erro ao parar event bus: {e}")
    
    async with sessions_lock:
        # Fechar todas as sessÃµes WebSocket abertas
        closed = 0
        for session_id, websocket in active_sessions.items():
            try:
                await websocket.close(code=1000, reason="Servidor encerrando")
                closed += 1
            except Exception as e:
                logger.warning(f"[SHUTDOWN] Erro ao fechar {session_id}: {e}")
        
        active_sessions.clear()
        logger.info(f"[SHUTDOWN] {closed} sessÃµes fechadas")
    
    logger.info("[SHUTDOWN] âœ“ Gateway encerrado")


app = FastAPI(
    title="Quinta-Feira AI Gateway",
    description="Interface entre Frontend (Next.js) e Core (Brain)",
    version="1.0-gateway",
    lifespan=lifespan  # â† NOVO: gerencia lifecycle
)
app.include_router(ws_observability_router)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    include_vision: bool = False


class CommandRequest(BaseModel):
    """Modelo simples para requisições REST do Frontend"""
    command: str


# ===== MIDDLEWARE: CORS =====
"""
CORS (Cross-Origin Resource Sharing):
Permite que frontend em localhost:3000 acesse backend em localhost:8000.

Sem CORS:
> Navegador bloqueia requisiÃ§Ã£o (SOP - Same Origin Policy)
> TypeError: Failed to fetch

Com CORS:
> Servidor autoriza requisiÃ§Ã£o
> Funciona normalmente
"""

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        config.FRONTEND_URL,  # http://localhost:3000
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== ROTAS REST =====

@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """
    Health Check: Frontend faz ping aqui para verificar se backend estÃ¡ online.
    
    Status Codes:
    - 200 OK: Gateway pronto
    - 503 Service Unavailable: CÃ©rebro ainda nÃ£o inicializado
    
    Resposta:
    {
        "status": "healthy",
        "gateway": "online",
        "timestamp": "2026-04-06T02:30:00.000Z",
        "active_sessions": 0
    }
    """
    try:
        async with sessions_lock:
            num_sessions = len(active_sessions)
        
        return {
            "status": "healthy",
            "gateway": "online",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "active_sessions": num_sessions,
            "version": "1.0-gateway",
            "security_profile": config.SECURITY_PROFILE,
        }
    
    except Exception as e:
        logger.error(f"[HEALTH] Erro: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "gateway": "degraded",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )


@app.get("/api/health", tags=["Health"])
async def api_health() -> Dict[str, Any]:
    """
    Alias do endpoint /health no namespace /api/ para consistência com Frontend.
    
    Usado por: frontend para verificar saúde do backend antes de enviar comandos
    """
    return await health_check()


@app.get("/status", tags=["Status"])
async def status_detail() -> Dict[str, Any]:
    """
    Status detalhado do Gateway e componentes integrados.
    
    Quando o CÃ©rebro estiver pronto, vai reportar:
    - Tools registradas
    - LLM adapter
    - Memory persistida
    """
    async with sessions_lock:
        num_sessions = len(active_sessions)
    
    return {
        "gateway": {
            "status": "ready",
            "version": "1.0-gateway",
        },
        "sessions": {
            "active": num_sessions,
            "max": 100,  # Limite suave
        },
        "config": {
            "security_profile": config.SECURITY_PROFILE,
            "frontend_url": config.FRONTEND_URL,
            "backend_host": config.BACKEND_HOST,
            "backend_port": config.BACKEND_PORT,
        },
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/chat", tags=["Chat"])
async def chat_http(payload: ChatRequest) -> Dict[str, Any]:
    """
    Fallback HTTP para chat quando WebSocket não entrega resposta no frontend.
    
    EXECUTA NO EVENT LOOP PRINCIPAL (sem asyncio.to_thread, sem run_in_executor).
    Todos os awaits diretos para manter compatibilidade com async_playwright.
    """
    logger_instance = get_logger("chat_http")
    
    if not brain:
        logger_instance.error("[CHAT_HTTP] ERRO CRÍTICO: Brain não inicializado")
        raise HTTPException(status_code=503, detail="Brain não inicializado")

    session_id = payload.session_id or f"http_{int(datetime.utcnow().timestamp() * 1000)}"
    message_text = (payload.message or "").strip()

    if not message_text:
        logger_instance.error(f"[CHAT_HTTP] ERRO: Mensagem vazia no session_id={session_id}")
        raise HTTPException(status_code=400, detail="Mensagem vazia")

    logger_instance.info(f"[CHAT_HTTP] Iniciando processamento | session_id={session_id} | comando={message_text[:50]}")

    try:
        await database.add_message(
            session_id=session_id,
            role="user",
            content=message_text,
        )
        logger_instance.debug(f"[CHAT_HTTP] Mensagem do usuário armazenada | session_id={session_id}")

        # ===== EXECUÇÃO NO EVENT LOOP PRINCIPAL =====
        # IMPORTANTE: await direto, sem asyncio.to_thread ou run_in_executor
        # O Playwright precisa do main thread loop
        logger_instance.info(f"[CHAT_HTTP] Chamando brain.ask() | session_id={session_id}")
        
        try:
            brain_response: BrainResponse = await asyncio.wait_for(
                brain.ask(
                    message=message_text,
                    image_data=None,
                    include_vision=payload.include_vision,
                ),
                timeout=30.0,
            )
            logger_instance.info(f"[CHAT_HTTP] Brain respondeu com sucesso | session_id={session_id} | resposta_len={len(brain_response.text)}")
            
        except asyncio.TimeoutError:
            logger_instance.warning(f"[CHAT_HTTP] TIMEOUT: Brain levou >30s para responder | session_id={session_id}")
            return {
                "type": "response",
                "status": "timeout",
                "text": "Estou com lentidao para responder agora. Tente novamente em alguns segundos.",
                "audio": "",
                "mode": "responding",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "session_id": session_id,
            }
        except Exception as e:
            # ===== LOGS AGRESSIVOS: Capturar o ERRO REAL =====
            logger_instance.error(
                f"[CHAT_HTTP] CRITICAL ERROR ao chamar brain.ask():\n"
                f"Session: {session_id}\n"
                f"Comando: {message_text[:100]}\n"
                f"Tipo Erro: {type(e).__name__}\n"
                f"Mensagem: {str(e)}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
            # Re-lançar a exceção para que FastAPI trate adequadamente
            raise HTTPException(status_code=500, detail=f"Erro ao processar comando: {str(e)}")

        # Armazenar resposta no banco de dados
        try:
            await database.add_message(
                session_id=session_id,
                role="assistant",
                content=brain_response.text,
            )
            logger_instance.debug(f"[CHAT_HTTP] Resposta armazenada | session_id={session_id}")
        except Exception as e:
            logger_instance.error(
                f"[CHAT_HTTP] ERRO ao armazenar resposta no DB:\n"
                f"Session: {session_id}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
            # Continuar mesmo se DB falhar - resposta já foi processada

        logger_instance.info(f"[CHAT_HTTP] Processamento completo | session_id={session_id} | status=success")
        
        return {
            "type": "response",
            "status": "success",
            "text": brain_response.text,
            "audio": brain_response.audio or "",
            "mode": brain_response.mode,
            "timestamp": brain_response.timestamp,
            "session_id": session_id,
        }
        
    except HTTPException:
        # Deixar HTTPExceptions passarem (já têm status code apropriado)
        logger_instance.warning(f"[CHAT_HTTP] HTTPException capturada | session_id={session_id}")
        raise
    except Exception as e:
        # ===== CATCH-ALL FINAL: Qualquer erro não esperado =====
        logger_instance.error(
            f"[CHAT_HTTP] UNEXPECTED ERROR (catch-all final):\n"
            f"Session: {session_id}\n"
            f"Tipo Erro: {type(e).__name__}\n"
            f"Mensagem: {str(e)}\n"
            f"Traceback Completo:\n{traceback.format_exc()}"
        )
        raise HTTPException(status_code=500, detail="Erro interno do servidor ao processar comando")


@app.post("/api/chat", tags=["Chat"])
async def api_chat(payload: CommandRequest) -> Dict[str, Any]:
    """
    Endpoint REST para o Frontend (Next.js) no padrão /api/...
    
    Aceita: CommandRequest com campo "command"
    Retorna: { "response": "...", "timestamp": ..., "session_id": ... }
    
    Usado por: frontend/app/page.tsx via fetch POST com { command: "..." }
    """
    # Converte CommandRequest para ChatRequest para reusar lógica
    chat_req = ChatRequest(message=payload.command)
    
    # Chama handler original e reformata resposta para Frontend
    response = await chat_http(chat_req)
    
    # Adapt para resposta esperada pelo Frontend (response, não text)
    return {
        "response": response.get("text", ""),
        "audio": response.get("audio", ""),
        "mode": response.get("mode", "responding"),
        "status": response.get("status", "success"),
        "timestamp": response.get("timestamp"),
        "session_id": response.get("session_id"),
    }


@app.get("/api/logs", tags=["Logs"])
async def get_logs() -> Dict[str, Any]:
    """
    Endpoint de polling para o Frontend recuperar últimos logs do backend.
    
    Usado por: frontend/app/page.tsx (polling GET a cada 2 segundos)
    Resposta: { "logs": ["linha1", "linha2", ...], "status": "ok" }
    """
    try:
        # Tenta ler do arquivo .runtime/logs/backend.log
        log_path = Path(".runtime/logs/backend.log")
        
        if not log_path.exists():
            return {"logs": [], "status": "ok"}
        
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        # Últimas 30 linhas para não sobrecarregar frontend
        recent_logs = [line.rstrip('\n') for line in lines[-30:] if line.strip()]
        
        return {
            "logs": recent_logs,
            "status": "ok",
            "count": len(recent_logs)
        }
    except Exception as e:
        logger_instance = get_logger("api")
        logger_instance.error(f"[API_LOGS] Erro ao ler logs: {e}")
        return {
            "logs": [f"[ERRO] Falha ao ler logs: {str(e)}"],
            "status": "error"
        }

# ===== WEBSOCKET: CONDUÃTE NEURAL =====

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket Endpoint: ConduÃ­te Neural entre Frontend e Brain.
    
    FLUXO:
    1. Cliente conecta â†’ Registra sessÃ£o
    2. Cliente envia JSON â†’ Gateway parseia
    3. Gateway encaminha para Brain (ainda mock)
    4. Brain responde â†’ Gateway retorna JSON ao cliente
    5. Cliente desconecta â†’ Limpa sessÃ£o
    
    TRATAMENTO DE CONCORRÃŠNCIA:
    
    Problema: MÃºltiplas conexÃµes WebSocket simultÃ¢neas podem:
    - Corromper dicionÃ¡rio active_sessions (race condition)
    - Enviar mensagens fora de ordem
    - Deixar sessÃ£o "zumbando" sem cleanup
    
    SoluÃ§Ã£o: Usar asyncio.Lock
    - Lock Ã© adquirido ANTES de modificar active_sessions
    - Liberar IMEDIATAMENTE depois
    - Receber/Enviar SEM lock (nÃ£o Ã© crÃ­tico)
    
    Exemplo de race condition SEM lock:
    > Thread A lÃª: len(active_sessions) = 5
    > Thread B lÃª: len(active_sessions) = 5
    > Thread A escreve: active_sessions[id] = ws â†’ agora 6
    > Thread B nÃ£o viu a alteraÃ§Ã£o de A
    > Estado inconsistente!
    
    Com lock:
    > Thread A adquire: lock.acquire()
    > Thread A lÃª/escreve atomicamente
    > Thread A libera: lock.release()
    > Thread B espera lock ficar disponÃ­vel
    > OrdenaÃ§Ã£o garantida
    """
    
    await websocket.accept()
    
    # Registrar sessÃ£o
    async with sessions_lock:
        active_sessions[session_id] = websocket
    
    logger.info(f"[WS] Conectado: {session_id} (total: {len(active_sessions)})")
    
    try:
        # Enviar confirmaÃ§Ã£o de conexÃ£o
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "session_id": session_id,
            "message": "Gateway ativo. Aguardando cÃ©rebro...",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        
        # ===== LOOP PRINCIPAL =====
        while True:
            # Receber mensagem do cliente (BLOCKING)
            # asyncio libera event loop enquanto aguarda
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=300.0  # 5 minutos antes de desconectar ocioso
                )
            except asyncio.TimeoutError:
                logger.warning(f"[WS] Timeout: {session_id} inativo por 5min")
                await websocket.send_json({
                    "type": "error",
                    "error": "TIMEOUT",
                    "message": "SessÃ£o inativa por muito tempo",
                })
                break
            
            # Parsear mensagem
            try:
                message_text = data.get("message", "").strip()
                include_vision = data.get("include_vision", False)
                
                if not message_text:
                    await websocket.send_json({
                        "type": "error",
                        "error": "EMPTY_MESSAGE",
                        "message": "Mensagem vazia",
                    })
                    continue
                
                logger.info(f"[WS] Recebido de {session_id}: '{message_text[:50]}'...")
                
                # ===== CHAMAR BRAIN REAL =====
                if not brain:
                    raise RuntimeError("Brain nÃ£o inicializado")
                
                # Persistir mensagem em database
                logger.debug(f"[WS] Persistindo mensagem em DB...")
                await database.add_message(
                    session_id=session_id,
                    role="user",
                    content=message_text
                )
                logger.debug(f"[WS] Mensagem persistida")
                
                # Chamar Brain com Motor injetado
                logger.info(f"[WS] Chamando brain.ask() para {session_id}...")
                try:
                    brain_response: BrainResponse = await asyncio.wait_for(
                        brain.ask(
                            message=message_text,
                            image_data=None,
                            include_vision=include_vision
                        ),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    logger.error(f"[WS] Timeout em brain.ask() para {session_id}")
                    await websocket.send_json({
                        "type": "response",
                        "status": "timeout",
                        "text": "Estou com lentidao para responder agora. Tente novamente em alguns segundos.",
                        "audio": "",
                        "mode": "responding",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    })
                    continue
                logger.info(f"[WS] Brain respondeu: {brain_response.text[:50]}...")
                
                # Persistir resposta
                logger.debug(f"[WS] Persistindo resposta em DB...")
                await database.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=brain_response.text
                )
                logger.debug(f"[WS] Resposta persistida")
                
                # Sintetizar voz se disponÃ­vel
                response_audio = ""
                if brain_response.audio:
                    logger.debug(f"[WS] Brain retornou Ã¡udio")
                    response_audio = brain_response.audio
                elif voice_manager:
                    try:
                        logger.debug(f"[WS] Sintetizando voz...")
                        audio_bytes = await voice_manager.synthesize(brain_response.text)
                        import base64
                        response_audio = base64.b64encode(audio_bytes).decode('utf-8')
                        logger.debug(f"[WS] Ãudio sintetizado ({len(audio_bytes)} bytes)")
                    except Exception as e:
                        logger.warning(f"[WS] Erro ao sintetizar voz: {e}")
                else:
                    logger.debug(f"[WS] Sem voice_manager, pulando sÃ­ntese")
                
                # Enviar resposta do Brain
                logger.info(f"[WS] Enviando resposta para {session_id}...")
                await websocket.send_json({
                    "type": "response",
                    "status": "success",
                    "text": brain_response.text,
                    "audio": response_audio,
                    "mode": brain_response.mode,
                    "timestamp": brain_response.timestamp,
                })
                
                logger.info(f"[WS] Respondido a {session_id}")
            
            except json.JSONDecodeError as e:
                logger.error(f"[WS] JSON invÃ¡lido de {session_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": "INVALID_JSON",
                    "message": f"JSON invÃ¡lido: {str(e)}",
                })
            
            except Exception as e:
                logger.error(f"[WS] Erro ao processar: {type(e).__name__}: {e}")
                if isinstance(e, QuintaFeirError):
                    await websocket.send_json(e.to_dict())
                else:
                    await websocket.send_json({
                        "type": "error",
                        "error": "PROCESSING_ERROR",
                        "message": f"Erro interno: {str(e)}",
                    })
    
    except WebSocketDisconnect:
        logger.info(f"[WS] DesconexÃ£o normal: {session_id}")
    
    except Exception as e:
        logger.error(f"[WS] Erro fatal: {session_id}: {type(e).__name__}: {e}")
    
    finally:
        # ===== CLEANUP: ZERAR SESSÃƒO =====
        async with sessions_lock:
            if session_id in active_sessions:
                del active_sessions[session_id]
                logger.info(f"[WS] Limpeza: {session_id} removido (restam: {len(active_sessions)})")


# ===== WEBSOCKET ALIAS: /ws/chat/{session_id} (para compatibilidade com frontend) =====

@app.websocket("/ws/chat/{session_id}")
async def websocket_chat_endpoint(websocket: WebSocket, session_id: str):
    """
    Alias do WebSocket endpoint: redireciona `/ws/chat/{session_id}` para a implementaÃ§Ã£o principal.
    
    MOTIVO: O frontend prÃ³ximo espera este path, mantemos compatibilidade.
    """
    # Delegar para a implementaÃ§Ã£o principal
    return await websocket_endpoint(websocket, session_id)


# ===== MIDDLEWARE DE ERRO GLOBAL (Exception Handler) =====

@app.exception_handler(QuintaFeirError)
async def quintafeira_exception_handler(request, exc: QuintaFeirError):
    """
    Catch de exceÃ§Ãµes do domÃ­nio (ToolNotFoundError, TerminalSecurityError, etc).
    
    Converte para resposta JSON amigÃ¡vel.
    """
    logger.error(f"[ERROR] {exc}")
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """
    Catch global de exceÃ§Ãµes inesperadas.
    
    Em produÃ§Ã£o, logging e monitoramento aqui.
    """
    logger.error(f"[CRITICAL] ExceÃ§Ã£o inesperada: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "Erro interno do servidor",
            "type": type(exc).__name__,
        },
    )


if __name__ == "__main__":
    """
    Para executar localmente (desenvolvimento):
    
    cd backend
    python main.py
    
    Ou com uvicorn (recomendado):
    
    cd backend
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    """
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=config.BACKEND_HOST,
        port=config.BACKEND_PORT,
        reload=True,
        log_level=config.LOG_LEVEL.lower(),
    )

