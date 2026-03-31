"""
FastAPI Backend v2.1 - Quinta-Feira AI Assistant
Orquestrador Principal: WebSocket + REST API + Brain v2

Suporte a:
- WebSocket streaming com QuintaFeira Brain
- REST API tradicional
- CORS para localhost:3000
- Auto-reload com uvicorn
"""

import asyncio
import json
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ============ SETUP LOGGING ============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ===== OTIMIZAÇÃO DE LATÊNCIA: Desativar logs desnecessários ✓ NOVO =====
# Reduz consumo de memória e aumenta performance
logging.getLogger('httpx').setLevel(logging.WARNING)  # ← Silenciar logs de HTTP
logging.getLogger('google.genai').setLevel(logging.WARNING)  # ← Silenciar logs de Gemini
logging.getLogger('urllib3').setLevel(logging.WARNING)  # ← Silenciar logs de urllib3
logging.getLogger('googleapis').setLevel(logging.WARNING)  # ← Silenciar logs de Google APIs

# ============ IMPORTS CORE (COM FALLBACK) ============
try:
    from backend.brain_v2 import QuintaFeiraBrainV2
except (ImportError, ModuleNotFoundError):
    try:
        from brain_v2 import QuintaFeiraBrainV2
    except ImportError as e:
        logger.error(f"ERRO CRÍTICO: Não conseguiu importar QuintaFeiraBrainV2: {e}")
        QuintaFeiraBrainV2 = None

# ============ INSTÂNCIA GLOBAL DO BRAIN ============
brain: Optional[QuintaFeiraBrainV2] = None
startup_errors = []

async def initialize_brain():
    """Inicializa o Brain v2 na startup"""
    global brain, startup_errors
    try:
        logger.info("[INICIALIZANDO] Quinta-Feira Brain v2...")
        brain = QuintaFeiraBrainV2()
        logger.info("✓ [SISTEMA] Quinta-Feira Brain v2 Inicializada com sucesso")
        return True
    except Exception as e:
        error_msg = f"✗ [ERRO] Falha ao inicializar Brain: {str(e)}"
        logger.error(error_msg)
        startup_errors.append(str(e))
        return False

# ============ FAST API APP ============
app = FastAPI(
    title="Quinta-Feira AI",
    description="Backend para assistente de IA com controle por voz",
    version="2.1"
)

# ============ MIDDLEWARE CORS ============
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ ROTAS REST API ============

@app.on_event("startup")
async def startup_event():
    """Inicializar recursos na startup"""
    await initialize_brain()

@app.on_event("shutdown")
async def shutdown_event():
    """Limpar recursos na shutdown"""
    global brain
    if brain:
        logger.info("[SHUTDOWN] Finalizando Brain...")
        brain = None

@app.get("/health")
async def health_check():
    """Health check do backend"""
    return {
        "status": "healthy" if brain else "degraded",
        "brain_initialized": brain is not None,
        "timestamp": datetime.now().isoformat(),
        "startup_errors": startup_errors if startup_errors else None
    }

