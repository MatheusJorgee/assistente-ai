"""
Gemini provider canônico para interface LLMProvider.

Este módulo concentra a implementação de produção do provider Gemini
usado pelo Brain. Mantém compatibilidade com o contrato LLMProvider.
"""

import asyncio
import json
from copy import deepcopy
from typing import Any, AsyncIterator, Dict, List, Optional

from google import genai
from google.genai import types

from .config import get_config
from .llm_provider import LLMProvider, Message, Response, ToolDefinition
from .logger import get_logger

logger = get_logger(__name__)


class GeminiAdapter(LLMProvider):
    """Adaptador do Google Gemini para o contrato LLMProvider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.config = get_config()
        self.model_name = model
        self.client = None
        self.api_key = api_key or self.config.GEMINI_API_KEY

        logger.info(f"[Gemini] Inicializando com modelo: {self.model_name}")

    async def initialize(self) -> None:
        if not self.api_key:
            raise EnvironmentError("GEMINI_API_KEY não configurada!")

        try:
            self.client = genai.Client(api_key=self.api_key)
            logger.info("[Gemini] Cliente inicializado com sucesso")
        except Exception as exc:
            logger.error(f"[Gemini] Erro ao inicializar: {exc}")
            raise

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Response:
        if not self.client:
            await self.initialize()

        try:
            gemini_messages = self._convert_messages(messages)
            gemini_tools = self._convert_tools(tools) if tools and self.supports_tools() else None

            call_kwargs = {
                "model": f"models/{self.model_name}",
                "contents": gemini_messages,
                "config": {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            }

            if gemini_tools:
                call_kwargs["config"]["tools"] = gemini_tools

            gemini_response = await asyncio.wait_for(
                asyncio.to_thread(self.client.models.generate_content, **call_kwargs),
                timeout=30.0,
            )

            return self._parse_response(gemini_response)

        except asyncio.TimeoutError:
            logger.error("[Gemini] Timeout (30s)")
            return Response(
                text="Desculpe, o Gemini demorou muito para responder.",
                tool_calls=None,
                stop_reason="timeout",
            )
        except Exception as exc:
            logger.error(f"[Gemini] Erro: {type(exc).__name__}: {exc}")
            return Response(
                text=f"Erro ao processar com Gemini: {str(exc)}",
                tool_calls=None,
                stop_reason="error",
            )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        if not self.client:
            await self.initialize()

        try:
            gemini_messages = self._convert_messages(messages)
            gemini_tools = self._convert_tools(tools) if tools and self.supports_tools() else None

            stream_kwargs = {
                "model": f"models/{self.model_name}",
                "contents": gemini_messages,
                "config": {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            }

            if gemini_tools:
                stream_kwargs["config"]["tools"] = gemini_tools

            gemini_response = await asyncio.to_thread(
                self.client.models.generate_content,
                **stream_kwargs,
            )

            for chunk in gemini_response:
                if chunk.text:
                    yield chunk.text

        except Exception as exc:
            logger.error(f"[Gemini Stream] Erro: {exc}")
            yield f"[ERRO STREAMING]: {str(exc)}"

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True

    def name(self) -> str:
        return f"Gemini ({self.model_name})"

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        converted = []

        for msg in messages:
            if msg.role == "user":
                converted.append({"role": "user", "parts": [{"text": msg.content or ""}]})
            elif msg.role == "assistant":
                parts = []
                if msg.content:
                    parts.append({"text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        parts.append(
                            {
                                "functionCall": {
                                    "name": tc["name"],
                                    "args": tc.get("arguments", {}),
                                }
                            }
                        )
                converted.append({"role": "model", "parts": parts})
            elif msg.role == "tool":
                # ✅ CORRIGIDO: Usar function_response (snake_case) conforme SDK Pydantic exige
                # Anteriormente usava functionResult (camelCase) causando erro 400
                tool_name = msg.tool_name or "tool_result"
                tool_result_str = msg.tool_result or ""
                
                # Usar construtor nativo do SDK para máxima compatibilidade
                function_response_part = types.Part.from_function_response(
                    name=tool_name,
                    response={"result": tool_result_str}
                )
                
                converted.append(
                    {
                        "role": "user",
                        "parts": [function_response_part],
                    }
                )

        return converted

    def _convert_tools(self, tools: List[ToolDefinition]) -> Optional[List]:
        if not tools:
            return None

        function_declarations = []
        for tool in tools:
            parameters_schema = self._normalize_schema_for_gemini(tool.parameters)
            function_declarations.append(
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=parameters_schema,
                )
            )

        return [types.Tool(function_declarations=function_declarations)]

    def _normalize_schema_for_gemini(self, schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not schema:
            return {"type": "OBJECT", "properties": {}}

        normalized = deepcopy(schema)
        type_map = {
            "object": "OBJECT",
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
        }

        def visit(node: Any) -> Any:
            if isinstance(node, dict):
                out: Dict[str, Any] = {}
                for key, value in node.items():
                    if key in {"additionalProperties", "additional_properties"}:
                        continue
                    if key == "type" and isinstance(value, str):
                        out[key] = type_map.get(value.lower(), value)
                    elif key == "properties" and isinstance(value, dict):
                        out[key] = {prop_name: visit(prop_schema) for prop_name, prop_schema in value.items()}
                    elif key == "items":
                        out[key] = visit(value)
                    elif key == "default":
                        try:
                            json.dumps(value)
                            out[key] = value
                        except Exception:
                            continue
                    else:
                        out[key] = visit(value)

                if out.get("type") == "ARRAY" and "items" not in out:
                    out["items"] = {"type": "STRING"}
                if out.get("type") == "OBJECT" and "properties" not in out:
                    out["properties"] = {}
                return out
            if isinstance(node, list):
                return [visit(item) for item in node]
            return node

        result = visit(normalized)
        if not isinstance(result, dict):
            return {"type": "OBJECT", "properties": {}}

        if "type" not in result:
            result["type"] = "OBJECT"
        if result.get("type") == "OBJECT" and "properties" not in result:
            result["properties"] = {}

        return result

    def _parse_response(self, gemini_response) -> Response:
        text_parts = []
        tool_calls = []
        stop_reason = "end_turn"

        if gemini_response.candidates:
            candidate = gemini_response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        text_parts.append(part.text)
                    elif hasattr(part, "function_call") and part.function_call:
                        tool_calls.append(
                            {
                                "name": part.function_call.name,
                                "arguments": dict(part.function_call.args) if part.function_call.args else {},
                            }
                        )

            if candidate.finish_reason == "STOP":
                stop_reason = "end_turn"
            elif candidate.finish_reason == "MAX_TOKENS":
                stop_reason = "max_tokens"
            elif "FUNCTION_CALL" in str(candidate.finish_reason):
                stop_reason = "tool_use"

        return Response(
            text="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,
        )
