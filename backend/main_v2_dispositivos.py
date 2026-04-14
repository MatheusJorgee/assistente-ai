"""
main.py - FastAPI Backend v2.1+ com Device Routing

Funcionalidades:
1. API REST tradicional
2. WebSocket com suporte a múltiplos dispositivos
3. Device registry e roteamento
4. Process Manager para contexto de mídia
5. Streaming de respostas com markdown
6. Suporte a LAN (0.0.0.0:8000)

Padrões Arquiteturais:
- Registry: Registro de dispositivos conectados
- Observer: Notificações entre componentes
- Factory: Criação de device handlers
- Hub: Roteamento central de mensagens
"""

import asyncio
import json
import os
import uuid
import logging
from typing import Dict, Set, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# Importar módulos do projeto (com fallback)
try:
    from brain_v2 import QuintaFeiraBrain
except ImportError:
    QuintaFeiraBrain = None

try:
    from process_manager import create_process_manager, ProcessManager, MediaContext, MediaType
except ImportError:
    ProcessManager = None

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ============ Tipos e Enums ============

class DeviceType(Enum):
    """Tipos de dispositivos que podem se conectar"""
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"
    UNKNOWN = "unknown"


class MessageType(Enum):
    """Tipos de mensagens no protocolo"""
    CHAT = "chat"
    COMMAND = "command"
    DEVICE_REGISTER = "device_register"
    DEVICE_UNREGISTER = "device_unregister"
    PROCESS_CONTROL = "process_control"
    STATUS_REQUEST = "status_request"
    STREAM = "stream"
    ERROR = "error"


@dataclass
class Device:
    """Representação de um dispositivo conectado"""
    device_id: str
    device_type: DeviceType
    name: str
    ip_address: str
    connected_at: datetime
    last_activity: datetime
    websocket: Optional[WebSocket] = None
    
    def to_dict(self):
        return {
            "device_id": self.device_id,
            "device_type": self.device_type.value,
            "name": self.name,
            "ip_address": self.ip_address,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat()
        }


# ============ DeviceRegistry - Padrão Registry ============

class DeviceRegistry:
    """Registro central de dispositivos conectados"""
    
    def __init__(self):
        self.devices: Dict[str, Device] = {}
        self.device_connections: Dict[str, WebSocket] = {}  # device_id -> websocket
    
    def register_device(self, device: Device) -> str:
        """Register a new device"""
        self.devices[device.device_id] = device
        logger.info(f"Dispositivo registrado: {device.name} ({device.device_id})")
        return device.device_id
    
    def unregister_device(self, device_id: str) -> bool:
        """Unregister a device"""
        if device_id in self.devices:
            device = self.devices[device_id]
            del self.devices[device_id]
            if device_id in self.device_connections:
                del self.device_connections[device_id]
            logger.info(f"Dispositivo desregistrado: {device.name} ({device_id})")
            return True
        return False
    
    def get_device(self, device_id: str) -> Optional[Device]:
        """Get device by ID"""
        return self.devices.get(device_id)
    
    def get_all_devices(self) -> list[Device]:
        """Get all connected devices"""
        return list(self.devices.values())
    
    def get_devices_by_type(self, device_type: DeviceType) -> list[Device]:
        """Get devices of a specific type"""
        return [d for d in self.devices.values() if d.device_type == device_type]
    
    def store_websocket(self, device_id: str, websocket: WebSocket):
        """Store WebSocket connection for device"""
        self.device_connections[device_id] = websocket
    
    def get_websocket(self, device_id: str) -> Optional[WebSocket]:
        """Get WebSocket for device"""
        return self.device_connections.get(device_id)
    
    def update_activity(self, device_id: str):
        """Update last activity timestamp"""
        if device_id in self.devices:
            self.devices[device_id].last_activity = datetime.now()


# ============ Message Hub - Roteamento Central ============

