"""
process_manager.py - Gerenciador de Processos com Consciência de Contexto de Mídia

Responsável por:
1. Detectar processos em execução (navegadores, players, etc)
2. Rastrear contexto de mídia por aplicativo (música, vídeo, podcast)
3. Permitir controle granular de volume/pausa/play por processo
4. Observer pattern para monitorar mudanças

Padrões Arquiteturais:
- Observer: Notificações de mudanças de processo
- Registry: Registro central de processos conhecidos
- Context: Rastreamento de contexto por aplicativo
"""

import asyncio
import platform
import psutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MediaType(Enum):
    """Tipo de mídia sendo processada"""
    MUSIC = "music"
    VIDEO = "video"
    PODCAST = "podcast"
    STREAM = "stream"
    BROWSER_TAB = "browser_tab"
    UNKNOWN = "unknown"


class ProcessStatus(Enum):
    """Estado do processo"""
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    SUSPENDED = "suspended"


class BrowserType(Enum):
    """Tipos de navegador"""
    CHROME = "chrome"
    FIREFOX = "firefox"
    EDGE = "edge"
    BRAVE = "brave"
    OPERA = "opera"
    OTHER = "other"


@dataclass
class MediaContext:
    """Contexto de mídia para um processo"""
    media_type: MediaType
    title: str
    duration: Optional[int] = None  # segundos
    current_position: Optional[int] = None  # segundos
    is_playing: bool = False
    volume: int = 50  # 0-100
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self):
        return {
            "media_type": self.media_type.value,
            "title": self.title,
            "duration": self.duration,
            "current_position": self.current_position,
            "is_playing": self.is_playing,
            "volume": self.volume,
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class ProcessInfo:
    """Informações sobre um processo"""
    pid: int
    name: str
    description: str
    process_type: str  # "browser", "media_player", "stream", etc
    browser_type: Optional[BrowserType] = None
    media_context: Optional[MediaContext] = None
    status: ProcessStatus = ProcessStatus.RUNNING
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self):
        return {
            "pid": self.pid,
            "name": self.name,
            "description": self.description,
            "process_type": self.process_type,
            "browser_type": self.browser_type.value if self.browser_type else None,
            "media_context": self.media_context.to_dict() if self.media_context else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat()
        }


class ProcessObserver:
    """Observer para mudanças de processo"""
    
    async def on_process_started(self, process_info: ProcessInfo):
        """Chamado quando um novo processo é detectado"""
        pass
    
    async def on_process_stopped(self, pid: int):
        """Chamado quando um processo termina"""
        pass
    
    async def on_media_context_changed(self, pid: int, context: MediaContext):
        """Chamado quando o contexto de mídia muda"""
        pass