@app.get("/status")
async def status():
    """Status do sistema"""
    if not brain:
        return {
            "status": "not_initialized",
            "message": "Brain não foi inicializado",
            "errors": startup_errors
        }
    
    return {
        "status": "ready",
        "brain_version": "2.1",
        "tools_loaded": len(brain.tool_registry.get_all_tools()) if hasattr(brain, 'tool_registry') else 0,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/chat")
async def chat_rest(request: Dict[str, Any]):
    """Endpoint REST tradicional para chat"""
    if not brain:
        raise HTTPException(status_code=503, detail="Brain não inicializado")
    
    message = request.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    
    try:
        response = await brain.ask(message)
        return {
            "success": True,
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ WEBSOCKET ============

class ConnectionManager:
    """Gerenciador de conexões WebSocket"""
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"✓ Cliente conectado: {client_id}")
    
    async def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"✗ Cliente desconectado: {client_id}")
    
    async def send_personal(self, client_id: str, data: Dict[str, Any]):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(data)
            except Exception as e:
                logger.error(f"Erro ao enviar para {client_id}: {e}")
    
    async def broadcast(self, data: Dict[str, Any]):
        """Envia para todos os clientes conectados"""
        for client_id, connection in list(self.active_connections.items()):
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.error(f"Erro broadcast para {client_id}: {e}")

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket principal para comunicação com frontend"""
    client_id = f"client_{id(websocket)}"
    await manager.connect(websocket, client_id)
    
    try:
        if not brain:
            await websocket.send_json({
                "type": "error",
                "message": "Backend não inicializado",
                "errors": startup_errors
            })
            return
        
        while True:
            # Recebe mensagem do cliente
            data = await websocket.receive_text()
            
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_personal(client_id, {
                    "type": "error",
                    "message": "Formato inválido"
                })
                continue
            
            message_text = (
                payload.get("message") or 
                payload.get("payload") or 
                payload.get("text") or
                ""
            ).strip()
            
            # ===== V1 BARGE-IN: Handle interrupt =====
            if payload.get("type") == "interrupt":
                logger.info(f"[INTERRUPT] Recebido de {client_id}: {payload.get('reason', 'user_speech_detected')}")
                # TODO: Cancelar task de Brain ativa se houver
                # Por enquanto, enviar ACK
                await manager.send_personal(client_id, {
                    "type": "interrupt_ack",
                    "status": "interrupted",
                    "timestamp": datetime.now().isoformat()
                })
                continue
            
            if not message_text:
                continue
            
            logger.info(f"[MSG] {client_id}: {message_text}")
            
            try:
                # Processa com Brain v2
                response_json_str = await brain.ask(message_text)
                
                # Parse da resposta (brain retorna JSON com "text" e "audio")
                try:
                    response_data = json.loads(response_json_str)
                    texto_resposta = response_data.get("text", "")
                    audio_resposta = response_data.get("audio", "")
                except json.JSONDecodeError:
                    # Se não for JSON válido, tratar como texto puro
                    texto_resposta = response_json_str
                    audio_resposta = ""
                
                # ✓ ENVIAR SEPARADO: Texto primeiro (com heartbeat robusto)
                if texto_resposta:
                    # ✓ VALIDAÇÃO: Certificar que não há Base64 no texto
                    if texto_resposta.startswith("UklGR") or texto_resposta.startswith("SUQz"):
                        logger.error("[P0] BASE64 DETECTADO NO TEXTO! Bloqueando envio")
                        texto_resposta = "[ERRO] Base64 vazou no texto. Ativando apenas modo áudio."
                    
                    try:
                        await manager.send_personal(client_id, {
                            "type": "streaming",
                            "content": texto_resposta,
                            "timestamp": datetime.now().isoformat()
                        })
                    except RuntimeError as e:
                        logger.warning(f"[WEBSOCKET] Cliente {client_id} desconectou durante envio de texto: {e}")
                        return
                
                # ✓ ENVIAR SEPARADO: Áudio depois (se existir, com heartbeat robusto)
                if audio_resposta:
                    # ✓ VALIDAÇÃO: Certificar que é Base64 válido e começa com header correto
                    if audio_resposta and (audio_resposta.startswith("UklGR") or 
                                          audio_resposta.startswith("SUQz") or
                                          audio_resposta.startswith("ID3") or
                                          audio_resposta.startswith("/+MYxA")):
                        try:
                            await manager.send_personal(client_id, {
                                "type": "audio",
                                "audio": audio_resposta,
                                "timestamp": datetime.now().isoformat()
                            })
                        except RuntimeError as e:
                            logger.warning(f"[WEBSOCKET] Cliente {client_id} desconectou durante tarefa longa: {e}")
                            return
                    else:
                        logger.warning("[AUDIO] Formato inválido ou faltando header. Ignorando.")
                
                # ✓ ENVIAR SINAL DE CONCLUSÃO (com heartbeat robusto)
                try:
                    await manager.send_personal(client_id, {
                        "type": "complete",
                        "status": "completed",
                        "timestamp": datetime.now().isoformat()
                    })
                except RuntimeError as e:
                    logger.warning(f"[WEBSOCKET] Cliente {client_id} desconectou na conclusão: {e}")
                    return
                
            except Exception as e:
                logger.error(f"Erro ao processar mensagem: {e}", exc_info=True)
                await manager.send_personal(client_id, {
                    "type": "error",
                    "message": str(e)
                })
    
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"Erro WebSocket: {e}", exc_info=True)
        await manager.disconnect(client_id)

# ============ ROOT ============

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Quinta-Feira AI",
        "version": "2.1",
        "status": "online",
        "endpoints": {
            "ws": "/ws",
            "api": "/api/chat",
            "health": "/health",
            "status": "/status"
        }
    }

# ============ MAIN ============

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    
    logger.info(f"Iniciando servidor em {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