class MessageHub:
    """Hub central para roteamento de mensagens entre dispositivos"""
    
    def __init__(self, registry: DeviceRegistry):
        self.registry = registry
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.subscriptions: Dict[str, Set[str]] = {}  # topic -> set of device_ids
    
    async def broadcast_to_device(self, device_id: str, message: dict):
        """Enviar mensagem para um dispositivo específico"""
        websocket = self.registry.get_websocket(device_id)
        if websocket:
            try:
                await websocket.send_json(message)
                self.registry.update_activity(device_id)
            except Exception as e:
                logger.error(f"Erro ao enviar para dispositivo {device_id}: {e}")
    
    async def broadcast_to_all(self, message: dict, exclude_device_id: Optional[str] = None):
        """Broadcast para todos os dispositivos"""
        for device in self.registry.get_all_devices():
            if exclude_device_id and device.device_id == exclude_device_id:
                continue
            await self.broadcast_to_device(device.device_id, message)
    
    async def broadcast_to_type(self, device_type: DeviceType, message: dict):
        """Broadcast para todos os dispositivos de um tipo"""
        for device in self.registry.get_devices_by_type(device_type):
            await self.broadcast_to_device(device.device_id, message)
    
    async def route_command(self, source_device_id: str, target_device_id: str, command: dict):
        """Rotear comando de um dispositivo para outro"""
        message = {
            "type": MessageType.COMMAND.value,
            "source_device_id": source_device_id,
            "command": command,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast_to_device(target_device_id, message)
    
    def subscribe(self, device_id: str, topic: str):
        """Subscribe device to topic"""
        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
        self.subscriptions[topic].add(device_id)
    
    def unsubscribe(self, device_id: str, topic: str):
        """Unsubscribe device from topic"""
        if topic in self.subscriptions:
            self.subscriptions[topic].discard(device_id)


# ============ FastAPI App Setup ============

app = FastAPI(
    title="Quinta-Feira v2.1+ com Device Hub",
    description="Backend com suporte a múltiplos dispositivos via LAN",
    version="2.1.0"
)

# Configuração de CORS para LAN
def _parse_allowed_origins() -> list[str]:
    """Parse CORS origins from env"""
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


ALLOWED_ORIGINS = _parse_allowed_origins()
ALLOW_CREDENTIALS = os.getenv("ALLOW_CREDENTIALS", "false").lower() == "true"

# Middleware para CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # LAN access - requer validação em produção
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware para trusted hosts (LAN)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.local"]  # Adicionar IPs da LAN em produção
)

# ============ Global State ============

brain: Optional[QuintaFeiraBrain] = None
process_manager: Optional[ProcessManager] = None
device_registry: DeviceRegistry = DeviceRegistry()
message_hub: MessageHub = MessageHub(device_registry)


async def initialize_services():
    """Inicializar serviços no startup"""
    global brain, process_manager
    
    logger.info("Inicializando serviços...")
    
    # Inicializar Brain
    if QuintaFeiraBrain:
        brain = QuintaFeiraBrain()
        logger.info("✅ QuintaFeiraBrain inicializado")
    else:
        logger.warning("⚠️ QuintaFeiraBrain não disponível")
    
    # Inicializar ProcessManager
    if ProcessManager:
        process_manager = create_process_manager()
        await process_manager.scan_processes()
        logger.info(f"✅ ProcessManager inicializado ({len(process_manager.get_all_processes())} processos)")
    else:
        logger.warning("⚠️ ProcessManager não disponível")


@app.on_event("startup")
async def startup_event():
    """Executar ao iniciar o servidor"""
    await initialize_services()
    logger.info("🚀 Backend Quinta-Feira iniciado com sucesso")


@app.on_event("shutdown")
async def shutdown_event():
    """Executar ao desligar o servidor"""
    logger.info("🛑 Backend Quinta-Feira desligando")
    # Cleanup se necessário
    device_registry.devices.clear()
    device_registry.device_connections.clear()


# ============ REST API Endpoints ============

