"""
LLM_PROVIDER.PY - Interface Abstrata de Provedores de LLM
===========================================================

PADRÃO: Strategy Pattern + Dependency Inversion Principle (DIP)

INVERSÃO DE DEPENDÊNCIA EXPLICADA:

ANTES (Acoplamento ❌):
─────────────────────

    brain.py
    │
    └─ import google.genai
       │
       └─ if usar_gemini:
          │  gemini_client.models.generate_content(...)
          │
          └─ if usar_ollama: (seria outro código)
             ollama_client.generate(...)

Problema:
- Brain.py conhece TODAS as bibliotecas de LLM
- Adicionar Ollama = modificar brain.py
- Testar brain = precisa de google.genai instalado
- Impossível substituir por mock em testes


DEPOIS (Desacoplamento ✅):
──────────────────────────

    brain.py
    │
    └─ self.llm_provider  (abstrato, interface)
       │
       ├─ GeminiProvider (implementação)
       │  └─ usa google.genai internamente
       │
       ├─ OllamaProvider (futura)
       │  └─ usa requests para HTTP
       │
       └─ MockProvider (testes)
          └─ retorna respostas hardcoded

Brain.py NÃO conhece:
- google.genai
- requests
- Ollama
- Detalhes de HTTP

Brain.py CONHECE APENAS:
- Interface LLMProvider
- Métodos: generate(), stream(), supports_tools()
- Tipos: Message, Response


BENEFÍCIO CONCRETO:

Mudar de Gemini para Ollama:

    # Antes (acoplado):
    300+ linhas para refatorar brain.py

    # Depois (desacoplado):
    brain = QuintaFeiraBrain(
        llm_provider=OllamaProvider(base_url="http://ollama:11434")
    )
    # Pronto! Brain não mudou!


FLUXO DE DADOS COM INVERSÃO:

    Gateway (main.py)
    │
    ├─ create LLMProvider
    │  └─ GeminiAdapter(config)
    │
    ├─ create QuintaFeiraBrain
    │  └─ brain = QuintaFeiraBrain(llm_provider=adapter)
    │
    └─ awaitmessage do cliente
       │
       └─ brain.ask(message)
          │
          └─ llm_provider.generate(messages, tools)
             │
             ├─ Não importa se é Gemini, Ollama, etc
             ├─ Retorna sempre Response(text, tool_calls)
             └─ brain continua igual!
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, AsyncIterator
from enum import Enum


class ToolChoice(Enum):
    """Como o LLM deve usar ferramentas."""
    AUTO = "auto"              # LLM decide se quer usar tool
    REQUIRED = "required"      # Sempre deve usar uma tool
    NONE = "none"              # Nunca use tools


@dataclass
class Message:
    """Mensagem no contexto de conversa."""
    role: str                  # "user", "assistant", "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None  # [{id, name, arguments}]
    tool_result: Optional[str] = None
    tool_name: Optional[str] = None


@dataclass
class ToolDefinition:
    """Definição de ferramenta (compatível com qualquer LLM)."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema puro


@dataclass
class Response:
    """Resposta do LLM."""
    text: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    stop_reason: str = "end_turn"  # "end_turn" ou "tool_use"


class LLMProvider(ABC):
    """
    Interface abstrata para provedores de LLM.
    
    Qualquer LLM (Gemini, Ollama, Claude, etc) DEVE implementar estes métodos.
    
    Vantagem: Brain.py não precisa saber qual LLM está por trás.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Inicializa conexão com o LLM."""
        pass
    
    @abstractmethod
    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Response:
        """
        Gera resposta do LLM.
        
        Args:
            messages: Histórico de conversa
            tools: Ferramentas disponíveis
            temperature: Criatividade (0-1)
            max_tokens: Limite de tokens
            
        Returns:
            Response com texto e/ou tool_calls
            
        Implementadores devem:
            1. Convertir Message para formato nativo (ex: Gemini JSON)
            2. Convertir ToolDefinition para formato nativo
            3. Chamar API do LLM
            4. Parsear resposta para Message/Response
        """
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        Streaming de resposta (real-time, parecido com ChatGPT).
        
        Yields:
            Chunks de texto conforme chegam
        """
        pass
    
    def supports_tools(self) -> bool:
        """Retorna True se LLM suporta function calling."""
        return True
    
    def supports_vision(self) -> bool:
        """Retorna True se LLM suporta análise de imagens."""
        return False
    
    def name(self) -> str:
        """Nome amigável do LLM (ex: 'Gemini 2.5 Flash')."""
        return self.__class__.__name__


class FunctionCallingOrchestrator:
    """
    Orquestra o loop de Function Calling automático.
    
    FLUXO:
    1. Brain envia: mensages + tools
    2. LLM retorna: {"text": "", "tool_calls": [{name, arguments}]}
    3. Este orquestrador executa: tool_result = execute(tool_calls)
    4. Brain envia de volta: messasges + [tool_result]
    5. LLM final: gera resposta final sem tools
    
    Máx 10 iterações para evitar loop infinito.
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: Optional[Any] = None  # Será injetado ao registrar tools
    ):
        self.llm = llm_provider
        self.tool_registry = tool_registry
        self.max_iterations = 10
    
    async def process_with_tools(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
    ) -> Response:
        """
        Processa mensagem com função calling automático.
        
        Args:
            messages: Histórico
            tools: Ferramentas disponíveis
            temperature: Criatividade
            
        Returns:
            Response final (após executar ferramentas se necessário)
        """
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # 1. Perguntar LLM
            response = await self.llm.generate(
                messages=messages,
                tools=tools,
                temperature=temperature
            )
            
            # 2. Se não tem tool_calls, retorna
            if not response.tool_calls or response.stop_reason == "end_turn":
                return response
            
            # 3. Executar ferramentas
            for tool_call in response.tool_calls:
                tool_result = await self._execute_tool_call(tool_call)
                
                # Adicionar resultado ao histórico
                messages.append(Message(
                    role="tool",
                    tool_name=tool_call.get("name"),
                    tool_result=tool_result
                ))
            
            # 4. Adicionar resposta do LLM ao histórico
            messages.append(Message(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls
            ))
        
        # Timeout: atingiu max_iterations
        return Response(
            text="Limite de iterações atingido. Encerrando loop de ferramentas.",
            tool_calls=None,
            stop_reason="max_iterations"
        )
    
    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> str:
        """
        Executa uma chamada de ferramenta.
        
        Args:
            tool_call: {"name": "...", "arguments": {...}, ...}
            
        Returns:
            Resultado como string
        """
        if not self.tool_registry:
            return "[ERRO] Tool Registry não configurado"
        
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        try:
            result = await self.tool_registry.execute(tool_name, **arguments)

            # Compatibilidade com registries que retornam objeto ToolResult
            if hasattr(result, "success") and hasattr(result, "output"):
                success = bool(getattr(result, "success", False))
                output = str(getattr(result, "output", "") or "")
                error = str(getattr(result, "error", "") or "")
                if success:
                    return output
                return error or "[TOOL_ERROR] Execução sem detalhes de erro"

            return str(result)
        except Exception as e:
            return f"[ERRO ao executar {tool_name}]: {str(e)}"
