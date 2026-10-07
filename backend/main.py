"""
MAIN.PY - Tronco Encefálico (Gateway FastAPI)
==============================================

Responsabilidade ÚNICA:
- Roteador HTTP/WebSocket
- Não contém lógica de IA, visão ou automação
- Interface entre Frontend (Next.js) e Cérebro (brain/)

Padrão: Facade (simplifica comunicação)

NÃO IMPORTA:
- brain.py / LLM adapters
- automação / tools
- visão / processamento de imagens
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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

# ===== IMPORTAÇÕES RESILIENTES (funciona de qualquer cwd) =====
try:
    # Tentar importação absoluta (uvicorn backend.main:app do pai)
    from core import (
        ActionOrchestrator,
        AudioAdapter,
        AsyncEventBus,
        AutonomousWorker,
        LoopEvent,
        ManualCommandHandler,
        VoiceCommandOrchestrator,
        WakeWordListener,
        get_config,
        get_logger,
        configure_logging,
        QuintaFeirError,
    )
    from core.memory import MemoryManager
    from brain import QuintaFeiraBrain, BrainResponse
    from core.api import ws_observability_router, brain_router, init_connection_manager
    from core.tools import inicializar_ferramentas
    from services import get_database, get_voice_manager
except ImportError:
    # Fallback: importação relativa (uvicorn main:app do backend/)
    from core import (
        ActionOrchestrator,
        AudioAdapter,
        AsyncEventBus,
        AutonomousWorker,
        LoopEvent,
        ManualCommandHandler,
        VoiceCommandOrchestrator,
        WakeWordListener,
        get_config,
        get_logger,
        configure_logging,
        QuintaFeirError,
    )
    from core.memory import MemoryManager
    from brain import QuintaFeiraBrain, BrainResponse
    from core.api import ws_observability_router, brain_router, init_connection_manager
    from core.tools import inicializar_ferramentas
    from services import get_database, get_voice_manager

# ===== INICIALIZAR LOGGING E CONFIG =====
config = get_config()
configure_logging(log_level=config.LOG_LEVEL)
logger = get_logger(__name__)

logger.info(f"[GATEWAY] Iniciando Quinta-Feira Gateway v1.0")
logger.info(f"[GATEWAY] Modo: {config.SECURITY_PROFILE}")


# ===== DEPENDÊNCIAS GLOBAIS =====
"""
Singletons que serão inicializados na startup:
- brain: QuintaFeiraBrain (LLM + funcionalidades)
- motor: ToolRegistry (automação)
- database: Persistência
- voice_manager: Síntese de voz
"""
brain = None
motor = None
database = None
voice_manager = None
memory_manager = None
autonomous_event_bus = None
autonomous_worker = None
action_orchestrator = None
manual_command_handler = None
audio_adapter = None
wake_word_listener = None
voice_command_orchestrator = None
proactive_monitor = None
last_user_activity = None  # timestamp da última interação do usuário (para "pausa")


# ===== ESTADO GLOBAL =====
"""
Nota sobre State Management em FastAPI + Async:

O FastAPI roda em uvicorn com múltiplos workers (por padrão 4).
Cada worker tem seu próprio event loop e estado Python separado.

Para rastrear sessões WebSocket, usamos:
1. active_sessions: Dict[session_id] â†' WebSocket connection
2. Lock assíncrono: para operações thread-safe

Em produção com múltiplos workers, consideraríamos:
- Redis para sessões compartilhadas
- Ou um único worker mode (--workers 1) para desenvolvimento