@app.get("/api/health")
async def health_check():
    """Health check do servidor"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "2.1.0",
        "services": {
            "brain": "ready" if brain else "unavailable",
            "process_manager": "ready" if process_manager else "unavailable"
        }
    }


@app.get("/api/devices")
async def list_devices():
    """Listar todos os dispositivos conectados"""
    return {
        "devices": [d.to_dict() for d in device_registry.get_all_devices()],
        "total": len(device_registry.devices)
    }


@app.get("/api/devices/{device_id}")
async def get_device(device_id: str):
    """Obter informações de um dispositivo específico"""
    device = device_registry.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    return device.to_dict()


@app.post("/api/devices/register")
async def register_device(device_name: str, device_type: str):
    """Registrar um novo dispositivo"""
    device_id = str(uuid.uuid4())
    
    try:
        dev_type = DeviceType(device_type)
    except ValueError:
        dev_type = DeviceType.UNKNOWN
    
    device = Device(
        device_id=device_id,
        device_type=dev_type,
        name=device_name,
        ip_address="0.0.0.0",  # Será atualizado no WebSocket
        connected_at=datetime.now(),
        last_activity=datetime.now()
    )
    
    device_registry.register_device(device)
    
    return {
        "device_id": device_id,
        "message": f"Dispositivo '{device_name}' registrado com sucesso"
    }


@app.get("/api/processes")
async def get_processes():
    """Obter lista de processos com contexto de mídia"""
    if not process_manager:
        raise HTTPException(status_code=503, detail="ProcessManager não disponível")
    
    await process_manager.scan_processes()
    
    return {
        "processes": [p.to_dict() for p in process_manager.get_all_processes()],
        "active_media": [p.to_dict() for p in process_manager.get_active_media_processes()],
        "system": process_manager.get_system_info()
    }


@app.post("/api/process/{pid}/pause")
async def pause_process(pid: int):
    """Pausar mídia em um processo específico"""
    if not process_manager:
        raise HTTPException(status_code=503, detail="ProcessManager não disponível")
    
    result = await process_manager.pause_process(pid)
    if not result:
        raise HTTPException(status_code=404, detail=f"Processo {pid} não encontrado")
    
    # Broadcast para todos os dispositivos
    await message_hub.broadcast_to_all({
        "type": "process_paused",
        "pid": pid,
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "paused", "pid": pid}


@app.post("/api/process/{pid}/resume")
async def resume_process(pid: int):
    """Retomar mídia em um processo específico"""
    if not process_manager:
        raise HTTPException(status_code=503, detail="ProcessManager não disponível")
    
    result = await process_manager.resume_process(pid)
    if not result:
        raise HTTPException(status_code=404, detail=f"Processo {pid} não encontrado")
    
    await message_hub.broadcast_to_all({
        "type": "process_resumed",
        "pid": pid,
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "resumed", "pid": pid}


# ============ WebSocket Endpoints ============

@app.websocket("/api/chat/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket para chat com streaming de respostas em markdown
    Compatível com frontend v2.1+
    """
    await websocket.accept()
    device_id = str(uuid.uuid4())
    
    # Construir dispositivo a partir do WebSocket
    client_host = websocket.client[0] if websocket.client else "unknown"
    device = Device(
        device_id=device_id,
        device_type=DeviceType.DESKTOP,
        name=f"Chat Client - {client_host}",
        ip_address=client_host,
        connected_at=datetime.now(),
        last_activity=datetime.now(),
        websocket=websocket
    )
    
    device_registry.register_device(device)
    device_registry.store_websocket(device_id, websocket)
    
    logger.info(f"Cliente conectado: {device_id} ({client_host})")
    
    try:
        while True:
            data = await websocket.receive_json()
            
            message = data.get("message", "")
            user_id = data.get("user_id", device_id)
            
            device_registry.update_activity(device_id)
            
            if not message.strip():
                await websocket.send_json({
                    "type": "error",
                    "message": "Mensagem vazia"
                })
                continue
            
            # Enviar resposta em streaming
            if brain:
                try:
                    # Obter resposta do brain
                    response = await asyncio.to_thread(brain.ask, message)
                    
                    # Parsear resposta JSON
                    try:
                        response_data = json.loads(response)
                        response_text = response_data.get("text", response)
                    except:
                        response_text = response
                    
                    # Enviar em chunks (streaming)
                    for i in range(0, len(response_text), 50):
                        chunk = response_text[i:i+50]
                        await websocket.send_json({
                            "type": "streaming",
                            "content": chunk
                        })
                        await asyncio.sleep(0.05)  # Pequeno delay para efeito de digitação
                    
                    # Finalizar
                    await websocket.send_json({
                        "type": "complete",
                        "timestamp": datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    logger.error(f"Erro ao processar mensagem: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Brain não disponível"
                })
    
    except WebSocketDisconnect:
        device_registry.unregister_device(device_id)
        logger.info(f"Cliente desconectado: {device_id}")
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")
        device_registry.unregister_device(device_id)


@app.websocket("/api/device/{device_id}/ws")
async def websocket_device(websocket: WebSocket, device_id: str):
    """
    WebSocket para dispositivo específico com suporte a device routing
    Permite comunicação inter-device
    """
    device = device_registry.get_device(device_id)
    if not device:
        await websocket.close(code=1008, reason="Device not registered")
        return
    
    await websocket.accept()
    device_registry.store_websocket(device_id, websocket)
    device.websocket = websocket
    
    logger.info(f"Dispositivo WebSocket conectado: {device_id}")
    
    # Notificar outros dispositivos
    await message_hub.broadcast_to_all({
        "type": "device_connected",
        "device": device.to_dict()
    }, exclude_device_id=device_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            message_type = data.get("type", MessageType.CHAT.value)
            
            device_registry.update_activity(device_id)
            
            # Processador de diferentes tipos de mensagens
            if message_type == MessageType.COMMAND.value:
                # Roteamento de comando para outro dispositivo
                target_device_id = data.get("target_device_id")
                command = data.get("command")
                
                if target_device_id:
                    await message_hub.route_command(device_id, target_device_id, command)
                    logger.info(f"Comando roteado: {device_id} -> {target_device_id}")
            
            elif message_type == MessageType.PROCESS_CONTROL.value:
                # Controle de processo
                action = data.get("action")
                pid = data.get("pid")
                
                if process_manager and action and pid:
                    if action == "pause":
                        await process_manager.pause_process(pid)
                    elif action == "resume":
                        await process_manager.resume_process(pid)
                    elif action == "set_volume":
                        volume = data.get("volume", 50)
                        await process_manager.set_volume(pid, volume)
    
    except WebSocketDisconnect:
        device_registry.unregister_device(device_id)
        
        # Notificar outros dispositivos
        await message_hub.broadcast_to_all({
            "type": "device_disconnected",
            "device_id": device_id
        })
        
        logger.info(f"Dispositivo WebSocket desconectado: {device_id}")
    except Exception as e:
        logger.error(f"Erro no device WebSocket: {e}")


# ============ Main ============

if __name__ == "__main__":
    import uvicorn
    
    # Obter host e porta das variáveis de ambiente
    host = os.getenv("HOST", "0.0.0.0")  # 0.0.0.0 para expor para LAN
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"🚀 Iniciando Quinta-Feira em {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        debug=debug,
        log_level="info"
    )