class ProcessManager:
    """Gerenciador central de processos com contexto de mídia"""
    
    def __init__(self):
        self.processes: Dict[int, ProcessInfo] = {}
        self.observers: List[ProcessObserver] = []
        self.browser_map = {
            "chrome.exe": BrowserType.CHROME,
            "firefox.exe": BrowserType.FIREFOX,
            "msedge.exe": BrowserType.EDGE,
            "brave.exe": BrowserType.BRAVE,
            "opera.exe": BrowserType.OPERA,
            "chromium.exe": BrowserType.CHROME,
        }
        self.media_player_keywords = [
            "spotify", "vlc", "itunes", "media player",
            "youtube", "netflix", "amazon prime", "twitch"
        ]
    
    # ============ Observables ============
    def add_observer(self, observer: ProcessObserver):
        """Adicionar observer para mudanças"""
        self.observers.append(observer)
    
    def remove_observer(self, observer: ProcessObserver):
        """Remover observer"""
        if observer in self.observers:
            self.observers.remove(observer)
    
    async def _notify_process_started(self, process_info: ProcessInfo):
        """Notificar todos os observers sobre novo processo"""
        for observer in self.observers:
            try:
                await observer.on_process_started(process_info)
            except Exception as e:
                logger.error(f"Erro ao notificar observer: {e}")
    
    async def _notify_process_stopped(self, pid: int):
        """Notificar todos os observers sobre processo parado"""
        for observer in self.observers:
            try:
                await observer.on_process_stopped(pid)
            except Exception as e:
                logger.error(f"Erro ao notificar observer: {e}")
    
    async def _notify_media_context_changed(self, pid: int, context: MediaContext):
        """Notificar todos os observers sobre mudança de contexto"""
        for observer in self.observers:
            try:
                await observer.on_media_context_changed(pid, context)
            except Exception as e:
                logger.error(f"Erro ao notificar observer: {e}")
    
    # ============ Detecção de Processos ============
    def detect_browser_type(self, process_name: str) -> Optional[BrowserType]:
        """Detectar tipo de navegador pelo nome do processo"""
        process_lower = process_name.lower()
        for exe_name, browser_type in self.browser_map.items():
            if exe_name in process_lower:
                return browser_type
        return None
    
    def is_media_player(self, process_name: str, process_desc: str = "") -> bool:
        """Verificar se é um media player conhecido"""
        combined = f"{process_name} {process_desc}".lower()
        return any(keyword in combined for keyword in self.media_player_keywords)
    
    async def scan_processes(self) -> Dict[int, ProcessInfo]:
        """Escanear todos os processos em execução e retornar mapeamento de PIDs"""
        new_processes = {}
        current_pids = set()
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    current_pids.add(proc.pid)
                    
                    # Ignorar processos já conhecidos
                    if proc.pid in self.processes:
                        new_processes[proc.pid] = self.processes[proc.pid]
                        continue
                    
                    process_name = proc.name()
                    process_exe = proc.exe() if proc.exe() else ""
                    
                    # Detectar tipo de processo
                    browser_type = self.detect_browser_type(process_name)
                    if browser_type:
                        process_info = ProcessInfo(
                            pid=proc.pid,
                            name=process_name,
                            description=f"{browser_type.value} browser - {process_exe}",
                            process_type="browser",
                            browser_type=browser_type
                        )
                        new_processes[proc.pid] = process_info
                        await self._notify_process_started(process_info)
                    
                    elif self.is_media_player(process_name, process_exe):
                        process_info = ProcessInfo(
                            pid=proc.pid,
                            name=process_name,
                            description=f"Media player - {process_exe}",
                            process_type="media_player"
                        )
                        new_processes[proc.pid] = process_info
                        await self._notify_process_started(process_info)
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        
        except Exception as e:
            logger.error(f"Erro ao escanear processos: {e}")
        
        # Detectar processos que pararam
        stopped_pids = set(self.processes.keys()) - current_pids
        for pid in stopped_pids:
            await self._notify_process_stopped(pid)
        
        self.processes = new_processes
        return new_processes
    
    # ============ Controle de Contexto de Mídia ============
    def set_media_context(self, pid: int, media_context: MediaContext):
        """Definir contexto de mídia para um processo"""
        if pid in self.processes:
            self.processes[pid].media_context = media_context
            asyncio.create_task(self._notify_media_context_changed(pid, media_context))
        else:
            logger.warning(f"PID {pid} não encontrado no registro de processos")
    
    def get_process_by_pid(self, pid: int) -> Optional[ProcessInfo]:
        """Obter informações de processo por PID"""
        return self.processes.get(pid)
    
    def get_processes_by_type(self, process_type: str) -> List[ProcessInfo]:
        """Obter todos os processos de um tipo específico"""
        return [p for p in self.processes.values() if p.process_type == process_type]
    
    def get_processes_by_browser_type(self, browser_type: BrowserType) -> List[ProcessInfo]:
        """Obter todos os processos de um navegador específico"""
        return [p for p in self.processes.values() if p.browser_type == browser_type]
    
    def get_processes_by_media_type(self, media_type: MediaType) -> List[ProcessInfo]:
        """Obter todos os processos que estão tocando um certo tipo de mídia"""
        return [
            p for p in self.processes.values()
            if p.media_context and p.media_context.media_type == media_type
        ]
    
    def get_active_media_processes(self) -> List[ProcessInfo]:
        """Obter todos os processos com mídia ativa (está tocando)"""
        return [
            p for p in self.processes.values()
            if p.media_context and p.media_context.is_playing
        ]
    
    # ============ Operações de Controle ============
    async def pause_process(self, pid: int) -> bool:
        """Pausar mídia em um processo específico"""
        process_info = self.get_process_by_pid(pid)
        if not process_info or not process_info.media_context:
            return False
        
        try:
            process_info.media_context.is_playing = False
            await self._notify_media_context_changed(pid, process_info.media_context)
            logger.info(f"Processo {pid} ({process_info.name}) pausado")
            return True
        except Exception as e:
            logger.error(f"Erro ao pausar processo {pid}: {e}")
            return False
    
    async def resume_process(self, pid: int) -> bool:
        """Retomar mídia em um processo específico"""
        process_info = self.get_process_by_pid(pid)
        if not process_info or not process_info.media_context:
            return False
        
        try:
            process_info.media_context.is_playing = True
            await self._notify_media_context_changed(pid, process_info.media_context)
            logger.info(f"Processo {pid} ({process_info.name}) retomado")
            return True
        except Exception as e:
            logger.error(f"Erro ao retomar processo {pid}: {e}")
            return False
    
    async def set_volume(self, pid: int, volume: int) -> bool:
        """Definir volume de um processo (0-100) - NOTA: Requer integração com pycaw"""
        if volume < 0 or volume > 100:
            logger.warning(f"Volume inválido: {volume}. Deve estar entre 0 e 100")
            return False
        
        process_info = self.get_process_by_pid(pid)
        if not process_info:
            return False
        
        try:
            if process_info.media_context:
                process_info.media_context.volume = volume
                await self._notify_media_context_changed(pid, process_info.media_context)
            logger.info(f"Volume do processo {pid} definido para {volume}%")
            return True
        except Exception as e:
            logger.error(f"Erro ao definir volume do processo {pid}: {e}")
            return False
    
    async def pause_by_browser_type(self, browser_type: BrowserType) -> int:
        """Pausar todos os processos de um navegador específico (ex: Brave)"""
        count = 0
        for process_info in self.get_processes_by_browser_type(browser_type):
            if await self.pause_process(process_info.pid):
                count += 1
        return count
    
    async def pause_by_media_type(self, media_type: MediaType) -> int:
        """Pausar todos os processos de um tipo de mídia específico (ex: MUSIC)"""
        count = 0
        for process_info in self.get_processes_by_media_type(media_type):
            if await self.pause_process(process_info.pid):
                count += 1
        return count
    
    async def pause_all_except(self, pid: int) -> int:
        """Pausar todos os processos com mídia ativa EXCETO um específico"""
        count = 0
        for process_info in self.get_active_media_processes():
            if process_info.pid != pid and await self.pause_process(process_info.pid):
                count += 1
        return count
    
    # ============ Informações e Status ============
    def get_all_processes(self) -> List[ProcessInfo]:
        """Obter todos os processos registrados"""
        return list(self.processes.values())
    
    def get_system_info(self) -> Dict:
        """Obter informações gerais do sistema"""
        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "total_processes": len(self.processes),
            "active_media_processes": len(self.get_active_media_processes()),
            "browsers_detected": len(self.get_processes_by_type("browser"))
        }
    
    def get_detailed_status(self) -> Dict:
        """Obter status detalhado de todos os processos"""
        return {
            "system": self.get_system_info(),
            "processes": [p.to_dict() for p in self.get_all_processes()],
            "active_media": [p.to_dict() for p in self.get_active_media_processes()],
            "timestamp": datetime.now().isoformat()
        }


# ============ Factory para criar instância global ============
_process_manager: Optional[ProcessManager] = None


def create_process_manager() -> ProcessManager:
    """Factory para criar/retornar instância global do ProcessManager"""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager


async def get_process_manager() -> ProcessManager:
    """Obter instância global do ProcessManager"""
    return create_process_manager()


if __name__ == "__main__":
    # Teste rápido
    import asyncio
    
    async def test():
        manager = create_process_manager()
        processes = await manager.scan_processes()
        print(f"Processos detectados: {len(processes)}")
        for pid, info in list(processes.items())[:5]:
            print(f"  - {info.name} (PID: {pid}, Type: {info.process_type})")
        
        status = manager.get_system_info()
        print(f"\nInfo do Sistema: {status}")
    
    asyncio.run(test())
