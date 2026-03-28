"""
Motor de Fila e Loop (Media Queue Management)
Implementa State Pattern para gerenciar estado de mídia e fila de reprodução.

Estados: Playing, Paused, Queued, LoopActive
Operações: add_to_queue, skip, toggle_loop, get_status
"""

import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any
from collections import deque
import json
from datetime import datetime


class MediaState(Enum):
    """Estados possíveis da mídia."""
    IDLE = "idle"  # Nenhuma mídia
    PLAYING = "playing"  # Tocando agora
    PAUSED = "paused"  # Pausada
    QUEUED = "queued"  # Na fila (waiting)
    LOOP_ACTIVE = "loop_active"  # Loop ligado


class LoopMode(Enum):
    """Modos de loop."""
    OFF = "off"  # Sem loop
    TRACK = "track"  # Repetir faixa
    PLAYLIST = "playlist"  # Repetir playlist


@dataclass
class MediaItem:
    """Representa uma faixa na fila."""
    id: str  # ID único (hash ou uuid)
    title: str
    artist: str
    source: str  # 'spotify', 'youtube', 'local'
    duration_ms: int = 0
    url: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'artist': self.artist,
            'source': self.source,
            'duration_ms': self.duration_ms,
            'url': self.url,
            'metadata': self.metadata,
            'added_at': self.added_at
        }


@dataclass
class MediaQueueStatus:
    """Status atual da fila."""
    current_state: MediaState
    current_playing: Optional[MediaItem] = None
    queue: List[MediaItem] = field(default_factory=list)
    loop_mode: LoopMode = LoopMode.OFF
    total_duration_ms: int = 0
    queue_size: int = 0
    
    def to_dict(self):
        return {
            'current_state': self.current_state.value,
            'current_playing': self.current_playing.to_dict() if self.current_playing else None,
            'queue': [item.to_dict() for item in self.queue],
            'loop_mode': self.loop_mode.value,
            'total_duration_ms': self.total_duration_ms,
            'queue_size': self.queue_size
        }


class MediaStateContext:
    """
    State Pattern Context para gerenciar transições de estado.
    Implementa máquina de estados para mídia.
    """
    
    def __init__(self, event_bus_callback: Optional[Callable] = None):
        """
        Args:
            event_bus_callback: Função para emitir eventos (async)
        """
        self._state = MediaState.IDLE
        self._current_item = None
        self._loop_mode = LoopMode.OFF
        self._event_bus = event_bus_callback
    
    async def _emit_event(self, event_type: str, data: Any = None):
        """Emitir evento via EventBus."""
        if self._event_bus:
            try:
                await self._event_bus(event_type, data)
            except Exception as e:
                print(f"[ERRO] Falha ao emitir evento {event_type}: {e}")
    
    @property
    def state(self) -> MediaState:
        return self._state
    
    @property
    def current_item(self) -> Optional[MediaItem]:
        return self._current_item
    
    @property
    def loop_mode(self) -> LoopMode:
        return self._loop_mode
    
    # Transições de Estado
    
    async def start_playing(self, item: MediaItem):
        """Iniciar reprodução de mídia."""
        self._state = MediaState.PLAYING
        self._current_item = item
        await self._emit_event('media_state_changed', {
            'state': self._state.value,
            'item': item.to_dict()
        })
    
    async def pause(self):
        """Pausar reprodução."""
        if self._state == MediaState.PLAYING:
            self._state = MediaState.PAUSED
            await self._emit_event('media_paused', {
                'item': self._current_item.to_dict() if self._current_item else None
            })
    
    async def resume(self):
        """Retomar reprodução."""
        if self._state == MediaState.PAUSED:
            self._state = MediaState.PLAYING
            await self._emit_event('media_resumed', {
                'item': self._current_item.to_dict() if self._current_item else None
            })
    
    async def set_queued(self, item: MediaItem):
        """Marcar item como na fila (waiting)."""
        if self._state in [MediaState.PLAYING, MediaState.PAUSED]:
            self._state = MediaState.QUEUED
            await self._emit_event('media_queued', {
                'item': item.to_dict()
            })
    
    async def toggle_loop(self, mode: Optional[LoopMode] = None):
        """Alternar modo de loop."""
        if mode:
            self._loop_mode = mode
        else:
            # Ciclar entre OFF -> TRACK -> PLAYLIST -> OFF
            modes = [LoopMode.OFF, LoopMode.TRACK, LoopMode.PLAYLIST]
            current_idx = modes.index(self._loop_mode)
            self._loop_mode = modes[(current_idx + 1) % len(modes)]
        
        self._state = MediaState.LOOP_ACTIVE if self._loop_mode != LoopMode.OFF else self._state
        
        await self._emit_event('loop_toggled', {
            'loop_mode': self._loop_mode.value
        })


