"""
CORE ARQUITETURAL: Tool Registry Pattern
Implementa a abstração de ferramentas com injeção de dependência.

Padrão: Strategy + Registry + Dependency Injection (DI Container)
Benefício: Adicionar novas ferramentas sem modificar brain.py
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass
import inspect
import asyncio


@dataclass
class ToolMetadata:
    """Metadados de uma ferramenta plug-in."""
    name: str
    description: str
    version: str = "1.0.0"
    tags: list[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class Tool(ABC):
    """
    Classe base para todas as ferramentas (Strategy Pattern).
    Cada ferramenta nova herda disto e implementa execute().
    
    Exemplo:
        class NotionTool(Tool):
            async def execute(self, **kwargs) -> str:
                # Sua lógica aqui
                pass
    """
    
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata
        self._event_bus: Optional['EventBus'] = None
    
    def set_event_bus(self, event_bus: 'EventBus'):
        """Setter para injetar o EventBus (DI)."""
        self._event_bus = event_bus
    
    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """
        Executa a ferramenta.
        
        Args:
            **kwargs: Parâmetros específicos da ferramenta
            
        Returns:
            str: Resultado da execução
        """
        pass
    
    @abstractmethod
    def validate_input(self, **kwargs) -> bool:
        """
        Valida entrada antes de executar.
        Override para adicionar validação específica.
        """
        pass
    
    async def safe_execute(self, **kwargs) -> str:
        """
        Wrapper seguro que:
        1. Valida entrada
        2. Loga início (via EventBus)
        3. Executa com tratamento de erro
        4. Loga resultado/erro
        """
        try:
            if not self.validate_input(**kwargs):
                return f"[ERRO] Validação falhou para {self.metadata.name}"
            
            if self._event_bus:
                self._event_bus.emit('tool_started', {
                    'tool_name': self.metadata.name,
                    'params': kwargs
                })
            
            result = await self.execute(**kwargs)
            
            if self._event_bus:
                self._event_bus.emit('tool_completed', {
                    'tool_name': self.metadata.name,
                    'result': result
                })
            
            return result
            
        except Exception as e:
            error_msg = f"[ERRO] {self.metadata.name} falhou: {str(e)}"
            if self._event_bus:
                self._event_bus.emit('tool_error', {
                    'tool_name': self.metadata.name,
                    'error': str(e)
                })
            return error_msg


class ToolRegistry:
    """
    Registry Pattern: Registra e gerencia ferramentas.
    Singleton por instância de brain.
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical_name
        self._event_bus: Optional['EventBus'] = None
    
    def set_event_bus(self, event_bus: 'EventBus'):
        """Injetar EventBus (DI)."""
        self._event_bus = event_bus
        # Propagar para todas as ferramentas registradas
        for tool in self._tools.values():
            tool.set_event_bus(event_bus)
    
    def register(self, tool: Tool, aliases: list[str] = None) -> None:
        """
        Registra uma ferramenta no padrão Registry.
        
        Args:
            tool: Instância da ferramenta (Tool)
            aliases: Nomes alternativos para a ferramenta
        """
        name = tool.metadata.name
        self._tools[name] = tool
        
        # Se injetamos EventBus antes, propagar para nova ferramenta
        if self._event_bus:
            tool.set_event_bus(self._event_bus)
        
        # Registrar aliases
        if aliases:
            for alias in aliases:
                self._aliases[alias] = name
        
        print(f"✓ Ferramenta registrada: {name}")
    
    async def execute(self, tool_name: str, **kwargs) -> str:
        """
        Executa uma ferramenta pelo nome ou alias.
        
        Args:
            tool_name: Nome ou alias da ferramenta
            **kwargs: Argumentos para a ferramenta
            
        Returns:
            str: Resultado da execução
        """
        canonical_name = self._aliases.get(tool_name, tool_name)
        
        if canonical_name not in self._tools:
            available = ", ".join(list(self._tools.keys())[:5])
            return f"[ERRO] Ferramenta '{tool_name}' não encontrada. Disponíveis: {available}"
        
        tool = self._tools[canonical_name]
        return await tool.safe_execute(**kwargs)
    
    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """Lista todas as ferramentas registradas com metadados."""
        return {
            name: {
                'description': tool.metadata.description,
                'version': tool.metadata.version,
                'tags': tool.metadata.tags
            }
            for name, tool in self._tools.items()
        }
    
    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Retorna a instância da ferramenta (para casos avançados)."""
        return self._tools.get(tool_name)


class EventBus:
    """
    Event Bus para sistema de logs táticos.
    Padrão: Publish-Subscribe (Observer)
    
    Eventos disponíveis:
    - tool_started: {tool_name, params}
    - tool_completed: {tool_name, result}
    - tool_error: {tool_name, error}
    - vision_captured: {monitor, dimensions, size_bytes}
    - action_terminal: {command, risk_level, result}
    - cortex_thinking: {step, reasoning}
    """
    
    def __init__(self):
        self._subscribers: Dict[str, list[Callable]] = {}
        self._event_buffer: list[Dict] = []  # Para debugging
        self._max_buffer_size = 1000
    
    def subscribe(self, event_type: str, callback: Callable) -> None:
        """
        Subscreve a um evento.
        
        Args:
            event_type: Tipo de evento (ex: 'tool_started', 'vision_captured')
            callback: Função/método a chamar quando o evento ocorrer
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Remove subscrição."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] 
                if cb != callback
            ]
    
    def emit(self, event_type: str, data: Dict = None) -> None:
        """
        Publica um evento para todos os subscritores.
        
        Args:
            event_type: Tipo do evento
            data: Dados do evento
        """
        if data is None:
            data = {}
        
        event = {'type': event_type, 'data': data}
        self._event_buffer.append(event)
        
        # Manter buffer gerenciável
        if len(self._event_buffer) > self._max_buffer_size:
            self._event_buffer.pop(0)
        
        # Invocar callbacks (pode ser async ou sync)
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(data))
                    else:
                        callback(data)
                except Exception as e:
                    print(f"[ERRO EventBus] Callback falhou: {e}")
    
    def get_events(self, event_type: str = None, limit: int = 50) -> list[Dict]:
        """
        Retorna eventos do buffer (para console/debug).
        
        Args:
            event_type: Filtrar por tipo (None = todos)
            limit: Número máximo de eventos
            
        Returns:
            List de eventos
        """
        if event_type:
            events = [e for e in self._event_buffer if e['type'] == event_type]
        else:
            events = self._event_buffer
        
        return events[-limit:] if limit else events
    
    def clear_buffer(self) -> None:
        """Limpa o buffer de eventos."""
        self._event_buffer.clear()


class DIContainer:
    """
    Dependency Injection Container (Singleton Pattern).
    Gerencia instâncias globais: ToolRegistry, EventBus, BaseDadosMemoria, etc.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._services: Dict[str, Any] = {}
        self._initialized = True
        
        # Instanciar serviços core
        self.event_bus = EventBus()
        self.tool_registry = ToolRegistry()
        self.tool_registry.set_event_bus(self.event_bus)
    
    def register_service(self, name: str, service: Any) -> None:
        """Registra um serviço no container."""
        self._services[name] = service
    
    def get_service(self, name: str) -> Optional[Any]:
        """Retorna uma instância de serviço."""
        return self._services.get(name)
    
    def get_all_services(self) -> Dict[str, Any]:
        """Retorna todos os serviços registrados."""
        return dict(self._services)


# Singleton global para fácil acesso
_di_container: Optional[DIContainer] = None

def get_di_container() -> DIContainer:
    """Factory para obter o DI Container (Singleton)."""
    global _di_container
    if _di_container is None:
        _di_container = DIContainer()
    return _di_container
