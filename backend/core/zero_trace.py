"""
Zero-Trace Manager: Cleanup automático de recursos no WebSocket
Implementa Context Manager e Async Context Manager para garantir limpeza

Padrão: Context Manager + Resource Cleanup + Event Hooks
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any
from weakref import WeakSet

logger = logging.getLogger(__name__)


class Cleanable(ABC):
    """Interface para objetos que precisam de limpeza."""
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Executa limpeza de recursos."""
        pass


class AsyncResourceManager(Cleanable):
    """
    Gerenciador de recursos assíncrono.
    
    Rastreia objetos Cleanable e garante limpeza ao sair do contexto.
    
    Uso:
    async with AsyncResourceManager() as rm:
        browser = await create_browser()
        rm.track(browser)
        # ... usar browser ...
    # browser.cleanup() é chamado automaticamente
    """
    
    def __init__(self):
        self._resources: WeakSet[Cleanable] = WeakSet()
        self._cleanup_hooks: Dict[str, Callable] = {}
    
    def track(self, resource: Cleanable) -> None:
        """Rastreia um recurso para limpeza."""
        if not hasattr(resource, 'cleanup'):
            logger.warning(f"Recurso {resource} não implementa cleanup()")
            return
        self._resources.add(resource)
    
    def register_hook(self, name: str, hook: Callable) -> None:
        """
        Registra hook de limpeza customizado.
        
        Args:
            name: Nome único do hook
            hook: Função async (ou sync) a executar
        """
        self._cleanup_hooks[name] = hook
    
    async def cleanup(self) -> None:
        """Executa limpeza de todos os recursos rastreados."""
        logger.info("[Zero-Trace] Iniciando cleanup de recursos...")
        
        # 1. Executar hooks customizados
        for hook_name, hook in self._cleanup_hooks.items():
            try:
                logger.debug(f"[Cleanup Hook] {hook_name}")
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.error(f"[Cleanup Hook Error] {hook_name}: {e}")
        
        # 2. Limpeza de recursos rastreados
        for resource in list(self._resources):
            try:
                logger.debug(f"[Cleanup Resource] {resource.__class__.__name__}")
                if asyncio.iscoroutinefunction(resource.cleanup):
                    await resource.cleanup()
                else:
                    resource.cleanup()
            except Exception as e:
                logger.error(f"[Cleanup Error] {resource}: {e}")
        
        logger.info("[Zero-Trace] ✓ Cleanup concluído")
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit (sempre executa cleanup)."""
        await self.cleanup()
        return False


class WebSocketLifecycle:
    """
    Gerenciador de ciclo de vida de WebSocket.
    
    Responsabilidades:
    - Inicializar recursos na conexão
    - Rastrear sessão
    - Limpar na desconexão
    - Log tático de eventos
    """
    
    _active_sessions: WeakSet['WebSocketLifecycle'] = WeakSet()
    
    def __init__(self, session_id: str):
        """
        Args:
            session_id: ID único da sessão WebSocket
        """
        self.session_id = session_id
        self.resource_manager = AsyncResourceManager()
        self.is_active = False
        self._on_disconnect: Optional[Callable] = None
        
        logger.info(f"[WS Session] Nova sessão: {session_id}")
        self._active_sessions.add(self)
    
    async def on_connect(self) -> None:
        """Executado quando WebSocket conecta."""
        self.is_active = True
        logger.info(f"[WS Connected] {self.session_id}")
    
    async def on_disconnect(self) -> None:
        """Executado quando WebSocket desconecta (CRITICAL: Cleanup aqui)."""
        if not self.is_active:
            return
        
        self.is_active = False
        logger.info(f"[WS Disconnecting] {self.session_id}")
        
        # ✓ CRITICAL: Executar cleanup automaticamente
        await self.resource_manager.cleanup()
        
        # Executar callback de desconexão
        if self._on_disconnect:
            try:
                if asyncio.iscoroutinefunction(self._on_disconnect):
                    await self._on_disconnect()
                else:
                    self._on_disconnect()
            except Exception as e:
                logger.error(f"[WS Disconnect Handler Error] {e}")
        
        logger.info(f"[WS Disconnected] {self.session_id} - Todos recursos limpos")
    
    def set_disconnect_handler(self, handler: Callable) -> None:
        """Define callback a executar quando WebSocket desconecta."""
        self._on_disconnect = handler
    
    def track_resource(self, resource: Cleanable) -> None:
        """Rastreia recurso para limpeza automática."""
        self.resource_manager.track(resource)
    
    def register_cleanup_hook(self, name: str, hook: Callable) -> None:
        """Registra hook de limpeza customizado."""
        self.resource_manager.register_hook(name, hook)
    
    @classmethod
    def get_active_sessions(cls) -> int:
        """Retorna número de sessões ativas."""
        return len(cls._active_sessions)


class PlaywrightCleanable(Cleanable):
    """Wrapper para Playwright browser com cleanup."""
    
    def __init__(self, browser, context=None, page=None):
        self.browser = browser
        self.context = context
        self.page = page
    
    async def cleanup(self) -> None:
        """Fecha Playwright em ordem correta."""
        logger.info("[Playwright Cleanup] Iniciando...")
        
        try:
            if self.page:
                await self.page.close()
                self.page = None
        except Exception as e:
            logger.warning(f"[Playwright] Erro ao fechar page: {e}")
        
        try:
            if self.context:
                await self.context.close()
                self.context = None
        except Exception as e:
            logger.warning(f"[Playwright] Erro ao fechar context: {e}")
        
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
        except Exception as e:
            logger.warning(f"[Playwright] Erro ao fechar browser: {e}")
        
        logger.info("[Playwright Cleanup] ✓ Concluído")


class LLMClientCleanable(Cleanable):
    """Wrapper para cliente LLM com cleanup."""
    
    def __init__(self, llm_adapter):
        """
        Args:
            llm_adapter: Implementação de LLMAdapter
        """
        self.llm_adapter = llm_adapter
    
    async def cleanup(self) -> None:
        """Limpa cliente LLM."""
        logger.info("[LLM Cleanup] Encerrando cliente...")
        try:
            await self.llm_adapter.cleanup()
        except Exception as e:
            logger.error(f"[LLM Cleanup Error] {e}")


class DatabaseCleanable(Cleanable):
    """Wrapper para banco de dados com cleanup."""
    
    def __init__(self, database):
        self.database = database
    
    async def cleanup(self) -> None:
        """Limpa conexão com banco."""
        logger.info("[Database Cleanup] Persistindo dados...")
        try:
            if hasattr(self.database, 'salvar'):
                self.database.salvar()
            elif hasattr(self.database, 'flush'):
                self.database.flush()
        except Exception as e:
            logger.error(f"[Database Cleanup Error] {e}")


class SessionResourceManager:
    """
    Gerenciador centralizado de all resources para uma sessão WebSocket.
    Integra: LLM, Browser, Database, Tools
    """
    
    def __init__(self, session_id: str, brain_instance):
        """
        Args:
            session_id: ID da sessão WebSocket
            brain_instance: Referência para QuintaFeiraBrainV2
        """
        self.lifecycle = WebSocketLifecycle(session_id)
        self.brain = brain_instance
        self.session_id = session_id
    
    async def initialize(self) -> None:
        """Inicializa todos os recursos da sessão."""
        await self.lifecycle.on_connect()
        
        # Rastrear recursos do brain
        if hasattr(self.brain, 'client'):
            self.lifecycle.track_resource(
                LLMClientCleanable(self.brain.client)
            )
        
        if hasattr(self.brain, 'db'):
            self.lifecycle.track_resource(
                DatabaseCleanable(self.brain.db)
            )
    
    async def cleanup(self) -> None:
        """Limpa todos os recursos da sessão."""
        await self.lifecycle.on_disconnect()
    
    def get_resource_manager(self) -> AsyncResourceManager:
        """Retorna o gerenciador de recursos para uso customizado."""
        return self.lifecycle.resource_manager
