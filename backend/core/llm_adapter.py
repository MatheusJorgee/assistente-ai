"""
LLM Adapter Pattern: Abstração de Modelos de Linguagem
Desacopla brain.py de Gemini específico, permitindo trocar para Ollama/Claude/OpenAI

Interface padrão para qualquer LLM:
- Suporte a tool_choice/function_calling
- Streaming responses
- Async/await ready
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncIterator
from dataclasses import dataclass
import asyncio


@dataclass
class LLMToolDefinition:
    """
    Definição de ferramenta limpa (compatível com qualquer LLM).
    CRÍTICO: Apenas JSON Schema puro, sem metadados Pydantic.
    """
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema puro: {type, properties, required, etc}
    
    def to_dict(self) -> Dict[str, Any]:
        """Exporta para formato JSON Schema limpo."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }


@dataclass
class LLMMessage:
    """Mensagem no contexto do LLM."""
    role: str  # "user", "assistant", "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None  # [{id, name, arguments}, ...]
    tool_result: Optional[str] = None  # Resultado da ferramenta


@dataclass
class LLMResponse:
    """Resposta do LLM."""
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None  # [{id, name, arguments}, ...]
    stop_reason: str = "end_turn"  # "end_turn" ou "tool_use"


class LLMAdapter(ABC):
    """
    Interface padrão para adaptadores de LLM.
    Implementar para cada modelo (Gemini, Ollama, Claude, OpenAI).
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Inicializa o cliente/conexão."""
        pass
    
    @abstractmethod
    async def send_message(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Envia mensagem para o LLM.
        
        Args:
            messages: Histórico de mensagens
            tools: Lista de ferramentas disponíveis
            temperature: Criatividade (0-1)
            max_tokens: Limite de tokens
            
        Returns:
            LLMResponse com resposta e/ou tool_calls
        """
        pass
    
    @abstractmethod
    async def stream_message(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        Streaming de resposta (para real-time).
        
        Yields:
            Chunks de texto conforme chegam
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Limpa recursos (conexão, etc)."""
        pass


class SchemaBuilder:
    """
    Construtor de schemas clean para Function Calling.
    Remove metadados Pydantic e gera JSON Schema puro.
    
    Critério: Apenas {name, type, description, properties, required} ✓
    Proibido: extra fields, PydanticModel fields, Pydantic decorators ✗
    """
    
    @staticmethod
    def build_parameter_schema(
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Constrói schema limpo para parâmetros.
        
        ENTRADA (antes):
        {
            "params": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Busca"
                    }
                },
                "extra_forbidden": True,  # ← PROBLEM!
                "model_config": {...}  ← PROBLEM!
            }
        }
        
        SAÍDA (depois):
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Busca"
                }
            },
            "required": ["query"]
        }
        """
        
        cleaned = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Copiar apenas campos válidos
        if "properties" in parameters:
            for prop_name, prop_schema in parameters["properties"].items():
                # Limpar cada propriedade recursivamente
                cleaned_prop = SchemaBuilder._clean_property(prop_schema)
                cleaned["properties"][prop_name] = cleaned_prop
        
        if "required" in parameters:
            cleaned["required"] = parameters["required"]
        
        return cleaned
    
    @staticmethod
    def _clean_property(prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Remove campos inválidos de uma propriedade."""
        allowed_keys = {
            "type", "description", "enum", "default",
            "items", "properties", "required", "minimum",
            "maximum", "pattern", "minLength", "maxLength",
            "format", "example"
        }
        
        cleaned = {
            k: v for k, v in prop_schema.items()
            if k in allowed_keys and v is not None
        }

        if cleaned.get("type") == "array" and "items" not in cleaned:
            cleaned["items"] = {"type": "string"}

        return cleaned
    
    @staticmethod
    def build_tool_definition(
        name: str,
        description: str,
        parameters: Dict[str, Any]
    ) -> LLMToolDefinition:
        """
        Factory para construir LLMToolDefinition limpo.
        """
        cleaned_params = SchemaBuilder.build_parameter_schema(parameters)
        
        return LLMToolDefinition(
            name=name,
            description=description,
            parameters=cleaned_params
        )


class FunctionCallingOrchestrator:
    """
    Orquestrador do loop de Function Calling.
    
    Flow:
    1. Brain envia mensagem com tools disponíveis
    2. LLM retorna tool_calls (ex: {id, name, arguments})
    3. Orquestrador executa ferramentas
    4. Retorna resultados para LLM
    5. LLM processa e responde final
    """
    
    def __init__(self, llm_adapter: LLMAdapter, tool_registry: Any):
        """
        Args:
            llm_adapter: Implementação do LLMAdapter
            tool_registry: ToolRegistry com ferramentas registradas
        """
        self.llm = llm_adapter
        self.registry = tool_registry
        self.max_iterations = 10  # Prevenir loops infinitos
    
    async def process_with_tools(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDefinition]] = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Processa mensagem com tool calling automático.
        
        Returns:
            Resposta final do LLM (após executar ferramentas se necessário)
        """
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # 1️⃣ Enviar para LLM com ferramentas
            response = await self.llm.send_message(
                messages=messages,
                tools=tools,
                temperature=temperature
            )
            
            # 2️⃣ Se não tem tool_calls, retorna resposta final
            if not response.tool_calls or response.stop_reason == "end_turn":
                return response
            
            # 3️⃣ Executar ferramentas
            for tool_call in response.tool_calls:
                tool_result = await self._execute_tool_call(tool_call)
                
                # Adicionar resultado ao histórico
                messages.append(LLMMessage(
                    role="tool",
                    tool_result=tool_result,
                    content=None
                ))
            
            # 4️⃣ Adicionar resposta do assistant ao histórico
            messages.append(LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls
            ))
        
        # Segurança: Se atingiu max_iterations
        return LLMResponse(
            content="Limite de iterações atingido. Encerrando loop de ferramentas.",
            tool_calls=None,
            stop_reason="end_turn"
        )
    
    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> str:
        """
        Executa uma chamada de ferramenta.
        
        Args:
            tool_call: {id, name, arguments}
            
        Returns:
            Resultado como string
        """
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        try:
            result = await self.registry.execute(tool_name, **arguments)
            return result
        except Exception as e:
            return f"[ERRO] Execução de {tool_name} falhou: {str(e)}"
