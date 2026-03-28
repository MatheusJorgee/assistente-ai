"""
YouTube Loop Manager - Gerencia repetição de vídeos no YouTube
Implementa mecanismo para tocar música em loop no YouTube via browser automation
"""

import asyncio
import subprocess
import json
import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Callable, Any
from datetime import datetime


class YouTubeLoopMode(Enum):
    """Modos de repetição no YouTube."""
    OFF = "off"  # Sem repetição
    SINGLE = "single"  # Repetir uma faixa
    ALL = "all"  # Repetir playlist inteira
    SHUFFLE = "shuffle"  # Aleatória com repetição


@dataclass
class YouTubeVideo:
    """Representa um vídeo do YouTube."""
    video_id: str  # ID do vídeo (ex: dQw4w9WgXcQ)
    title: str
    duration_seconds: int = 0
    is_music: bool = True
    url: Optional[str] = None
    
    @property
    def full_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"
    
    @property
    def embed_url(self) -> str:
        return f"https://www.youtube.com/embed/{self.video_id}"


@dataclass
class LoopSession:
    """Sessão de loop no YouTube."""
    session_id: str
    video: YouTubeVideo
    loop_mode: YouTubeLoopMode
    browser_type: str  # 'chrome', 'firefox', 'edge'
    started_at: str
    loop_count: int = 0
    current_time_seconds: int = 0
    is_playing: bool = True


class YouTubeLoopManager:
    """
    Gerenciador de loops de vídeo no YouTube.
    Automatiza browser para repetir vídeos.
    """
    
    def __init__(self, event_bus_callback: Optional[Callable] = None):
        self.event_bus_callback = event_bus_callback
        self.active_sessions: dict[str, LoopSession] = {}
        self.browser_processes: dict[str, Any] = {}
    
    async def _emit_event(self, event_type: str, data: dict):
        """Emite evento no event bus."""
        if self.event_bus_callback:
            await self.event_bus_callback(event_type, data)
    
    async def extract_video_id(self, url_or_id: str) -> Optional[str]:
        """
        Extrai ID do vídeo de URL ou usa direto se já for ID.
        
        Args:
            url_or_id: URL do YouTube ou ID do vídeo
            
        Returns:
            ID do vídeo ou None se não conseguir extrair
        """
        # Se já é um ID válido (11 caracteres)
        if len(url_or_id) == 11 and url_or_id.replace('-', '').replace('_', '').isalnum():
            return url_or_id
        
        # Extrair de URL completa
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
            r'youtube\.com\/embed\/([^&\n?#]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)
        
        await self._emit_event('extract_video_id_failed', {'input': url_or_id})
        return None
    
    async def create_loop_session(
        self,
        video_url_or_id: str,
        title: str,
        loop_mode: YouTubeLoopMode = YouTubeLoopMode.SINGLE,
        browser_type: str = 'chrome'
    ) -> Optional[LoopSession]:
        """
        Cria uma nova sessão de loop.
        
        Args:
            video_url_or_id: URL ou ID do vídeo
            title: Título da música/vídeo
            loop_mode: Modo de repetição
            browser_type: Tipo de navegador (chrome, firefox, edge)
            
        Returns:
            LoopSession criada ou None se falhar
        """
        video_id = await self.extract_video_id(video_url_or_id)
        if not video_id:
            return None
        
        session_id = f"yt_loop_{datetime.now().timestamp()}"
        
        video = YouTubeVideo(
            video_id=video_id,
            title=title,
            url=f"https://www.youtube.com/watch?v={video_id}"
        )
        
        session = LoopSession(
            session_id=session_id,
            video=video,
            loop_mode=loop_mode,
            browser_type=browser_type,
            started_at=datetime.now().isoformat()
        )
        
        self.active_sessions[session_id] = session
        
        await self._emit_event('youtube_loop_session_created', {
            'session_id': session_id,
            'video_id': video_id,
            'title': title,
            'loop_mode': loop_mode.value,
            'browser': browser_type
        })
        
        return session
    
    async def start_loop(self, session_id: str) -> bool:
        """
        Inicia o loop em um navegador.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            True se iniciou com sucesso
        """
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        session.is_playing = True
        
        # Gerar URL com parâmetros para loop
        url = self._build_youtube_url_with_loop(session)
        
        await self._emit_event('youtube_loop_started', {
            'session_id': session_id,
            'video_id': session.video.video_id,
            'video_title': session.video.title,
            'loop_mode': session.loop_mode.value,
            'url': url
        })
        
        return True
    
    def _build_youtube_url_with_loop(self, session: LoopSession) -> str:
        """
        Constrói URL do YouTube com parâmetros de loop.
        O YouTube não suporta loop nativo via URL, mas a lógica fica aqui
        para controle automático via browser.
        
        Args:
            session: Sessão ativa
            
        Returns:
            URL construída
        """
        base_url = f"https://www.youtube.com/watch?v={session.video.video_id}"
        
        params = []
        
        # Parâmetro de autoplay
        params.append("autoplay=1")
        
        # Parâmetro de loop (alguns browsers/extensões suportam)
        if session.loop_mode == YouTubeLoopMode.SINGLE:
            params.append("loop=1")
        
        return base_url + "?" + "&".join(params) if params else base_url
    
    async def set_loop_mode(self, session_id: str, loop_mode: YouTubeLoopMode) -> bool:
        """
        Altera o modo de loop de uma sessão ativa.
        
        Args:
            session_id: ID da sessão
            loop_mode: Novo modo de loop
            
        Returns:
            True se conseguiu alterarStatus
        """
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        old_mode = session.loop_mode
        session.loop_mode = loop_mode
        
        await self._emit_event('youtube_loop_mode_changed', {
            'session_id': session_id,
            'old_mode': old_mode.value,
            'new_mode': loop_mode.value,
            'video_title': session.video.title
        })
        
        return True
    
    async def pause_loop(self, session_id: str) -> bool:
        """Pausa o loop."""
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        session.is_playing = False
        
        await self._emit_event('youtube_loop_paused', {'session_id': session_id})
        return True
    
    async def resume_loop(self, session_id: str) -> bool:
        """Retoma o loop."""
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        session.is_playing = True
        
        await self._emit_event('youtube_loop_resumed', {'session_id': session_id})
        return True
    
    async def stop_loop(self, session_id: str) -> bool:
        """Para e encerra a sessão de loop."""
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        
        await self._emit_event('youtube_loop_stopped', {
            'session_id': session_id,
            'video_title': session.video.title,
            'total_loops': session.loop_count
        })
        
        del self.active_sessions[session_id]
        return True
    
    async def get_active_sessions(self) -> List[LoopSession]:
        """Retorna todas as sessões ativas."""
        return list(self.active_sessions.values())
    
    async def get_session_status(self, session_id: str) -> Optional[dict]:
        """
        Obtém status de uma sessão.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            Dict com status ou None
        """
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        return {
            'session_id': session_id,
            'video_id': session.video.video_id,
            'title': session.video.title,
            'loop_mode': session.loop_mode.value,
            'is_playing': session.is_playing,
            'loop_count': session.loop_count,
            'current_time': session.current_time_seconds,
            'url': session.video.full_url,
            'started_at': session.started_at
        }


# Factory function
def create_youtube_loop_manager(event_bus_callback: Optional[Callable] = None) -> YouTubeLoopManager:
    """Cria uma nova instância do gerenciador de loops."""
    return YouTubeLoopManager(event_bus_callback)