Para agora (desenvolvimento local), usamos Dict simples com async Lock.
"""

active_sessions: Dict[str, WebSocket] = {}  # session_id â†' WebSocket
sessions_lock = asyncio.Lock()  # Protege acesso a active_sessions


# ===== APLICAÇÃO FASTAPI =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia ciclo de vida da aplicação (startup/shutdown).
    
    Context Manager assíncrono:
    - yield: tudo antes roda na startup
    - tudo depois roda na shutdown
    
    Benefício: Garantido executar cleanup mesmo com exceções
    """
    global brain, motor, database, voice_manager, memory_manager, autonomous_event_bus, autonomous_worker, action_orchestrator, manual_command_handler, audio_adapter, wake_word_listener, voice_command_orchestrator, proactive_monitor
    
    # ===== STARTUP =====
    logger.info("[STARTUP] Quinta-Feira Gateway carregando...")
    logger.info(f"[STARTUP] Frontend esperado em: {config.FRONTEND_URL}")
    logger.info(f"[STARTUP] Security profile: {config.SECURITY_PROFILE}")
    
    # Restauração de backup pedida antes do desligamento: aplicada AQUI, antes de qualquer banco abrir.
    try:
        from core.host.backup import aplicar_restauracao_pendente
        _restaurado = aplicar_restauracao_pendente()
        if _restaurado:
            logger.warning(f"[STARTUP] Backup de {_restaurado} RESTAURADO (o estado anterior ficou em backups/pre_restauracao_*)")
    except Exception as _exc_bk:
        logger.warning(f"[STARTUP] Restauração de backup falhou: {_exc_bk}")

    try:
        # 0. Inicializar ConnectionManager (Singleton para WebSocket)
        logger.info("[STARTUP] Inicializando ConnectionManager (Singleton)...")
        init_connection_manager()
        logger.info("[STARTUP] ConnectionManager pronto")
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

        # 2. Inicializar Motor (automação)
        logger.info("[STARTUP] Inicializando Motor...")
        motor = inicializar_ferramentas(event_publisher=publish_runtime_event)
        # Bridge: ferramentas podem publicar diretamente no AsyncEventBus
        # (ex.: TocarYoutubeTool -> media_playback_requested -> WebSocket)
        if hasattr(motor, "set_runtime_publisher"):
            motor.set_runtime_publisher(publish_runtime_event)
        # Ferramentas de servidores MCP listados em .runtime/mcp.json (nada acontece sem esse arquivo)
        try:
            import os as _os_mcp
            if _os_mcp.getenv("MCP_ENABLED", "true").strip().lower() not in ("0", "false", "no"):
                from core.mcp import carregar as _mcp_carregar
                _mcp_nomes = await _mcp_carregar(motor)
                if _mcp_nomes:
                    logger.info(f"[STARTUP] MCP: {len(_mcp_nomes)} ferramenta(s) registradas")
        except Exception as _exc_mcp:
            logger.warning(f"[STARTUP] MCP indisponível: {_exc_mcp}")
        # Ferramentas que a Quinta propôs e VOCÊ aprovou (hash conferido a cada boot)
        try:
            from core.plugins import carregar_plugins as _carregar_plugins
            _plug = _carregar_plugins(motor)
            if _plug:
                logger.info(f"[STARTUP] Plugins aprovados carregados: {', '.join(_plug)}")
        except Exception as _exc_plug:
            logger.warning(f"[STARTUP] Plugins indisponíveis: {_exc_plug}")

        # 2.1 Aprovação por risco (Fase 0.3): ação CRÍTICA (enviar WhatsApp, terminal, apagar
        # arquivo, iniciar/encerrar processo) pergunta ao Matheus na tela antes de rodar.
        # Guardrail no código, não no prompt. Modo em GET /autonomia; auditoria em /auditoria/acoes.
        from core.api.connection_manager import get_connection_manager
        from core.policy.approvals import get_broker

        _broker = get_broker()

        async def _enviar_aprovacao(evento: Dict[str, Any]) -> int:
            return await get_connection_manager().broadcast_tagged(evento, {"brain_command"})

        _broker.configurar(_enviar_aprovacao)
        motor.set_approval_gate(_broker.gate)
        logger.info(f"[STARTUP] Aprovação por risco ativa (modo: {_broker.modo})")
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
        await brain.initialize()  # pré-aquece o cliente Gemini — elimina latência na 1ª chamada
        brain.set_memory_manager(memory_manager)  # memória viva: auto-recall em toda resposta
        app.state.brain = brain

        # Tools que precisam do brain pra raciocinar (ex: resumir documento)
        try:
            _doc = motor._tools.get("ler_documento")
            if _doc and hasattr(_doc, "set_brain"):
                _doc.set_brain(brain)
            # Visão: `capturar_tela` acao=analisar manda o print ao mesmo modelo do cérebro
            _vis = motor._tools.get("capturar_tela")
            if _vis and hasattr(_vis, "set_brain"):
                _vis.set_brain(brain)
            # Macro precisa do registry pra executar os passos
            _macro = motor._tools.get("macro")
            if _macro and hasattr(_macro, "set_registry"):
                _macro.set_registry(motor)
            # Rascunho precisa do brain + caminho do chat DB (pra amostrar o estilo dele)
            _draft = motor._tools.get("rascunhar")
            if _draft:
                if hasattr(_draft, "set_brain"):
                    _draft.set_brain(brain)
                if hasattr(_draft, "set_chat_db"):
                    _draft.set_chat_db(database.db_path)
        except Exception as _e:
            logger.debug(f"[STARTUP] inject deps em tools: {_e}")
        logger.info(f"[STARTUP] Brain inicializado com LLM: Gemini")

        # 5.1 Inicializar ManualCommandHandler
        manual_command_handler = ManualCommandHandler(
            event_bus=autonomous_event_bus,
            brain=brain,
        )
        await manual_command_handler.start()

        # 6. Inicializar runtime autônomo
        logger.info("[STARTUP] Inicializando EventBus + AutonomousWorker...")
        autonomous_worker = AutonomousWorker(
            event_bus=autonomous_event_bus,
            brain=brain,
            memory_manager=memory_manager,
            tick_interval_seconds=300,  # 5 min: evita queimar tokens da API a cada 20s
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

        # 7. Inicializar stack de áudio (wake word + voz)
        logger.info("[STARTUP] Inicializando Audio Adapter + Wake Word...")
        audio_adapter = AudioAdapter()
        wake_word_listener = WakeWordListener(
            event_bus=autonomous_event_bus,
            audio_adapter=audio_adapter,
        )

        import os as _os
        wake_word_enabled = _os.getenv("WAKE_WORD_ENABLED", "false").lower() == "true"
        if wake_word_enabled:
            await wake_word_listener.start()
            logger.info("[STARTUP] WakeWordListener ativo (microfone em escuta)")
        else:
            logger.info("[STARTUP] WakeWordListener desabilitado (WAKE_WORD_ENABLED=false) — economiza CPU/API")

        voice_command_orchestrator = VoiceCommandOrchestrator(
            event_bus=autonomous_event_bus,
            brain=brain,
            audio_adapter=audio_adapter,
        )
        await voice_command_orchestrator.start()
        app.state.audio_adapter = audio_adapter
        app.state.wake_word_listener = wake_word_listener
        app.state.voice_command_orchestrator = voice_command_orchestrator
        logger.info("[STARTUP] Runtime autônomo ativo")

        # 8. Briefing matinal na inicialização (se habilitado via BRIEFING_ON_STARTUP)
        if config.BRIEFING_ON_STARTUP:
            async def _startup_briefing():
                try:
                    await asyncio.sleep(2)  # deixa o servidor estabilizar
                    from core.briefing import gerar_briefing
                    texto = await gerar_briefing(brain)
                    logger.info(f"[BRIEFING] Startup briefing: {texto[:80]}...")
                    if audio_adapter:
                        await audio_adapter.speak_text(texto)
                except Exception as e:
                    logger.warning(f"[BRIEFING] Falha no briefing de startup: {e}")
            asyncio.create_task(_startup_briefing())
            logger.info("[STARTUP] Briefing matinal agendado (BRIEFING_ON_STARTUP=true)")

        # 9. Ponte Telegram (a Quinta-Feira no celular — conversa + avisos à distância)
        telegram_bridge = None
        try:
            from core.social import TelegramBridge
            telegram_bridge = TelegramBridge(brain=brain, config=config)
            await telegram_bridge.start()
            app.state.telegram_bridge = telegram_bridge
        except Exception as e:
            logger.warning(f"[STARTUP] Telegram indisponível: {e}")

        # 10. Monitor proativo v2 (presença viva: avisos contextuais, saudação,
        #     pulso de presença, amostras de hábito, espelho pro Telegram)
        if config.PROACTIVE_ENABLED:
            from core.proactive import ProactiveMonitor
            proactive_monitor = ProactiveMonitor(
                brain=brain,
                config=config,
                get_last_activity=lambda: getattr(app.state, "last_user_activity", None),
                check_interval_seconds=60,
                memory_manager=memory_manager,
                notifier=telegram_bridge,
            )
            await proactive_monitor.start()
            app.state.proactive_monitor = proactive_monitor
            logger.info("[STARTUP] Monitor proativo ativo")

        # 11. Reflexão (auto-aprendizado): ela relê o dia e destila fatos sozinha
        if config.REFLECTION_ENABLED:
            try:
                from core.learning import ReflectionService
                reflection_service = ReflectionService(
                    brain=brain,
                    memory_manager=memory_manager,
                    chat_db_path=database.db_path,
                    interval_hours=config.REFLECTION_INTERVAL_HOURS,
                )
                await reflection_service.start()
                app.state.reflection_service = reflection_service
                logger.info("[STARTUP] Reflexão (auto-aprendizado) ativa")
            except Exception as e:
                logger.warning(f"[STARTUP] Reflexão indisponível: {e}")

        # 11.5 Memória vetorial: indexa memórias antigas em background (uma vez
        #      por boot; memórias novas são indexadas na hora em que são salvas)
        if config.EMBEDDINGS_ENABLED:
            try:
                from core.memory.embedding_service import get_embedding_service
                emb = get_embedding_service()
                if emb:
                    asyncio.create_task(emb.backfill())
                    logger.info("[STARTUP] Memória vetorial ativa (backfill em background)")
            except Exception as e:
                logger.warning(f"[STARTUP] Memória vetorial indisponível: {e}")

        # 12. Curiosidade (aprendizado via internet, com SearchGuard): ela
        #     pesquisa sozinha sobre o universo do Matheus e traz descobertas.
        if config.CURIOSITY_ENABLED:
            try:
                from core.learning import CuriosityService
                curiosity_service = CuriosityService(
                    brain=brain,
                    memory_manager=memory_manager,
                    config=config,
                    interval_hours=config.CURIOSITY_INTERVAL_HOURS,
                )
                await curiosity_service.start()
                app.state.curiosity_service = curiosity_service
                logger.info("[STARTUP] Curiosidade (aprendizado via internet) ativa")
            except Exception as e:
                logger.warning(f"[STARTUP] Curiosidade indisponível: {e}")

        logger.info("[STARTUP] Gateway PRONTO (Fase 3-6 integrada!)")
    
    except Exception as e:
        logger.error(f"[STARTUP] Erro: {e}", exc_info=True)
        raise
    
    yield  # Aplicação roda aqui
    
    # ===== SHUTDOWN =====
    logger.info("[SHUTDOWN] Encerrando Gateway...")
    
    # Fechar todas as conexoes WebSocket (ConnectionManager)
    from core.api import get_connection_manager
    try:
        manager = get_connection_manager()
        await manager.close_all()
        logger.info("[SHUTDOWN] ConnectionManager: todas as conexoes fechadas")
    except Exception as e:
        logger.warning(f"[SHUTDOWN] Erro ao fechar ConnectionManager: {e}")

    if proactive_monitor:
        try:
            await proactive_monitor.stop()
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Erro ao parar monitor proativo: {e}")

    for attr in ("reflection_service", "curiosity_service", "telegram_bridge"):
        svc = getattr(app.state, attr, None)
        if svc:
            try:
                await svc.stop()
            except Exception as e:
                logger.warning(f"[SHUTDOWN] Erro ao parar {attr}: {e}")

    try:
        from core.mcp import parar_todos as _mcp_parar
        await _mcp_parar()
    except Exception as e:
        logger.warning(f"[SHUTDOWN] Erro ao parar servidores MCP: {e}")

    # Parar runtime autônomo primeiro (graceful shutdown)
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

    if manual_command_handler:
        try:
            await manual_command_handler.stop()
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Erro ao parar manual command handler: {e}")

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
        # Fechar todas as sessões WebSocket abertas
        closed = 0
        for session_id, websocket in active_sessions.items():
            try:
                await websocket.close(code=1000, reason="Servidor encerrando")
                closed += 1
            except Exception as e:
                logger.warning(f"[SHUTDOWN] Erro ao fechar {session_id}: {e}")
        
        active_sessions.clear()
        logger.info(f"[SHUTDOWN] {closed} sessões fechadas")
    
    logger.info("[SHUTDOWN] Gateway encerrado")


app = FastAPI(
    title="Quinta-Feira AI Gateway",
    description="Interface entre Frontend (Next.js) e Core (Brain)",
    version="1.0-gateway",
    lifespan=lifespan  # â† NOVO: gerencia lifecycle
)
app.include_router(ws_observability_router)
app.include_router(brain_router)  # Rota /ws/quinta para comunicacao com Brain

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    include_vision: bool = False




# ===== MIDDLEWARE: CORS =====
"""
CORS (Cross-Origin Resource Sharing):
Permite que frontend em localhost:3000 acesse backend em localhost:8000.

Sem CORS:
> Navegador bloqueia requisição (SOP - Same Origin Policy)
> TypeError: Failed to fetch

Com CORS:
> Servidor autoriza requisição
> Funciona normalmente
"""

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        config.FRONTEND_URL,  # http://localhost:3000
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        *config.EXTRA_ALLOWED_ORIGINS,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Guarda de acesso local (Host + Origin, HTTP e WebSocket). Adicionada DEPOIS do CORS,
# então é a camada mais externa: barra antes de qualquer rota. Ver core/api/local_guard.py.
if config.LOCAL_GUARD_ENABLED:
    from core.api.local_guard import LocalOnlyGuard, origens_permitidas

    app.add_middleware(
        LocalOnlyGuard,
        allowed_origins=origens_permitidas(config.FRONTEND_URL, config.EXTRA_ALLOWED_ORIGINS),
        allowed_hosts=config.EXTRA_ALLOWED_HOSTS,
    )

# Token por sessão (core/api/session_token.py): modo `registrar` por padrão (só avisa no log se o
# cliente não mandou o token); SESSION_TOKEN_MODE=exigir passa a recusar (401 / fecha o WebSocket).
try:
    from core.api.session_token import TokenGuard, iniciar_token, modo_configurado
    if modo_configurado() != "off":
        iniciar_token()
        app.add_middleware(TokenGuard)
        logger.info(f"[STARTUP] Token por sessão: modo '{modo_configurado()}'")
except Exception as _exc_tok:
    logger.warning(f"[STARTUP] Token por sessão indisponível: {_exc_tok}")


# ===== ROTAS REST =====

@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """
    Health Check: Frontend faz ping aqui para verificar se backend está online.
    
    Status Codes:
    - 200 OK: Gateway pronto
    - 503 Service Unavailable: Cérebro ainda não inicializado
    
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
    
    Quando o Cérebro estiver pronto, vai reportar:
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


@app.get("/context", tags=["Status"])
async def get_context_snapshot() -> Dict[str, Any]:
    """
    Fotografia do momento (ContextSensor): hora, app em foco, jogo rodando,
    CPU/RAM, bateria, clima e uptime de sessão. Alimenta o HUD de sistema
    do frontend (polling leve).
    """
    monitor = getattr(app.state, "proactive_monitor", None)
    sensor = getattr(monitor, "_sensor", None) if monitor else None
    if sensor is None:
        sensor = getattr(app.state, "context_sensor", None)
        if sensor is None:
            from core.proactive.context_snapshot import ContextSensor
            sensor = ContextSensor(config)
            app.state.context_sensor = sensor
    try:
        snap = await sensor.snapshot()
        return {"ok": True, **snap}
    except Exception as e:
        logger.warning(f"[CONTEXT] Erro ao coletar snapshot: {e}")
        return {"ok": False}


@app.get("/proactive", tags=["Proactive"])
async def get_proactive() -> Dict[str, Any]:
    """
    Avisos proativos pendentes (bateria/CPU/RAM/clima/pausa). O frontend faz polling
    e narra em voz alta. Cada aviso é entregue uma única vez (a fila é esvaziada).
    """
    monitor = getattr(app.state, "proactive_monitor", None)
    if not monitor:
        return {"alerts": []}
    try:
        alerts = await monitor.get_pending()
        return {"alerts": alerts}
    except Exception as e:
        logger.warning(f"[PROACTIVE] Erro ao obter avisos: {e}")
        return {"alerts": []}


class TTSRequest(BaseModel):
    text: str


@app.post("/tts", tags=["Voice"])
async def tts_endpoint(payload: TTSRequest) -> Response:
    """
    A VOZ dela: sintetiza o texto com o melhor provider (ElevenLabs → EdgeTTS
    neural pt-BR → pyttsx3) e retorna o áudio. O frontend toca este áudio em
    vez da voz robótica do navegador.
    """
    if not voice_manager:
        raise HTTPException(status_code=503, detail="Voz não inicializada")
    texto = (payload.text or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Texto vazio")
    try:
        from core.audio import tts_cache
        audio = await tts_cache.sintetizar_com_cache(voice_manager, texto[:800])  # frase curta repetida: sem custo
        media = "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg"
        return Response(content=audio, media_type=media)
    except Exception as e:
        logger.warning(f"[TTS] Falha na síntese: {e}")
        raise HTTPException(status_code=503, detail="TTS indisponível")


@app.get("/profile", tags=["Learning"])
async def get_learned_profile() -> Dict[str, Any]:
    """
    O que a Quinta-Feira já aprendeu sozinha sobre o Matheus (memórias semânticas
    + últimos resumos de dia da reflexão). Visibilidade do auto-aprendizado.
    """
    if not memory_manager:
        return {"fatos": [], "diarios": []}
    try:
        mem = await memory_manager.retrieve_memory(memory_type="all", limit=40)
        fatos = [
            {
                "id": m.get("id"),
                "categoria": m.get("category", ""),
                "chave": m.get("key", ""),
                "valor": m.get("value", ""),
                "fonte": m.get("source", ""),
                "atualizado_em": m.get("updated_at", ""),
            }
            for m in mem.get("semantic", [])
        ]
        diarios = [
            {"resumo": m.get("summary", ""), "data": m.get("created_at", "")}
            for m in mem.get("episodic", [])
            if m.get("event_type") == "diario"
        ]
        # Descobertas da curiosidade (o que ela foi atrás e aprendeu na internet)
        descobertas = [
            {"texto": m.get("summary", ""), "data": m.get("created_at", "")}
            for m in mem.get("episodic", [])
            if m.get("event_type") == "descoberta"
        ]
        reflexao = getattr(app.state, "reflection_service", None)
        curiosidade = getattr(app.state, "curiosity_service", None)
        return {
            "fatos": fatos,
            "diarios": diarios[:7],
            "descobertas": descobertas[:8],
            "ultima_reflexao_ts": getattr(reflexao, "last_run_ts", 0.0),
            "fatos_na_ultima_reflexao": getattr(reflexao, "last_facts_count", 0),
            "ultima_curiosidade_ts": getattr(curiosidade, "last_run_ts", 0.0),
        }
    except Exception as e:
        logger.warning(f"[PROFILE] Erro: {e}")
        return {"fatos": [], "diarios": []}


@app.put("/memoria/fatos/{fato_id}", tags=["Learning"])
async def editar_fato(fato_id: int, corpo: Dict[str, Any]) -> Dict[str, Any]:
    """Corrige um fato que ela aprendeu errado (painel de memória). Sem LLM."""
    from core.memory.edicao import validar_valor
    valor = validar_valor(corpo.get("valor"))
    if valor is None:
        raise HTTPException(status_code=422, detail="valor inválido (texto de 1 a 500 caracteres)")
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memória não inicializada")
    return {"ok": await memory_manager.update_semantic_value(fato_id, valor)}


@app.get("/memoria/saude", tags=["Learning"])
async def memoria_saude() -> Dict[str, Any]:
    """Números da memória: fatos por fonte/categoria, nunca usados, esquecíveis, conflitos. Sem LLM."""
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memória não inicializada")
    return await memory_manager.saude()


@app.get("/memoria/conflitos", tags=["Learning"])
async def memoria_conflitos() -> Dict[str, Any]:
    """Propostas que NÃO foram aplicadas porque o fato atual (ex.: corrigido por você) tem mais autoridade."""
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memória não inicializada")
    return {"conflitos": await memory_manager.conflitos()}


@app.post("/memoria/conflitos/{hid}/{acao}", tags=["Learning"])
async def memoria_resolver_conflito(hid: int, acao: str) -> Dict[str, Any]:
    """Você decide: `aceitar` (o valor proposto vira o fato) ou `manter` (fica o atual)."""
    if acao not in ("aceitar", "manter"):
        raise HTTPException(status_code=422, detail="acao deve ser 'aceitar' ou 'manter'")
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memória não inicializada")
    return {"ok": await memory_manager.resolver_conflito(hid, acao == "aceitar")}


@app.get("/memoria/esqueciveis", tags=["Learning"])
async def memoria_esqueciveis() -> Dict[str, Any]:
    """Candidatos a esquecer (baixa confiança e sem uso). Só sugere; apagar é decisão sua."""
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memória não inicializada")
    return {"esqueciveis": await memory_manager.esqueciveis()}


@app.delete("/memoria/fatos/{fato_id}", tags=["Learning"])
async def apagar_fato(fato_id: int) -> Dict[str, Any]:
    """Esquece um fato (painel de memória). Sem LLM."""
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memória não inicializada")
    return {"ok": await memory_manager.delete_semantic(fato_id)}


@app.post("/reflect", tags=["Learning"])
async def trigger_reflection() -> Dict[str, Any]:
    """Dispara uma rodada de reflexão manualmente (teste/depuração)."""
    reflexao = getattr(app.state, "reflection_service", None)
    if not reflexao:
        raise HTTPException(status_code=503, detail="Reflexão não inicializada")
    return await reflexao.refletir()


@app.post("/consolidar_memoria", tags=["Learning"])
async def consolidar_memoria() -> Dict[str, Any]:
    """Faxina da memória: funde fatos duplicados/redundantes."""
    if not brain or not memory_manager:
        raise HTTPException(status_code=503, detail="Brain/memória não inicializados")
    from core.learning.memory_consolidation import MemoryConsolidation
    return await MemoryConsolidation(brain=brain, memory_manager=memory_manager).consolidar()


@app.post("/curiosity", tags=["Learning"])
async def trigger_curiosity() -> Dict[str, Any]:
    """Dispara uma rodada de curiosidade (pesquisa autônoma na web) manualmente."""
    curiosidade = getattr(app.state, "curiosity_service", None)
    if not curiosidade:
        raise HTTPException(status_code=503, detail="Curiosidade não inicializada")
    return await curiosidade.explorar()


@app.get("/news", tags=["News"])
async def get_news(limit: int = 8) -> Dict[str, Any]:
    """
    Retorna as principais notícias (com imagem) para o carrossel do visor.
    Usado pelo frontend na inicialização (mostrar notícias ao ligar o PC).
    """
    try:
        from core.briefing.news import get_top_news_rich
        artigos = await get_top_news_rich(limit=limit)
        items = [
            {
                "titulo": a.get("titulo", ""),
                "resumo": a.get("resumo", ""),
                "imagem": a.get("imagem", ""),
                "fonte": "G1",
                "url": a.get("url", ""),
            }
            for a in artigos if a.get("titulo")
        ]
        # "Com as palavras dela" + opinião final (1 chamada ao LLM)
        comentario = ""
        if items and brain:
            try:
                narr = await brain.gerar_narracao_noticias(items)
                for it, fala in zip(items, narr.get("falas", [])):
                    it["fala"] = fala
                comentario = narr.get("comentario", "")
            except Exception as e:
                logger.warning(f"[NEWS] Falha ao gerar narração: {e}")
        return {"items": items, "count": len(items), "comentario": comentario}
    except Exception as e:
        logger.warning(f"[NEWS] Falha ao obter notícias: {e}")
        return {"items": [], "count": 0}



@app.get("/diagnostico", tags=["Health"])
async def diagnostico() -> Dict[str, Any]:
    """Saúde das integrações: Gemini, WhatsApp, embeddings, finanças, agenda.
    Falha nunca silenciosa — o que quebrou aparece aqui."""
    try:
        from core.diagnostics import diagnostico_completo
        return await diagnostico_completo()
    except Exception as e:
        return {"ok": False, "erro": str(e), "checks": {}, "problemas": [str(e)]}


@app.get("/traces", tags=["Health"])
async def traces_resumo() -> Dict[str, Any]:
    """Onde o tempo das respostas é gasto (p50/p95 por etapa, últimos 200 pedidos). Custo zero."""
    from core.telemetry.traces import resumo
    return resumo()


@app.get("/painel", tags=["Health"])
async def painel() -> Dict[str, Any]:
    """Custo, latência, falhas, regressões, avisos, backup, pendências e segurança numa resposta só.
    Só lê o que já está no disco (zero chamadas de modelo)."""
    from core.telemetry.painel import montar
    return await asyncio.to_thread(montar)


@app.get("/custo", tags=["Health"])
async def custo(horas: float = 24.0) -> Dict[str, Any]:
    """Quanto a Quinta gastou de Gemini na janela (tokens e US$ estimados), por função.
    Mostra onde o dinheiro vai: chat, avisos, reflexão, curiosidade... e a taxa de cache."""
    try:
        from core.telemetry.token_ledger import resumo
        return resumo(horas=max(0.1, min(float(horas), 24 * 30)))
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@app.get("/autonomia", tags=["Segurança"])
async def get_autonomia() -> Dict[str, Any]:
    """Modo de autonomia atual: quando a Quinta pergunta antes de agir."""
    from core.policy.approvals import MODOS, get_broker
    b = get_broker()
    return {"modo": b.modo, "modos": list(MODOS), "pendentes": len(b.eventos_pendentes())}


@app.post("/autonomia", tags=["Segurança"])
async def set_autonomia(body: Dict[str, Any]) -> Dict[str, Any]:
    """Muda o modo: perguntar_sempre | so_perigoso (padrão) | autonoma. Persiste entre reinícios."""
    from core.policy.approvals import MODOS, get_broker
    b = get_broker()
    modo = str((body or {}).get("modo", "")).strip()
    if not b.definir_modo(modo):
        raise HTTPException(status_code=400, detail=f"modo inválido; use um de {list(MODOS)}")
    return {"ok": True, "modo": b.modo}


@app.get("/auditoria/acoes", tags=["Segurança"])
async def auditoria_acoes(limite: int = 50) -> Dict[str, Any]:
    """Últimas decisões sobre ações de risco (liberado / aprovado / negado / expirou)."""
    import json as _json
    from pathlib import Path as _Path
    arq = _Path(__file__).resolve().parent / ".runtime" / "audit" / "tool_risk.jsonl"
    linhas = []
    try:
        for bruto in arq.read_text(encoding="utf-8").splitlines()[-max(1, min(int(limite), 500)):]:
            try:
                linhas.append(_json.loads(bruto))
            except Exception:
                continue
    except FileNotFoundError:
        pass
    return {"acoes": list(reversed(linhas))}


@app.get("/licoes", tags=["Learning"])
async def listar_licoes() -> Dict[str, Any]:
    """Regras de comportamento que ela aprendeu com as suas correções (ordem de gravação)."""
    try:
        from core.learning.lessons_store import get_lessons_store
        return {"licoes": get_lessons_store().listar()}
    except Exception as e:
        return {"licoes": [], "erro": str(e)}


@app.get("/evals", tags=["Learning"])
async def evals_resumo() -> Dict[str, Any]:
    """Casos de regressão feitos das suas correções + regras que não chegam ao prompt (grátis)."""
    from core.learning.regressao import get_casos, resumo_gratis
    return {**resumo_gratis(), "lista": get_casos().listar()[-30:]}


@app.post("/evals/rodar", tags=["Learning"])
async def evals_rodar(corpo: Dict[str, Any]) -> Dict[str, Any]:
    """Roda os casos contra o modelo. SÓ com confirmar=true (uma chamada por caso, máx. 10)."""
    if not brain:
        raise HTTPException(status_code=503, detail="Brain não inicializado")
    from core.learning.regressao import rodar_avaliacao
    return await rodar_avaliacao(brain, confirmar=bool(corpo.get("confirmar")))


@app.delete("/evals/casos/{cid}", tags=["Learning"])
async def evals_apagar(cid: str) -> Dict[str, Any]:
    from core.learning.regressao import get_casos
    return {"ok": get_casos().remover(cid)}


@app.get("/lacunas", tags=["Learning"])
async def lacunas_da_semana() -> Dict[str, Any]:
    """Onde ela falhou nos últimos 7 dias (agrupado). Local, sem LLM."""
    from core.learning.gaps import get_ledger
    led = get_ledger()
    return {"total": led.total(7), "grupos": led.agrupar(7, 15)}


@app.get("/melhorias", tags=["Learning"])
async def listar_melhorias() -> Dict[str, Any]:
    from core.learning.self_review import get_melhorias
    return {"melhorias": get_melhorias().listar()}


@app.post("/melhorias/revisar", tags=["Learning"])
async def revisar_agora() -> Dict[str, Any]:
    """Roda a revisão semanal agora (respeita o mínimo de lacunas; no máximo 1 chamada leve)."""
    if not brain:
        raise HTTPException(status_code=503, detail="Brain não inicializado")
    from core.learning.self_review import revisar
    return await revisar(brain, forcar=True)


@app.post("/melhorias/{pid}/{decisao}", tags=["Learning"])
async def decidir_melhoria(pid: str, decisao: str) -> Dict[str, Any]:
    if decisao not in ("aceitar", "rejeitar"):
        raise HTTPException(status_code=422, detail="decisao: aceitar | rejeitar")
    from core.learning.self_review import aceitar, get_melhorias
    if decisao == "aceitar":
        return aceitar(pid)
    return {"ok": get_melhorias().decidir(pid, False) is not None}


@app.get("/pendencias", tags=["Learning"])
async def listar_pendencias() -> Dict[str, Any]:
    """O que ficou em aberto e a Quinta acompanha (retoma no máximo 1 por dia, 3 toques por item)."""
    from core.learning.pendencias import get_pendencias
    return {"abertas": get_pendencias().listar("aberta")}


@app.post("/pendencias/{pid}/{estado}", tags=["Learning"])
async def decidir_pendencia(pid: str, estado: str) -> Dict[str, Any]:
    if estado not in ("resolvida", "dispensada"):
        raise HTTPException(status_code=422, detail="estado: resolvida | dispensada")
    from core.learning.pendencias import get_pendencias
    return {"ok": get_pendencias().decidir(pid, estado)}


@app.get("/backups", tags=["Health"])
async def listar_backups() -> Dict[str, Any]:
    """Backups diários do que a Quinta aprendeu (memória, lembretes, pessoas, lições, skills)."""
    from core.host import backup
    return {"backups": backup.listar()}


@app.post("/backups/agora", tags=["Health"])
async def backup_agora() -> Dict[str, Any]:
    from core.host import backup
    pasta = await asyncio.to_thread(backup.fazer_backup, None, None, forcar=True)
    return {"ok": pasta is not None, "dia": pasta.name if pasta else None}


@app.post("/backups/restaurar", tags=["Health"])
async def restaurar_backup(corpo: Dict[str, Any]) -> Dict[str, Any]:
    """Agenda a restauração para o PRÓXIMO boot (não mexe em arquivo aberto). Exige confirmar=true."""
    if not corpo.get("confirmar"):
        return {"ok": False, "mensagem": "Confirme: a restauração troca a memória atual pelo backup (o estado atual é guardado em backups/pre_restauracao_*)."}
    from core.host import backup
    motivo = backup.agendar_restauracao(str(corpo.get("dia", "")))
    return {"ok": not motivo, "mensagem": motivo or "Agendada: será aplicada quando a Quinta for reiniciada."}


@app.get("/plugins", tags=["Learning"])
async def listar_plugins() -> Dict[str, Any]:
    """Ferramentas propostas (com código e avisos) e as aprovadas."""
    from core.plugins import escanear, get_plugin_store
    loja = get_plugin_store()
    pend = loja.pendentes()
    for p in pend:
        p["relatorio"] = escanear(p["codigo"])
    return {"pendentes": pend, "aprovadas": loja.aprovadas()}


@app.post("/plugins/{pid}/testar", tags=["Learning"])
async def testar_plugin(pid: str) -> Dict[str, Any]:
    """Roda os testes da proposta num subprocesso isolado (só quando você pede)."""
    from core.plugins import get_plugin_store
    return await asyncio.to_thread(get_plugin_store().rodar_testes, pid)


@app.post("/plugins/{pid}/{decisao}", tags=["Learning"])
async def decidir_plugin(pid: str, decisao: str, leitura: bool = False) -> Dict[str, Any]:
    """aprovar (exige testes passados; `leitura=true` = sem cartão a cada uso) | rejeitar."""
    from core.plugins import get_plugin_store
    loja = get_plugin_store()
    if decisao == "aprovar":
        ok, msg = loja.aprovar(pid, somente_leitura=leitura)
        return {"ok": ok, "mensagem": msg}
    if decisao == "rejeitar":
        return {"ok": loja.rejeitar(pid)}
    raise HTTPException(status_code=422, detail="decisao: aprovar | rejeitar")


@app.get("/skills", tags=["Learning"])
async def listar_skills() -> Dict[str, Any]:
    """Skills aprovadas e propostas esperando a sua decisão (com o texto atual para comparar)."""
    from core.skills import get_skill_store
    loja = get_skill_store()
    return {"skills": loja.listar(), "pendentes": loja.pendentes()}


@app.post("/skills/pendentes/{pid}/{decisao}", tags=["Learning"])
async def decidir_skill(pid: str, decisao: str) -> Dict[str, Any]:
    """Só o Matheus decide (a ferramenta do LLM não tem acesso a esta rota)."""
    from core.skills import get_skill_store
    loja = get_skill_store()
    if decisao == "aprovar":
        ok, msg = loja.aprovar(pid)
        return {"ok": ok, "mensagem": msg}
    if decisao in ("rejeitar", "quarentena"):
        return {"ok": loja.rejeitar(pid, quarentena=(decisao == "quarentena"))}
    raise HTTPException(status_code=422, detail="decisao: aprovar | rejeitar | quarentena")


@app.post("/skills/{nome}/reverter", tags=["Learning"])
async def reverter_skill(nome: str) -> Dict[str, Any]:
    from core.skills import get_skill_store
    return {"ok": get_skill_store().reverter(nome)}


@app.delete("/skills/{nome}", tags=["Learning"])
async def arquivar_skill(nome: str) -> Dict[str, Any]:
    """'Apagar' arquiva (não exclui)."""
    from core.skills import get_skill_store
    return {"ok": get_skill_store().arquivar(nome)}


@app.get("/guardas/propostas", tags=["Learning"])
async def propostas_de_guarda() -> Dict[str, Any]:
    """Lições repetidas que podem virar regra em código (aceitar/rejeitar). Sem LLM."""
    from core.learning.lesson_guards import get_guard_store
    from core.learning.lessons_store import get_lessons_store
    guardas = get_guard_store()
    guardas.atualizar_propostas(get_lessons_store().listar())
    return {"propostas": guardas.listar()}


@app.post("/guardas/propostas/{pid}/{decisao}", tags=["Learning"])
async def decidir_proposta(pid: str, decisao: str) -> Dict[str, Any]:
    if decisao not in ("aceitar", "rejeitar"):
        raise HTTPException(status_code=422, detail="decisao deve ser 'aceitar' ou 'rejeitar'")
    from core.learning.lesson_guards import get_guard_store
    return {"ok": get_guard_store().decidir(pid, decisao == "aceitar")}


@app.delete("/licoes/{indice}", tags=["Learning"])
async def remover_licao(indice: int) -> Dict[str, Any]:
    """Apaga uma lição errada (índice de GET /licoes)."""
    try:
        from core.learning.lessons_store import get_lessons_store
        return {"ok": get_lessons_store().remover(indice)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@app.post("/briefing_ritual", tags=["Chat"])
async def briefing_ritual(periodo: str = "manha") -> Dict[str, Any]:
    """Ritual falado: panorama do dia (clima+notícias+agenda+mercado+lembretes)."""
    if not brain:
        raise HTTPException(status_code=503, detail="Brain não inicializado")
    texto = await brain.montar_briefing("noite" if periodo == "noite" else "manha")
    return {"ok": True, "periodo": periodo, "text": texto}


@app.post("/ambient", tags=["Chat"])
async def ambient_speech(payload: ChatRequest) -> Dict[str, Any]:
    """
    Escuta ambiente: o frontend manda TODA fala captada (sem exigir wake word) e
    aqui a Quinta-Feira decide, como uma pessoa, se aquilo foi dirigido A ELA ou
    a outra coisa (chamada no Discord, conversa com alguém, jogo). Só responde se
    tiver confiança de que era com ela — falso positivo é pior que silêncio.
    """
    import time as _time
    if not brain:
        raise HTTPException(status_code=503, detail="Brain não inicializado")
    texto = (payload.message or "").strip()
    if not texto:
        return {"responder": False, "motivo": "vazio"}

    # Contexto rápido do momento (sem clima, pra não atrasar)
    contexto = ""
    em_call = False
    em_jogo = False
    try:
        monitor = getattr(app.state, "proactive_monitor", None)
        sensor = getattr(monitor, "_sensor", None) if monitor else getattr(app.state, "context_sensor", None)
        if sensor is None:
            from core.proactive.context_snapshot import ContextSensor
            sensor = ContextSensor(config)
            app.state.context_sensor = sensor
        snap = await asyncio.wait_for(sensor.snapshot(include_weather=False), timeout=2.0)
        from core.proactive.context_snapshot import ContextSensor as _CS
        contexto = _CS.to_prompt(snap)
        em_call = bool(snap.get("em_chamada"))
        em_jogo = bool(snap.get("jogo_rodando") and snap.get("fullscreen"))
        if em_call:
            contexto += "\nHÁ UMA CHAMADA/REUNIÃO ATIVA agora (Discord/Meet/Zoom) — fala pode ser pra outra pessoa."
        if em_jogo:
            contexto += "\nEle está num JOGO em tela cheia — pode estar falando com o time."
    except Exception:
        pass

    ultima = getattr(app.state, "last_qf_interaction", None)
    ultima_seg = (_time.time() - ultima) if ultima else None

    veredito = await brain.classificar_enderecamento(texto, contexto, ultima_seg)
    # Reconhecimento contextual: numa chamada/jogo, a maior parte da fala é pra
    # OUTRA pessoa (a "galera do Discord"). Sem voiceprint acústico, elevamos a
    # exigência nesses momentos — ela só assume que é com ela se tiver bem certa.
    limiar = float(getattr(config, "AMBIENT_CONFIDENCE_THRESHOLD", 0.6))
    if em_call:
        limiar = max(limiar, 0.85)
    elif em_jogo:
        limiar = max(limiar, 0.78)

    if veredito.get("dirigido") and veredito.get("confianca", 0) >= limiar:
        app.state.last_qf_interaction = _time.time()
        try:
            resp = await asyncio.wait_for(brain.ask(message=texto), timeout=30.0)
            try:
                await database.add_message(session_id="ambient", role="user", content=texto)
                await database.add_message(session_id="ambient", role="assistant", content=resp.text)
            except Exception:
                pass
            return {
                "responder": True,
                "text": resp.text,
                "mode": resp.mode,
                "visor": resp.visor,
                "veredito": veredito,
            }
        except Exception as e:
            logger.warning(f"[AMBIENT] Falha ao responder: {e}")
            return {"responder": False, "motivo": "erro", "veredito": veredito}

    return {"responder": False, "veredito": veredito, "limiar": limiar}


@app.api_route("/briefing", methods=["GET", "POST"], tags=["Briefing"])
async def briefing_matinal(speak: bool = True) -> Dict[str, Any]:
    """
    Gera o briefing matinal (clima + notícias) e opcionalmente fala em voz alta.

    Query param:
        speak: se True (padrão), reproduz o áudio via TTS na máquina local.

    Usado por: gatilho de inicialização do PC e teste manual.
    """
    if not brain:
        raise HTTPException(status_code=503, detail="Brain não inicializado")

    from core.briefing import gerar_briefing

    texto = await gerar_briefing(brain)

    # TTS em background: a fala pode levar dezenas de segundos; não bloqueamos
    # a resposta HTTP por isso (o launcher só precisa do texto + o disparo).
    if speak and audio_adapter:
        async def _speak_briefing(t: str) -> None:
            try:
                await audio_adapter.speak_text(t)
            except Exception as e:
                logger.warning(f"[BRIEFING] TTS falhou: {e}")
        asyncio.create_task(_speak_briefing(texto))

    return {
        "text": texto,
        "spoken": bool(speak and audio_adapter),  # enfileirado para fala
        "timestamp": datetime.utcnow().isoformat() + "Z",
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

# ===== WEBSOCKET: CONDUÃTE NEURAL =====

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket Endpoint: Conduíte Neural entre Frontend e Brain.
    
    FLUXO:
    1. Cliente conecta â†' Registra sessão
    2. Cliente envia JSON â†' Gateway parseia
    3. Gateway encaminha para Brain (ainda mock)
    4. Brain responde â†' Gateway retorna JSON ao cliente
    5. Cliente desconecta â†' Limpa sessão
    
    TRATAMENTO DE CONCORRÊNCIA:
    
    Problema: Múltiplas conexões WebSocket simultâneas podem:
    - Corromper dicionário active_sessions (race condition)
    - Enviar mensagens fora de ordem
    - Deixar sessão "zumbando" sem cleanup
    
    Solução: Usar asyncio.Lock
    - Lock é adquirido ANTES de modificar active_sessions
    - Liberar IMEDIATAMENTE depois
    - Receber/Enviar SEM lock (não é crítico)
    
    Exemplo de race condition SEM lock:
    > Thread A lê: len(active_sessions) = 5
    > Thread B lê: len(active_sessions) = 5
    > Thread A escreve: active_sessions[id] = ws â†' agora 6
    > Thread B não viu a alteração de A
    > Estado inconsistente!
    
    Com lock:
    > Thread A adquire: lock.acquire()
    > Thread A lê/escreve atomicamente
    > Thread A libera: lock.release()
    > Thread B espera lock ficar disponível
    > Ordenação garantida
    """
    
    await websocket.accept()
    
    # Registrar sessão
    async with sessions_lock:
        active_sessions[session_id] = websocket
    
    logger.info(f"[WS] Conectado: {session_id} (total: {len(active_sessions)})")
    
    try:
        # Enviar confirmação de conexão
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "session_id": session_id,
            "message": "Gateway ativo. Aguardando cérebro...",
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
                    "payload": {
                        "error_code": "TIMEOUT",
                        "message": "Sessao inativa por muito tempo",
                    },
                    "request_id": "",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
                break
            
            # Parsear mensagem
            try:
                message_type = data.get("type", "").strip()
                payload = data.get("payload", {})
                request_id = data.get("request_id", "")
                
                logger.info(f"[WS] Recebido envelope type={message_type} de {session_id}")
                
                # Rota por tipo de mensagem
                if message_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "payload": {},
                        "request_id": request_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    })
                    logger.debug(f"[WS] Pong enviado")
                    continue
                
                if message_type != "user_message":
                    logger.warning(f"[WS] Tipo de mensagem desconhecido: {message_type}")
                    await websocket.send_json({
                        "type": "error",
                        "payload": {
                            "error_code": "UNKNOWN_MESSAGE_TYPE",
                            "message": f"Tipo de mensagem nao suportado: {message_type}",
                        },
                        "request_id": request_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    })
                    continue
                
                # Processar user_message
                message_text = payload.get("text", "").strip()
                mode = payload.get("mode", "streaming")
                
                if not message_text:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {
                            "error_code": "INVALID_INPUT",
                            "message": "Mensagem vazia",
                        },
                        "request_id": request_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    })
                    continue
                
                logger.info(f"[WS] Recebido de {session_id}: '{message_text[:50]}'... (mode={mode})")
                
                # ===== CHAMAR BRAIN REAL =====
                if not brain:
                    raise RuntimeError("Brain não inicializado")
                
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
                            include_vision=False
                        ),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    logger.error(f"[WS] Timeout em brain.ask() para {session_id}")
                    await websocket.send_json({
                        "type": "error",
                        "payload": {
                            "error_code": "TIMEOUT",
                            "message": "Estou com lentidao para responder agora. Tente novamente em alguns segundos.",
                        },
                        "request_id": request_id,
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
                
                # Enviar resposta do Brain IMEDIATAMENTE — sem bloquear para TTS
                audio_from_brain = brain_response.audio or ""
                logger.info(f"[WS] Enviando resposta para {session_id}...")
                await websocket.send_json({
                    "type": "brain_response",
                    "payload": {
                        "text": brain_response.text,
                        "audio": audio_from_brain,
                        "mode": brain_response.mode,
                        "execution_time_ms": 0,
                        "tools_used": [],
                        "visor": getattr(brain_response, "visor", None),
                    },
                    "request_id": request_id,
                    "timestamp": brain_response.timestamp,
                })
                logger.info(f"[WS] Respondido a {session_id}")

                # TTS em background: não bloqueia nem atrasa a resposta ao cliente
                if not audio_from_brain and voice_manager:
                    async def _speak_async(text: str) -> None:
                        try:
                            await voice_manager.synthesize(text)
                        except Exception as _e:
                            logger.debug(f"[WS] TTS background ignorado: {_e}")
                    asyncio.create_task(_speak_async(brain_response.text))
            
            except json.JSONDecodeError as e:
                logger.error(f"[WS] JSON invalido de {session_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "payload": {
                        "error_code": "JSON_PARSE_ERROR",
                        "message": f"JSON invalido: {str(e)}",
                    },
                    "request_id": "",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            
            except Exception as e:
                logger.error(f"[WS] Erro ao processar: {type(e).__name__}: {e}")
                if isinstance(e, QuintaFeirError):
                    await websocket.send_json(e.to_dict())
                else:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {
                            "error_code": "INTERNAL_ERROR",
                            "message": f"Erro interno: {str(e)}",
                        },
                        "request_id": "",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    })
    
    except WebSocketDisconnect:
        logger.info(f"[WS] Desconexão normal: {session_id}")
    
    except Exception as e:
        logger.error(f"[WS] Erro fatal: {session_id}: {type(e).__name__}: {e}")
    
    finally:
        # ===== CLEANUP: ZERAR SESSÃO =====
        async with sessions_lock:
            if session_id in active_sessions:
                del active_sessions[session_id]
                logger.info(f"[WS] Limpeza: {session_id} removido (restam: {len(active_sessions)})")


# ===== MIDDLEWARE DE ERRO GLOBAL (Exception Handler) =====

@app.exception_handler(QuintaFeirError)
async def quintafeira_exception_handler(request, exc: QuintaFeirError):
    """
    Catch de exceções do domínio (ToolNotFoundError, TerminalSecurityError, etc).
    
    Converte para resposta JSON amigável.
    """
    logger.error(f"[ERROR] {exc}")
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """
    Catch global de exceções inesperadas.
    
    Em produção, logging e monitoramento aqui.
    """
    logger.error(f"[CRITICAL] Exceção inesperada: {type(exc).__name__}: {exc}")
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

