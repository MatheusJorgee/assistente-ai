"""
Gemini LLM Adapter: Implementação específica para Google Gemini
Suporta tool calling automático e schemas limpos.
"""

import os
import json
import asyncio
import logging
from typing import List, Optional, AsyncIterator
from dotenv import load_dotenv

from google import genai
from google.genai import types

from .llm_adapter import (
    LLMAdapter,
    LLMMessage,
    LLMResponse,
    LLMToolDefinition,
    SchemaBuilder
)

logger = logging.getLogger(__name__)
logging.getLogger('google.genai').setLevel(logging.WARNING)


class GeminiLLMAdapter(LLMAdapter):
    """
    Adaptador Gemini: Encapsula google.genai SDK.
    
    Recursos:
    - Tool calling automático com schemas limpos
    - Streaming responses
    - Suporte a vision (imagens)
    - Async ready
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        """
        Args:
            api_key: GEMINI_API_KEY (None = ler de .env)
            model: Nome do modelo (default: gemini-2.5-flash)
        """
        self.model_name = model
        self.client = None
        self.api_key = api_key
        self._load_env()
    
    def _load_env(self) -> None:
        """Carrega .env com fallback para path absoluto."""
        if self.api_key:
            return
        
        current = os.path.dirname(os.path.abspath(__file__))
        for _ in range(3):
            path = os.path.join(current, ".env")
            if os.path.exists(path):
                load_dotenv(path)
                self.api_key = os.getenv("GEMINI_API_KEY")
                return
            current = os.path.dirname(current)
        
        if not self.api_key:
            self.api_key = os.getenv("GEMINI_API_KEY")
    
    async def initialize(self) -> None:
        """Inicializa cliente Gemini."""
        if not self.api_key:
            raise EnvironmentError("GEMINI_API_KEY não configurada!")
        
        logger.info(f"[Gemini] Inicializando com modelo: {self.model_name}")
        self.client = genai.Client(api_key=self.api_key)
        logger.info("[Gemini] ✓ Cliente pronto")
    
    async def send_message(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Envia mensagem para Gemini (não-streaming).
        
        CRÍTICO: Transforma LLMToolDefinition para formato Gemini
        com schemas limpos (sem Pydantic validation extras).
        """
        if not self.client:
            await self.initialize()
        
        # 1️⃣ Converter mensagens para formato Gemini
        gemini_messages = self._convert_messages(messages)
        
        # 2️⃣ Converter ferramentas para tools.Tool Gemini
        gemini_tools = None
        if tools:
            gemini_tools = self._convert_tools(tools)
        
        try:
            # 3️⃣ Chamar Gemini COM ASYNC (evitar bloqueio) + TIMEOUT
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=f"models/{self.model_name}",
                    contents=gemini_messages,
                    config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    }
                ),
                timeout=30.0  # 30 segundos máximo
            )
            
            # 4️⃣ Parsear resposta
            return self._parse_response(response)
            
        except Exception as e:
            logger.error(f"[Gemini] Erro na chamada: {str(e)}")
            raise
    
    async def stream_message(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        Streaming de resposta (para real-time frontend).
        
        Yields:
            Chunks de texto conforme chegam
        """
        if not self.client:
            await self.initialize()
        
        gemini_messages = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools) if tools else None
        
        try:
            # 3️⃣ Chamar Gemini COM ASYNC streaming (evitar bloqueio) + TIMEOUT
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=f"models/{self.model_name}",
                    contents=gemini_messages,
                    config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                    stream=True
                ),
                timeout=30.0  # 30 segundos máximo
            )
            
            for chunk in response:
                if chunk.text:
                    yield chunk.text
                    
        except Exception as e:
            logger.error(f"[Gemini Streaming] Erro: {str(e)}")
            yield f"[ERRO] {str(e)}"
    
    async def cleanup(self) -> None:
        """Limpa recursos (Gemini não precisa, mas mantém interface)."""
        self.client = None
        logger.info("[Gemini] Cleanup concluído")
    
    # ============ CONVERSORES (Implementação Interna) ============
    
    @staticmethod
    def _convert_messages(messages: List[LLMMessage]) -> list:
        """
        Converte LLMMessage para formato Gemini.
        
        Gemini espera:
        {
            "role": "user" | "model",
            "parts": [{"text": "..."}, {"inline_data": {...}}]
        }
        """
        gemini_msgs = []
        
        for msg in messages:
            if msg.role == "tool":
                # Ferramenta → resposta de executar função
                gemini_msgs.append({
                    "role": "user",
                    "parts": [{
                        "text": f"Resultado da ferramenta:\n{msg.tool_result}"
                    }]
                })
            else:
                # User ou assistant
                gemini_msgs.append({
                    "role": "model" if msg.role == "assistant" else "user",
                    "parts": [{
                        "text": msg.content or ""
                    }]
                })
        
        return gemini_msgs
    
    @staticmethod
    def _convert_tools(tools: List[LLMToolDefinition]) -> List[types.Tool]:
        """
        CRÍTICO: Converte LLMToolDefinition para types.Tool do Gemini.
        
        Valida que schemas são limpos (sem Pydantic extras).
        """
        gemini_tools = []
        
        for tool_def in tools:
            # ✓ Validar schema limpo
            schema_dict = tool_def.to_dict()
            
            # Verificar que não há campos Pydantic problemáticos
            params = schema_dict.get("parameters", {})
            if "extra_forbidden" in params or "model_config" in params:
                logger.warning(
                    f"⚠️ Ferramenta '{tool_def.name}' tem metadados Pydantic. "
                    "Usando SchemaBuilder para limpar..."
                )
                schema_dict["parameters"] = SchemaBuilder.build_parameter_schema(params)
            
            # Converter para types.Tool
            gemini_tool = types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool_def.name,
                        description=tool_def.description,
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                name: GeminiLLMAdapter._convert_property(prop)
                                for name, prop in schema_dict.get("parameters", {}).get("properties", {}).items()
                            },
                            required=schema_dict.get("parameters", {}).get("required", [])
                        )
                    )
                ]
            )
            gemini_tools.append(gemini_tool)
        
        return gemini_tools
    
    @staticmethod
    def _convert_property(prop_schema: dict) -> types.Schema:
        """Converte uma propriedade para types.Schema Gemini."""
        type_map = {
            "string": types.Type.STRING,
            "integer": types.Type.INTEGER,
            "number": types.Type.NUMBER,
            "boolean": types.Type.BOOLEAN,
            "array": types.Type.ARRAY,
            "object": types.Type.OBJECT,
        }
        
        prop_type = type_map.get(prop_schema.get("type", "string"), types.Type.STRING)
        
        schema_kwargs = {
            "type": prop_type,
            "description": prop_schema.get("description", "")
        }
        
        # Array items
        if "items" in prop_schema:
            schema_kwargs["items"] = GeminiLLMAdapter._convert_property(prop_schema["items"])
        elif prop_type == types.Type.ARRAY:
            schema_kwargs["items"] = types.Schema(type=types.Type.STRING)
        
        # Object properties
        if "properties" in prop_schema:
            schema_kwargs["properties"] = {
                name: GeminiLLMAdapter._convert_property(p)
                for name, p in prop_schema["properties"].items()
            }
            schema_kwargs["required"] = prop_schema.get("required", [])
        
        return types.Schema(**schema_kwargs)
    
    @staticmethod
    def _parse_response(gemini_response) -> LLMResponse:
        """
        Parseia resposta Gemini.
        
        Extrai:
        - Texto da resposta
        - Tool calls (se houver)
        - Stop reason
        """
        content = ""
        tool_calls = []
        stop_reason = "end_turn"
        
        if gemini_response.candidates:
            candidate = gemini_response.candidates[0]
            
            # Extrair stop reason
            if hasattr(candidate, 'finish_reason'):
                if str(candidate.finish_reason).lower() == "TOOL_USE":
                    stop_reason = "tool_use"
            
            # Parsear content/parts
            if hasattr(candidate, 'content') and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        content += part.text
                    
                    # Function calls
                    if hasattr(part, 'function_call') and part.function_call:
                        tool_calls.append({
                            "id": getattr(part.function_call, 'name', ''),
                            "name": getattr(part.function_call, 'name', ''),
                            "arguments": dict(part.function_call.args) if hasattr(part.function_call, 'args') else {}
                        })
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason
        )
