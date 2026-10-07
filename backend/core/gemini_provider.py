"""
Gemini provider canônico para interface LLMProvider.

Este módulo concentra a implementação de produção do provider Gemini
usado pelo Brain. Mantém compatibilidade com o contrato LLMProvider.
"""

import asyncio
import json
import time
from copy import deepcopy
from typing import Any, AsyncIterator, Dict, List, Optional

from google import genai
from google.genai import types

from .config import get_config
from .llm_policy import TIER_FORTE, TIER_LITE, Politica, inferir_proposito, politica_para
from .model_ladder import escada, marcar_por_erro
from .llm_provider import LLMProvider, Message, Response, ToolDefinition
from .logger import get_logger
from .telemetry.token_ledger import registrar as registrar_uso

logger = get_logger(__name__)


class GeminiAdapter(LLMProvider):
    """Adaptador do Google Gemini para o contrato LLMProvider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.config = get_config()
        self.model_name = model
        self.client = None
        self.api_key = api_key or self.config.GEMINI_API_KEY
        
        # ===== VALIDAÇÃO DE MODELO =====
        # system_instruction é suportado apenas em:
        # - gemini-1.5-flash (e acima)
        # - gemini-2.0-flash
        # - Modelos legados (1.0) NÃO suportam
        supported_models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash"]
        if not any(m in model for m in supported_models):
            logger.warning(
                f"[Gemini] ⚠️ Modelo '{model}' pode não suportar system_instruction. "
                f"Use: {', '.join(supported_models)}"
            )

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

        # Warm-up: primeira chamada TCP+SSL leva ~12s — fazemos no startup
        # para que o primeiro request do usuário seja imediato (~0.7s).
        try:
            logger.info("[Gemini] Aquecendo conexão com a API (cliente async)...")
            # Warm-up realista: inclui system_instruction e ThinkingConfig
            # para pré-carregar a instância de modelo correta no servidor Google.
            warmup_config = {
                "max_output_tokens": 1,
                "temperature": 0.0,
                "system_instruction": "Voce e um assistente.",
                "thinking_config": types.ThinkingConfig(thinking_budget=0),
            }
            await self.client.aio.models.generate_content(
                model=f"models/{self.model_name}",
                contents=[{"role": "user", "parts": [{"text": "hi"}]}],
                config=warmup_config,
            )
            logger.info("[Gemini] Conexão aquecida — primeira chamada de usuario sera rapida")
        except Exception as exc:
            logger.warning(f"[Gemini] Warm-up falhou (nao critico): {exc}")

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        thinking_budget: Optional[int] = None,
        purpose: Optional[str] = None,
        tier: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Response:
        if not self.client:
            await self.initialize()

        # Custo: politica por FUNCAO (modelo + raciocinio) — core/llm_policy.py. Tem que ser
        # descoberta antes de qualquer await, porque le a pilha de quem chamou.
        proposito = purpose or inferir_proposito()
        if getattr(self.config, "LLM_POLICY_ENABLED", True):
            politica = politica_para(proposito)
        else:
            politica = Politica()
        tier_efetivo = tier or politica.tier
        modelo = model or self._modelo_do_tier(tier_efetivo)
        if thinking_budget is None and politica.thinking is not None:
            thinking_budget = politica.thinking
        max_tokens = max(max_tokens, politica.max_tokens_min)

        try:
            # ===== EXTRAÇÃO CRÍTICA: system_instruction =====
            # Extrair a mensagem de sistema como texto para injetar no config
            system_instruction_text = next(
                (msg.content for msg in messages if msg.role == "system"), 
                None
            )
            filtered_messages = [msg for msg in messages if msg.role != "system"]
            
            gemini_messages = self._convert_messages(filtered_messages)
            gemini_tools = self._convert_tools(tools) if tools and self.supports_tools() else None

            # ===== PREPARAÇÃO DO CONFIG =====
            # CRÍTICO: O novo SDK exige system_instruction dentro do dicionário config
            # Não use GenerativeModel() - use client.models.generate_content() diretamente
            call_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                # Raciocínio: override por chamada (0 = rápido p/ msg simples; -1 dinâmico
                # p/ complexas). Sem override, usa o THINKING_BUDGET global do config.
                "thinking_config": types.ThinkingConfig(
                    thinking_budget=thinking_budget if thinking_budget is not None
                    else getattr(self.config, "THINKING_BUDGET", -1)
                ),
            }

            if system_instruction_text:
                call_config["system_instruction"] = system_instruction_text

            if gemini_tools:
                call_config["tools"] = gemini_tools

            # ===== CHAMADA DIRETA AO MODELO PELO SDK NOVO =====
            gemini_response = await self._chamar_com_fallback(
                modelo=modelo,
                tier=tier_efetivo,
                thinking_budget=thinking_budget,
                contents=gemini_messages,
                config=call_config,
                proposito=proposito,
                n_tools=len(tools) if gemini_tools else 0,
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

    def supports_streaming(self) -> bool:
        return True

    def _montar_pedido(self, messages, tools, temperature, max_tokens):
        """(contents, config, gemini_tools) de um pedido — mesma montagem do generate()."""
        system_instruction_text = next((m.content for m in messages if m.role == "system"), None)
        contents = self._convert_messages([m for m in messages if m.role != "system"])
        gemini_tools = self._convert_tools(tools) if tools and self.supports_tools() else None
        config: Dict[str, Any] = {"temperature": temperature, "max_output_tokens": max_tokens}
        if system_instruction_text:
            config["system_instruction"] = system_instruction_text
        if gemini_tools:
            config["tools"] = gemini_tools
        return contents, config, gemini_tools

    async def generate_stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        thinking_budget: Optional[int] = None,
        purpose: Optional[str] = None,
        tier: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """Streaming COM ferramentas: ("delta", texto) a cada pedaco e, no fim, ("final", Response).

        Mesma politica de modelo/raciocinio e mesmo ledger do generate(). Se o modelo escolhido
        falhar ANTES de produzir qualquer coisa, refaz no modelo padrao. Falha no meio do stream
        (ou em todos os modelos) LEVANTA a excecao: quem chama decide (o brain volta ao generate())."""
        if not self.client:
            await self.initialize()

        # Descoberto antes de qualquer await: depende da pilha de quem chamou.
        proposito = purpose or inferir_proposito()
        if getattr(self.config, "LLM_POLICY_ENABLED", True):
            politica = politica_para(proposito)
        else:
            politica = Politica()
        tier_efetivo = tier or politica.tier
        modelo = model or self._modelo_do_tier(tier_efetivo)
        if thinking_budget is None and politica.thinking is not None:
            thinking_budget = politica.thinking
        max_tokens = max(max_tokens, politica.max_tokens_min)

        contents, config, gemini_tools = self._montar_pedido(messages, tools, temperature, max_tokens)
        budget_base = (
            thinking_budget if thinking_budget is not None
            else getattr(self.config, "THINKING_BUDGET", -1)
        )
        candidatos = self._escada(modelo)
        n_tools = len(tools) if gemini_tools else 0

        for i, nome in enumerate(candidatos):
            cfg = dict(config)
            cfg["thinking_config"] = types.ThinkingConfig(
                thinking_budget=self._ajustar_thinking(nome, budget_base)
            )
            limite = float(getattr(self.config, "STREAM_TIMEOUT_SECONDS", 30.0))
            if tier_efetivo == TIER_FORTE and nome != self.model_name:
                limite *= 2  # modelo forte pensa mais
            t0 = time.time()
            textos: List[str] = []
            chamadas: List[Dict[str, Any]] = []
            uso: Any = None
            fim: Any = None
            produziu = False
            try:
                fluxo = await self.client.aio.models.generate_content_stream(
                    model=f"models/{nome}", contents=contents, config=cfg
                )
                iterador = fluxo.__aiter__()
                while True:
                    restante = limite - (time.time() - t0)
                    if restante <= 0:
                        raise asyncio.TimeoutError()
                    try:
                        pedaco = await asyncio.wait_for(iterador.__anext__(), timeout=restante)
                    except StopAsyncIteration:
                        break
                    uso = getattr(pedaco, "usage_metadata", None) or uso
                    for cand in (getattr(pedaco, "candidates", None) or [])[:1]:
                        fim = getattr(cand, "finish_reason", None) or fim
                        conteudo = getattr(cand, "content", None)
                        for parte in (getattr(conteudo, "parts", None) or []):
                            texto = getattr(parte, "text", None)
                            chamada = getattr(parte, "function_call", None)
                            if texto:
                                textos.append(texto)
                                produziu = True
                                yield ("delta", texto)
                            elif chamada:
                                produziu = True
                                chamadas.append({
                                    "name": chamada.name,
                                    "arguments": dict(chamada.args) if chamada.args else {},
                                })
            except asyncio.TimeoutError:
                logger.error(f"[Gemini] Timeout no streaming ({int(limite)}s)")
                if getattr(self.config, "LLM_LEDGER_ENABLED", True) and uso is not None:
                    registrar_uso(proposito, nome, uso, time.time() - t0, n_tools)
                yield ("final", Response(
                    text="".join(textos) or "Desculpe, o Gemini demorou muito para responder.",
                    tool_calls=chamadas or None,
                    stop_reason="timeout",
                ))
                return
            except Exception as exc:
                marcar_por_erro(nome, exc)
                if not produziu and i < len(candidatos) - 1:
                    logger.warning(
                        f"[Gemini] {nome} falhou no streaming ({type(exc).__name__}: {str(exc)[:80]}) — "
                        f"refazendo em {candidatos[-1]}"
                    )
                    continue
                raise

            if getattr(self.config, "LLM_LEDGER_ENABLED", True):
                registrar_uso(proposito, nome, uso, time.time() - t0, n_tools)
            if chamadas:
                parada = "tool_use"
            elif "MAX_TOKENS" in str(fim):
                parada = "max_tokens"
            else:
                parada = "end_turn"
            yield ("final", Response(
                text="".join(textos), tool_calls=chamadas or None, stop_reason=parada,
            ))
            return

    def _escada(self, modelo: str) -> List[str]:
        """escolhido -> padrão -> lite, sem os modelos que estouraram a cota há pouco (A6)."""
        lite = getattr(self.config, "GEMINI_MODEL_LITE", "") or ""
        return escada(modelo, [self.model_name, lite])

    def _modelo_do_tier(self, tier: Optional[str]) -> str:
        """lite = classificadores baratos; forte = so modo agente; padrao = GEMINI_MODEL."""
        if tier == TIER_LITE:
            return getattr(self.config, "GEMINI_MODEL_LITE", "") or self.model_name
        if tier == TIER_FORTE and getattr(self.config, "STRONG_MODEL_ENABLED", True):
            return getattr(self.config, "GEMINI_MODEL_STRONG", "") or self.model_name
        return self.model_name

    @staticmethod
    def _ajustar_thinking(modelo: str, budget: int) -> int:
        """O 2.5 Pro nao aceita raciocinio desligado (minimo 128)."""
        if "pro" in (modelo or "") and budget == 0:
            return 128
        return budget

    async def _chamar_com_fallback(
        self,
        *,
        modelo: str,
        tier: str,
        thinking_budget: Optional[int],
        contents: List[Dict[str, Any]],
        config: Dict[str, Any],
        proposito: str,
        n_tools: int,
    ):
        """Chama o modelo escolhido pela politica; se ele falhar (indisponivel, cota,
        nome errado), refaz UMA vez no modelo padrao — economizar nunca pode derrubar a Quinta.
        Registra o uso no ledger. Timeout propaga (o generate() ja trata)."""
        candidatos = self._escada(modelo)
        budget_base = (
            thinking_budget if thinking_budget is not None
            else getattr(self.config, "THINKING_BUDGET", -1)
        )
        for i, nome in enumerate(candidatos):
            cfg = dict(config)
            cfg["thinking_config"] = types.ThinkingConfig(
                thinking_budget=self._ajustar_thinking(nome, budget_base)
            )
            # Modelo forte pensa mais: folga de timeout so nele.
            timeout = 60.0 if (tier == TIER_FORTE and nome != self.model_name) else 30.0
            t0 = time.time()
            try:
                resposta = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=f"models/{nome}", contents=contents, config=cfg
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise
            except Exception as exc:
                marcar_por_erro(nome, exc)
                if i < len(candidatos) - 1:
                    logger.warning(
                        f"[Gemini] {nome} falhou ({type(exc).__name__}: {str(exc)[:80]}) — "
                        f"refazendo em {candidatos[-1]}"
                    )
                    continue
                raise
            if getattr(self.config, "LLM_LEDGER_ENABLED", True):
                registrar_uso(
                    proposito, nome, getattr(resposta, "usage_metadata", None),
                    time.time() - t0, n_tools,
                )
            return resposta

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
            # ===== EXTRAÇÃO CRÍTICA: system_instruction =====
            # Extrair a mensagem de sistema como texto para injetar no config
            system_instruction_text = next(
                (msg.content for msg in messages if msg.role == "system"), 
                None
            )
            filtered_messages = [msg for msg in messages if msg.role != "system"]
            
            gemini_messages = self._convert_messages(filtered_messages)
            gemini_tools = self._convert_tools(tools) if tools and self.supports_tools() else None

            # ===== PREPARAÇÃO DO CONFIG =====
            # CRÍTICO: O novo SDK exige system_instruction dentro do dicionário config
            # Não use GenerativeModel() - use client.models.generate_content() diretamente
            stream_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            
            if system_instruction_text:
                stream_config["system_instruction"] = system_instruction_text
                logger.info(f"[Gemini Stream] System instruction injetado no config")
            
            if gemini_tools:
                stream_config["tools"] = gemini_tools

            # ===== CHAMADA DIRETA AO MODELO PELO SDK NOVO =====
            stream_kwargs = {
                "model": f"models/{self.model_name}",
                "contents": gemini_messages,
                "config": stream_config,
            }

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
                parts: List[Any] = [{"text": msg.content or ""}]
                # Imagem inline (ex: screenshot da tela) para o Gemini "ver"
                if getattr(msg, "image_bytes", None):
                    try:
                        parts.append(
                            types.Part.from_bytes(
                                data=msg.image_bytes, mime_type=getattr(msg, "image_mime", "image/jpeg")
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"[Gemini] Falha ao anexar imagem: {exc}")
                converted.append({"role": "user", "parts": parts})
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
