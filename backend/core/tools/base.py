"""
Motor Base Classes - Interface abstrata para ferramentas do Motor.

PadrÃµes:
- Strategy Pattern: Cada ferramenta Ã© intercambiÃ¡vel
- Registry Pattern: Descoberta dinÃ¢mica de ferramentas
- Template Method: Tool.safe_execute() valida antes de executar
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from datetime import datetime

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)


class SecurityLevel(Enum):
    """NÃ­veis de seguranÃ§a de uma ferramenta."""
    LOW = "low"              # Apenas logging
    MEDIUM = "medium"        # Requer confirmaÃ§Ã£o
    CRITICAL = "critical"    # Bloqueado por padrÃ£o


@dataclass
class ToolParameter:
    """DefiniÃ§Ã£o de um parÃ¢metro de ferramenta."""
    name: str
    type: str                  # "string", "int", "bool", "list"
    description: str
    required: bool = True
    default: Any = None
    choices: Optional[List[Any]] = None


@dataclass
class ToolMetadata:
    """Metadados de uma ferramenta."""
    name: str
    description: str
    category: str              # "terminal", "media", "system", "vision"
    parameters: List[ToolParameter] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    security_level: SecurityLevel = SecurityLevel.LOW
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """Resultado da execuÃ§Ã£o de uma ferramenta."""
    success: bool
    output: str
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=datetime.now().isoformat)


class MotorTool(ABC):
    """Interface base para todas as ferramentas do Motor."""
    
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata
        self._execution_count = 0
    
    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """
        Executa a ferramenta com os kwargs fornecidos.
        
        Args:
            **kwargs: Argumentos especÃ­ficos da ferramenta
        
        Returns:
            str: Resultado da execuÃ§Ã£o
        
        Raises:
            ValueError: Se os argumentos forem invÃ¡lidos
            RuntimeError: Se a execuÃ§Ã£o falhar
        """
        pass
    
    @abstractmethod
    def validate_input(self, **kwargs) -> bool:
        """
        Valida os parÃ¢metros antes de executar.
        
        Returns:
            bool: True se os parÃ¢metros sÃ£o vÃ¡lidos
        """
        pass
    
    async def safe_execute(self, **kwargs) -> ToolResult:
        """
        Executa a ferramenta com validaÃ§Ã£o e tratamento de erros.
        
        Template Method que:
        1. Valida entrada
        2. Registra inÃ­cio
        3. Executa
        4. Registra resultado
        """
        start_time = datetime.now()
        
        # 1. Validar entrada
        if not self.validate_input(**kwargs):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid input for {self.metadata.name}: {kwargs}"
            )
        
        try:
            # 2. Registrar inÃ­cio
            logger.info(f"[{self.metadata.category}] Iniciando: {self.metadata.name}")
            
            # 3. Executar
            output = await self.execute(**kwargs)
            
            # 4. Calcular duraÃ§Ã£o
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            self._execution_count += 1
            
            logger.info(f"[{self.metadata.category}] Completo: {self.metadata.name} ({duration_ms:.2f}ms)")
            
            return ToolResult(
                success=True,
                output=output,
                error=None,
                duration_ms=duration_ms,
            )
        
        except Exception as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            
            logger.error(f"[{self.metadata.category}] Erro em {self.metadata.name}: {error_msg}")
            
            return ToolResult(
                success=False,
                output="",
                error=error_msg,
                duration_ms=duration_ms,
            )
    
    def get_info(self) -> Dict[str, Any]:
        """Retorna informaÃ§Ãµes pÃºblicas sobre a ferramenta."""
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "category": self.metadata.category,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "choices": p.choices
                }
                for p in self.metadata.parameters
            ],
            "security_level": self.metadata.security_level.value,
            "version": self.metadata.version,
            "examples": self.metadata.examples,
            "execution_count": self._execution_count,
        }

    def get_parameters(self) -> Dict[str, Any]:
        """
        Converte metadados de parÃ¢metros para JSON Schema.

        Usado pelo adapter de LLM (Gemini) para function calling semÃ¢ntico.
        """
        type_map = {
            "string": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
        }

        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param in self.metadata.parameters:
            schema_type = type_map.get(param.type, "string")
            prop: Dict[str, Any] = {
                "type": schema_type,
                "description": param.description,
            }

            if schema_type == "array":
                item_type = "string"
                if isinstance(param.default, list) and param.default:
                    sample = param.default[0]
                    if isinstance(sample, bool):
                        item_type = "boolean"
                    elif isinstance(sample, int):
                        item_type = "integer"
                    elif isinstance(sample, float):
                        item_type = "number"
                    elif isinstance(sample, dict):
                        item_type = "object"
                prop["items"] = {"type": item_type}
            elif schema_type == "object":
                prop["properties"] = {}

            if param.choices:
                prop["enum"] = param.choices
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }


class ToolRegistry:
    """Registro dinÃ¢mico e descoberta de ferramentas."""
    
    def __init__(self):
        self._tools: Dict[str, MotorTool] = {}
        self._aliases: Dict[str, str] = {}  # alias -> nome real
    
    def register(self, tool: MotorTool, aliases: Optional[List[str]] = None) -> None:
        """
        Registra uma ferramenta no registry.
        
        Args:
            tool: InstÃ¢ncia de MotorTool
            aliases: Nomes alternativos para a ferramenta
        """
        tool_name = tool.metadata.name
        
        if tool_name in self._tools:
            logger.warning(f"Ferramenta '{tool_name}' jÃ¡ estÃ¡ registrada, sobrescrevendo...")
        
        self._tools[tool_name] = tool
        logger.info(f"Registrada ferramenta: {tool_name} ({tool.metadata.category})")
        
        # Registrar aliases
        if aliases:
            for alias in aliases:
                self._aliases[alias] = tool_name
                logger.debug(f"  â””â”€ Alias: {alias} â†’ {tool_name}")
    
    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Executa uma ferramenta pelo nome ou alias.
        
        Args:
            tool_name: Nome ou alias da ferramenta
            **kwargs: Argumentos para a ferramenta
        
        Returns:
            ToolResult com sucesso/erro
        """
        # Resolver alias
        real_name = self._aliases.get(tool_name, tool_name)
        
        if real_name not in self._tools:
            error_msg = f"Ferramenta nÃ£o encontrada: {tool_name}"
            logger.error(error_msg)
            return ToolResult(success=False, output="", error=error_msg)
        
        tool = self._tools[real_name]
        return await tool.safe_execute(**kwargs)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Lista todas as ferramentas registradas."""
        return [tool.get_info() for tool in self._tools.values()]
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Retorna informaÃ§Ãµes de uma ferramenta especÃ­fica."""
        real_name = self._aliases.get(tool_name, tool_name)
        
        if real_name in self._tools:
            return self._tools[real_name].get_info()
        
        return None
    
    def has_tool(self, tool_name: str) -> bool:
        """Verifica se uma ferramenta estÃ¡ registrada."""
        real_name = self._aliases.get(tool_name, tool_name)
        return real_name in self._tools

    def get_all_tools(self) -> List[MotorTool]:
        """Compatibilidade com Brain: retorna objetos de tool para schema LLM."""
        return list(self._tools.values())