class MediaQueue:
    """
    Gerenciador de fila de mídia com operações não-bloqueantes.
    """
    
    def __init__(self, max_queue_size: int = 100, event_bus_callback: Optional[Callable] = None):
        """
        Args:
            max_queue_size: Máximo de itens na fila
            event_bus_callback: Função para emitir eventos (async)
        """
        self.max_size = max_queue_size
        self._queue: deque = deque(maxlen=max_queue_size)
        self._event_bus = event_bus_callback
        self._state_context = MediaStateContext(event_bus_callback)
        self._lock = asyncio.Lock()  # Proteção contra race conditions
    
    async def _emit_event(self, event_type: str, data: Any = None):
        """Emitir evento via EventBus."""
        if self._event_bus:
            try:
                await self._event_bus(event_type, data)
            except Exception as e:
                print(f"[ERRO] Falha ao emitir evento {event_type}: {e}")
    
    async def add_to_queue(self, item: MediaItem, position: int = -1) -> bool:
        """
        Adiciona mídia à fila sem bloquear operações principais.
        
        Args:
            item: MediaItem a adicionar
            position: Posição na fila (-1 = final)
            
        Returns:
            True se adicionado com sucesso
        """
        async with self._lock:
            if len(self._queue) >= self.max_size:
                await self._emit_event('queue_full', {'attempted_item': item.to_dict()})
                return False
            
            if position == -1:
                self._queue.append(item)
            else:
                # Converter para lista, inserir, e reconstruir
                temp_list = list(self._queue)
                temp_list.insert(min(position, len(temp_list)), item)
                self._queue = deque(temp_list, maxlen=self.max_size)
            
            await self._emit_event('queue_item_added', {
                'item': item.to_dict(),
                'queue_size': len(self._queue)
            })
            
            return True
    
    async def skip_to_next(self) -> Optional[MediaItem]:
        """
        Pula para a próxima faixa na fila.
        
        Returns:
            Próximo MediaItem ou None se fila vazia
        """
        async with self._lock:
            if not self._queue:
                await self._emit_event('queue_empty')
                return None
            
            next_item = self._queue.popleft()
            await self._state_context.start_playing(next_item)
            await self._emit_event('skipped_to_next', {
                'item': next_item.to_dict(),
                'remaining_queue': len(self._queue)
            })
            
            return next_item
    
    async def remove_from_queue(self, item_id: str) -> bool:
        """
        Remove item específico da fila.
        
        Args:
            item_id: ID do item a remover
            
        Returns:
            True se removido
        """
        async with self._lock:
            original_size = len(self._queue)
            self._queue = deque(
                (item for item in self._queue if item.id != item_id),
                maxlen=self.max_size
            )
            
            removed = len(self._queue) < original_size
            if removed:
                await self._emit_event('queue_item_removed', {
                    'item_id': item_id,
                    'remaining_queue': len(self._queue)
                })
            
            return removed
    
    async def clear_queue(self):
        """Limpa toda a fila."""
        async with self._lock:
            self._queue.clear()
            await self._emit_event('queue_cleared')
    
    async def toggle_loop(self, mode: Optional[LoopMode] = None):
        """Alternar modo de loop."""
        await self._state_context.toggle_loop(mode)
    
    async def play_now(self, item: MediaItem):
        """Reproduzir imediatamente, inserindo no início da fila."""
        async with self._lock:
            await self._state_context.start_playing(item)
            await self._emit_event('play_now', {'item': item.to_dict()})
    
    async def get_status(self) -> MediaQueueStatus:
        """
        Obtém status completo da fila.
        
        Returns:
            MediaQueueStatus com estado atual
        """
        async with self._lock:
            total_duration = sum(item.duration_ms for item in self._queue)
            
            status = MediaQueueStatus(
                current_state=self._state_context.state,
                current_playing=self._state_context.current_item,
                queue=list(self._queue),
                loop_mode=self._state_context.loop_mode,
                total_duration_ms=total_duration,
                queue_size=len(self._queue)
            )
            
            return status
    
    async def persist_to_file(self, filepath: str):
        """
        Persiste fila em arquivo JSON.
        Útil para recuperar fila após reinicialização.
        """
        async with self._lock:
            status = await self.get_status()
            data = {
                'status': status.to_dict(),
                'saved_at': datetime.now().isoformat()
            }
            
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                await self._emit_event('queue_persisted', {'filepath': filepath})
            except Exception as e:
                print(f"[ERRO] Falha ao persistir fila: {e}")
    
    async def load_from_file(self, filepath: str) -> bool:
        """
        Carrega fila de arquivo JSON.
        
        Returns:
            True se carregado com sucesso
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            async with self._lock:
                self._queue.clear()
                
                queue_data = data.get('status', {}).get('queue', [])
                for item_dict in queue_data:
                    item = MediaItem(
                        id=item_dict['id'],
                        title=item_dict['title'],
                        artist=item_dict['artist'],
                        source=item_dict['source'],
                        duration_ms=item_dict.get('duration_ms', 0),
                        url=item_dict.get('url'),
                        metadata=item_dict.get('metadata', {})
                    )
                    self._queue.append(item)
                
                await self._emit_event('queue_loaded', {
                    'filepath': filepath,
                    'items_loaded': len(self._queue)
                })
                
                return True
        
        except Exception as e:
            print(f"[ERRO] Falha ao carregar fila: {e}")
            return False


def create_media_queue(max_size: int = 100, event_bus_callback: Optional[Callable] = None) -> MediaQueue:
    """
    Factory para criar MediaQueue.
    
    Args:
        max_size: Tamanho máximo da fila
        event_bus_callback: Callback para eventos (async)
        
    Returns:
        MediaQueue pronto para usar
    """
    return MediaQueue(max_size, event_bus_callback)
