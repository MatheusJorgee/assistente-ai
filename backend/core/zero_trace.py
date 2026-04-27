"""
Zero-Trace Manager: Sandbox Isolado + Cleanup Automático de Recursos

Padrão: Context Manager + Resource Cleanup + Path Redirection

OBJETIVO: Permitir que o assistente rode em qualquer computador hospedeiro
sem deixar rastros permanentes (Zero-Trace Philosophy).

Implementa:
- ZeroTraceSession: Context manager que cria sandbox isolado (.runtime/sandbox/{session_id})
- SandboxPathRedirector: Silenciosamente redireciona writes para sandbox
- SandboxCleanable: Gerencia limpeza automática de pasta sandbox
- Integração com Circuit Breaker via PolicyViolationError
"""

import asyncio
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from weakref import WeakSet
import uuid

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


# ========== SANDBOX PATH REDIRECTION ==========
# Interceptor que silenciosamente redireciona paths para sandbox

class SandboxPathRedirector:
    """
    Rediretor de paths: silenciosamente redireciona writes para sandbox.
    
    Padrão: Proxy para operações de I/O
    
    Responsabilidades:
    - Interceptar tentativa de write em path arbitrary (ex: %TEMP%, %APPDATA%)
    - Redirecionar silenciosamente para sandbox (.runtime/sandbox/{session_id})
    - Preservar nome de arquivo (apenas muda pasta pai)
    
    Filosofia Zero-Trace:
    - Ferramenta tenta escrever em C:\\Users\\Admin\\Downloads\\report.pdf
    - Silenciosamente escreve em .runtime/sandbox/{session_id}/report.pdf
    - Ferramenta NÃO SABE que foi redirecionada
    - Cleanup ao final apaga .runtime/sandbox/{session_id}/ inteiramente
    
    Exemplo:
        redirector = SandboxPathRedirector(sandbox_root=Path('.runtime/sandbox/abc123'))
        
        # Tentativa de write fora do sandbox
        target = redirector.redirect_path(Path('C:/Users/Admin/file.txt'))
        # Retorna: Path('.runtime/sandbox/abc123/file.txt')
        
        # Write dentro do sandbox passa direto
        target = redirector.redirect_path(Path('.runtime/file.txt'))
        # Retorna: Path('.runtime/file.txt') [sem mudança]
    \"\"\"\n\n    def __init__(self, sandbox_root: Path):\n        \"\"\"        Args:\n            sandbox_root: Pasta raiz do sandbox (ex: .runtime/sandbox/{session_id})\n        \"\"\"\n        self.sandbox_root = sandbox_root.resolve()\n        self.sandbox_root.mkdir(parents=True, exist_ok=True)\n        logger.info(f\"[SandboxPathRedirector] Sandbox: {self.sandbox_root}\")\n    \n    def redirect_path(self, target: Path) -> Path:\n        \"\"\"\n        Redireciona path para sandbox se necessário.\n        \n        Lógica:\n        1. Se target já está dentro do sandbox: retorna unchanged\n        2. Se target está fora: redireciona para sandbox/{nome_arquivo}\n        3. Se target é relativa: resolve primeiro\n        \n        Args:\n            target: Path a verificar/redirecionar\n        \n        Returns:\n            Path final (pode ser sandbox-redirected)\n        \"\"\"\n        try:\n            resolved = target.expanduser().resolve()\n        except (ValueError, OSError):\n            # Path inválido (ex: se contains null bytes)\n            resolved = target\n        \n        # ✓ Verifica se target já está no sandbox\n        try:\n            resolved.relative_to(self.sandbox_root)\n            # Está no sandbox, retorna unchanged\n            logger.debug(f\"[Path] Inside sandbox: {resolved}\")\n            return resolved\n        except ValueError:\n            # Está fora do sandbox, redirecionar\n            pass\n        \n        # ✓ Redireciona para sandbox/{nome_arquivo}\n        redirected = self.sandbox_root / resolved.name\n        logger.debug(f\"[Path Redirect] {resolved} -> {redirected}\")\n        return redirected\n    \n    def is_in_sandbox(self, target: Path) -> bool:\n        \"\"\"Verifica se path está dentro do sandbox.\"\"\"\n        try:\n            resolved = target.expanduser().resolve()\n            resolved.relative_to(self.sandbox_root)\n            return True\n        except (ValueError, OSError):\n            return False


class SandboxCleanable(Cleanable):\n    \"\"\"Wrapper para sandbox folder com cleanup automático.\n    \n    Responsabilidade: Apagar a pasta sandbox inteiramente ao cleanup.\n    Objetivo Zero-Trace: Não deixa nenhum arquivo atrás no host.\n    \n    Uso (integrado com AsyncResourceManager):\n        async with AsyncResourceManager() as rm:\n            sandbox = SandboxCleanable(Path('.runtime/sandbox/abc123'))\n            rm.track(sandbox)\n            # ... operações com arquivos na sandbox ...\n        # sandbox_folder é deletada automaticamente!\n    \"\"\"\n    \n    def __init__(self, sandbox_path: Path):\n        self.sandbox_path = sandbox_path.resolve()\n    \n    async def cleanup(self) -> None:\n        \"\"\"Apaga pasta sandbox inteiramente (Zero-Trace).\"\"\"\n        if not self.sandbox_path.exists():\n            logger.debug(f\"[Sandbox Cleanup] Path não existe: {self.sandbox_path}\")\n            return\n        \n        logger.info(f\"[Sandbox Cleanup] Deletando: {self.sandbox_path}\")\n        try:\n            shutil.rmtree(str(self.sandbox_path))\n            logger.info(f\"[Sandbox Cleanup] ✓ Deletado: {self.sandbox_path}\")\n        except Exception as e:\n            logger.error(f\"[Sandbox Cleanup Error] Não conseguiu deletar {self.sandbox_path}: {e}\")\n            # Não propagar exceção, apenas log (cleanup best-effort)


class ZeroTraceSession:\n    \"\"\"        Context Manager para Zero-Trace Execution.\n        \n        Padrão: Context Manager + Sandbox + Cleanup\n        \n        Responsabilidades:\n        - Criar sandbox isolado ao entrar\n        - Prover path redirection durante execução\n        - Garantir cleanup (delete sandbox) ao sair\n        \n        Filosofia:\n        - Qualquer arquivo criado cai no sandbox\n        - Sandbox é deletado ao sair\n        - Host fica limpo (Zero-Trace)\n        - Integra com PolicyEngine + Circuit Breaker\n        \n        Uso:\n            async with ZeroTraceSession(session_id=\"req-123\") as session:\n                # session.sandbox_root = Path('.runtime/sandbox/req-123')\n                # session.redirector = SandboxPathRedirector(...)\n                \n                # ToolRegistry execute() vê PolicyEngine bloqueando format C:\n                # PolicyViolationError é lançado\n                # Circuit Breaker captura e trata\n                # Brain.ask_for_recovery() é chamado\n        \n        Ao sair: .runtime/sandbox/req-123/ é apagado (zero rastros)\n        \"\"\"\n    \n    def __init__(self, session_id: Optional[str] = None):\n        \"\"\"        Args:\n            session_id: Identificador da sessão (ex: \"req-123\", \"ws-abc\")\n                       Se None: gera UUID automático\n        \"\"\"\n        self.session_id = session_id or str(uuid.uuid4())[:8]\n        self.sandbox_root = Path('.runtime/sandbox') / self.session_id\n        self.redirector: Optional[SandboxPathRedirector] = None\n        self.resource_manager: Optional[AsyncResourceManager] = None\n        self._is_open = False\n        logger.info(f\"[ZeroTraceSession] Criado: {self.session_id}\")\n    \n    async def __aenter__(self):\n        \"\"\"Context manager entry: Inicializar sandbox.\"\"\"\n        self._is_open = True\n        \n        # ✓ Criar sandbox folder\n        self.sandbox_root.mkdir(parents=True, exist_ok=True)\n        logger.info(f\"[ZeroTraceSession] Sandbox inicializado: {self.sandbox_root}\")\n        \n        # ✓ Inicializar redirector\n        self.redirector = SandboxPathRedirector(self.sandbox_root)\n        \n        # ✓ Inicializar resource manager\n        self.resource_manager = AsyncResourceManager()\n        \n        # ✓ Rastrear sandbox para cleanup automático\n        sandbox_cleanable = SandboxCleanable(self.sandbox_root)\n        self.resource_manager.track(sandbox_cleanable)\n        \n        return self\n    \n    async def __aexit__(self, exc_type, exc_val, exc_tb):\n        \"\"\"Context manager exit: Cleanup sandbox (Zero-Trace).\"\"\"\n        if not self._is_open:\n            return False\n        \n        self._is_open = False\n        logger.info(f\"[ZeroTraceSession] Encerrando: {self.session_id}\")\n        \n        # ✓ Cleanup automático (apaga sandbox)\n        if self.resource_manager:\n            await self.resource_manager.cleanup()\n        \n        logger.info(f\"[ZeroTraceSession] ✓ Finalizado: {self.session_id}\")\n        return False\n    \n    def redirect_write(\n        self,\n        target_path: Path,\n    ) -> Path:\n        \"\"\"        Redireciona tentativa de write para sandbox.\n        \n        Padrão: Proxy + Interception\n        \n        Args:\n            target_path: Path que ferramenta quer escrever\n        \n        Returns:\n            Path final (pode ser redirected para sandbox)\n        \n        Exemplo:\n            session.redirect_write(Path('C:/Users/Admin/report.pdf'))\n            # Retorna: Path('.runtime/sandbox/req-123/report.pdf')\n        \"\"\"\n        if not self.redirector:\n            raise RuntimeError(\"ZeroTraceSession não foi inicializado (use async with)\")\n        \n        return self.redirector.redirect_path(target_path)\n    \n    def get_sandbox_path(self) -> Path:\n        \"\"\"Retorna pasta sandbox raiz.\"\"\"\n        return self.sandbox_root\n    \n    def get_session_id(self) -> str:\n        \"\"\"Retorna identificador da sessão.\"\"\"\n        return self.session_id


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
