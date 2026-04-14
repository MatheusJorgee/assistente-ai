"""
QUINTA_FEIRA_BRAIN.PY - CÃ³rtex Frontal (Orquestrador de IA)
============================================================

RESPONSABILIDADES:
- Recebe mensagem de texto/imagem do Gateway
- Gerencia histÃ³rico de conversa (buffer de contexto)
- Gerencia buffer de visÃ£o (imagens recentes)
- Injeta o LLMProvider (genÃ©rico)
- Injeta ToolRegistry (ferramentas disponÃ­veis)
- Orquestra Function Calling automÃ¡tico
- Retorna JSON rÃ­gido: {"text": "...", "audio": "", "mode": "..."}

NÃƒO FAZ:
- NÃ£o faz automaÃ§Ã£o (motor/)
- NÃ£o faz persistÃªncia (persistence/)
- NÃ£o faz captura de tela (motor/vision)
- NÃ£o faz sÃ­ntese de voz (voice/)

PADRÃƒO: Facade + Dependency Injection
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
import sys
import os
import re
import asyncio
import inspect

# ===== IMPORTAÃ‡Ã•ES RESILIENTES (funciona de qualquer cwd) =====
try:
    # Tentar importaÃ§Ã£o absoluta (uvicorn backend.main:app do pai)
    from core import get_config, get_logger
    from core.llm_provider import (
        LLMProvider,
        Message,
        Response,
        ToolDefinition,
        FunctionCallingOrchestrator,
    )
    from core.gemini_provider import GeminiAdapter
except ImportError:
    # Fallback: importaÃ§Ã£o relativa (uvicorn main:app do backend/)
    from core import get_config, get_logger
    from core.llm_provider import (
        LLMProvider,
        Message,
        Response,
        ToolDefinition,
        FunctionCallingOrchestrator,
    )
    from core.gemini_provider import GeminiAdapter

logger = get_logger(__name__)


@dataclass
class BrainResponse:
    """
    Resposta rÃ­gida do Brain para o Gateway.
    
    Sempre retorna neste formato (contrato entre Brain e Gateway):
    {
        "text": "Resposta da IA",
        "audio": "base64 audio ou vazio",
        "mode": "thinking|responding|error",
        "timestamp": "ISO 8601"
    }
    """
    text: str
    audio: str = ""
    mode: str = "responding"  # thinking, responding, error
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Exporta para JSON."""
        return {
            "text": self.text,
            "audio": self.audio,
            "mode": self.mode,
            "timestamp": self.timestamp,
        }


class VisionBuffer:
    """
    Gerencia buffer de imagens recentes.
    
    Usa LRU (Least Recently Used): mantÃ©m as Ãºltimas N imagens.
    
    Por quÃª?
    - UsuÃ¡rio manda screenshot
    - Pergunta "o que tem aÃ­?"
    - Brain precisa saber qual screenshot Ã© "aÃ­"
    - Mantemos Ãºltimas 5 imagens para contexto
    """
    
    def __init__(self, max_images: int = 5):
        self.max_images = max_images
        self.images: List[Dict[str, Any]] = []
    
    def add_image(self, image_data: bytes, format: str = "webp") -> None:
        """
        Adiciona imagem ao buffer.
        
        Args:
            image_data: Bytes da imagem
            format: Formato (webp, png, jpeg)
        """
        import base64
        
        self.images.append({
            "data": base64.b64encode(image_data).decode(),
            "format": format,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Remover imagens antigas se exceder limite
        if len(self.images) > self.max_images:
            self.images = self.images[-self.max_images:]
    
    def clear(self) -> None:
        """Limpa buffer."""
        self.images.clear()
    
    def has_images(self) -> bool:
        """Retorna True se hÃ¡ imagens no buffer."""
        return len(self.images) > 0
    
    def get_latest(self) -> Optional[Dict[str, Any]]:
        """Retorna imagem mais recente."""
        return self.images[-1] if self.images else None


class MessageHistory:
    """
    Gerencia histÃ³rico de mensagens (contexto conversacional).
    
    Usa sliding window: mantÃ©m Ãºltimas N mensagens para nÃ£o explodir
    encoding de tokens do LLM.
    """
    
    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages
        self.messages: List[Message] = []
    
    def add(self, role: str, content: Optional[str] = None, **kwargs) -> None:
        """Adiciona mensagem ao histÃ³rico."""
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        
        # Remover mensagens antigas se exceder limite
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
    
    def get_messages(self, limit: int = None) -> List[Message]:
        """
        Retorna histÃ³rico de mensagens com limite opcional.
        
        Args:
            limit: NÃºmero máximo de mensagens a retornar.
                   Se None, retorna todas as mensagens.
                   Para env. para LLM, usar limit=10.
        
        Returns:
            Lista de mensagens (cópia) em ordem cronológica.
        """
        messages = self.messages.copy()
        
        if limit and len(messages) > limit:
            # Pega últimas N mensagens em ordem cronológica
            messages = messages[-limit:]
        
        return messages
    
    def get_recent_messages_for_llm(self, limit: int = 10) -> List[Message]:
        """
        Retorna Ãºltimas N mensagens para enviar ao LLM.
        
        Use este método ao construir contexto para o LLM para limitar tokens.
        
        Args:
            limit: NÃºmero máximo de mensagens (default 10).
        
        Returns:
            Lista de mensagens em ordem cronológica.
        """
        return self.get_messages(limit=limit)
    
    def clear(self) -> None:
        """Limpa histÃ³rico."""
        self.messages.clear()
    
    def __len__(self) -> int:
        return len(self.messages)


class QuintaFeiraBrain:
    """
    CÃ³rtex Frontal: Orquestrador de IA.
    
    FLUXO PRINCIPAL:
    
    Gateway envia: {"message": "OlÃ¡", "image_data": null}
           â”‚
           â”œâ”€ brain.ask(message, image_data)
           â”‚
           â”œâ”€ Processar imagem (se houver)
           â”‚
           â”œâ”€ Adicionar ao histÃ³rico
           â”‚
           â”œâ”€ Injetar tools do ToolRegistry
           â”‚
           â”œâ”€ Chamar LLMProvider.generate()
           â”‚  (pode ser Gemini, Ollama, etc)
           â”‚
           â”œâ”€ Se funÃ§Ã£o calling, orquestrar
           â”‚
           â””â”€ Retornar BrainResponse
                   â”‚
                   â””â”€ Gateway formata em JSON
    """
    
    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        tool_registry: Optional[Any] = None,
    ):
        """
        Args:
            llm_provider: ImplementaÃ§Ã£o de LLM (ex: GeminiAdapter)
                         Se None, usa default Gemini
            tool_registry: Registry de ferramentas (ex: ToolRegistry)
                          Opcional, serÃ¡ injetado depois
        """
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # Injetar LLM Provider
        if llm_provider is None:
            self.llm_provider = GeminiAdapter()
        else:
            self.llm_provider = llm_provider
        
        # Injetar Tool Registry
        self.tool_registry = tool_registry
        self._automation = None
        
        # Orquestrador de Function Calling
        self.orchestrator = FunctionCallingOrchestrator(
            llm_provider=self.llm_provider,
            tool_registry=self.tool_registry
        )
        
        # Gerenciadores de contexto
        self.message_history = MessageHistory(max_messages=50)
        self.vision_buffer = VisionBuffer(max_images=5)
        
        # System Prompt (personalidade da Quinta-Feira)
        self.system_prompt = self._build_system_prompt()
        
        self.logger.info(f"[BRAIN] Inicializado com LLM: {self.llm_provider.name()}")
        self.logger.info(f"[BRAIN] Vision support: {self.llm_provider.supports_vision()}")
        self.logger.info(f"[BRAIN] Tools support: {self.llm_provider.supports_tools()}")
    
    def _build_system_prompt(self) -> str:
        """ConstrÃ³i system prompt com personalidade da Quinta-Feira."""
        return """VocÃª Ã© o Sistema Operativo Quinta-Feira, uma IA operacional criada por Matheus.

CaracterÃ­sticas:
- Brilhante e pragmÃ¡tica, com humor seco
- Direta ao ponto, sem robÃ³tica ("Como uma IA...")
- Sem emojis, sem frase de rodapÃ©
- Focada em resolver problemas de engenharia
    - VocÃª NÃƒO Ã© um chatbot passivo: vocÃª executa aÃ§Ãµes reais por ferramentas

Contexto:
- VocÃª tem acesso a ferramentas (terminal, aplicativos, busca)
- Pode processar imagens (prints de tela)
- Pode controlar mÃºsica (Spotify, YouTube)
- MantÃ©m contexto da conversa
- VocÃª possui memÃ³ria de longo prazo via ferramenta `memory_manager`

Uso esperado de memÃ³ria:
- Use `memory_manager` com action=save_memory para salvar fatos estÃ¡veis do usuÃ¡rio/host
- Prefira memory_type=semantic para preferÃªncias persistentes (ex: pasta padrÃ£o, linguagem)
- Use memory_type=episodic para eventos relevantes de execuÃ§Ã£o/falhas/decisÃµes
- Antes de assumir contexto antigo, consulte retrieve_memory/search_memory quando necessÃ¡rio

Regras obrigatÃ³rias de execuÃ§Ã£o:
- Nunca digas ao utilizador que nÃ£o consegues fazer algo ou que precisas que ele abra um programa manualmente,
  a menos que nÃ£o exista ferramenta disponÃ­vel para a aÃ§Ã£o solicitada.
- Se o pedido for para tocar mÃºsica, usa IMEDIATAMENTE a ferramenta `tocar_youtube_invisivel`.
- Ao usar ferramenta, executa primeiro e depois responde de forma objetiva com resultado real.

Quando nÃ£o souber:
- Diga "nÃ£o sei" e por quÃª
- Sugira prÃ³ximos passos
- NÃ£o invente informaÃ§Ãµes
"""
    
    async def initialize(self) -> None:
        """Inicializa componentes na startup."""
        await self.llm_provider.initialize()
        self.logger.info("[BRAIN] âœ“ Inicializado com sucesso")
    
    async def ask(
        self,
        message: str,
        image_data: Optional[bytes] = None,
        include_vision: bool = False,
        hidden_context: Optional[str] = None,
    ) -> BrainResponse:
        """
        Processa pergunta do usuÃ¡rio e retorna resposta.
        
        Args:
            message: Texto da pergunta
            image_data: Imagem (bytes) se usuÃ¡rio enviou
            include_vision: Se True, inclui buffer de visÃ£o no contexto
            
        Returns:
            BrainResponse ({"text": "...", "mode": "..."})
        """
        try:
            # Roteamento determinÃ­stico para mÃ­dia: evita degradaÃ§Ã£o de persona/chatbot.
            if self._is_music_request(message):
                pesquisa = self._extract_music_query(message)
                tool_call = {
                    "name": "tocar_youtube_invisivel",
                    "arguments": {"pesquisa": pesquisa},
                }
                tool_result = await self._execute_tool_call(tool_call)

                self.message_history.add("user", content=message)
                self.message_history.add(
                    "assistant",
                    content=tool_result,
                    tool_calls=[tool_call],
                )

                return BrainResponse(text=tool_result, audio="", mode="responding")

            # 1. Registrar imagem (se houver)
            if image_data:
                self.vision_buffer.add_image(image_data)
                self.logger.info(f"[BRAIN] Imagem adicionada ao buffer (total: {len(self.vision_buffer.images)})")
            
            # 2. Adicionar mensagem do usuÃ¡rio ao histÃ³rico
            self.message_history.add("user", content=message)
            
            # 3. Preparar lista de mensagens para LLM
            # Sempre comeÃ§ar com system prompt
            system_prompt = self.system_prompt
            if hidden_context:
                system_prompt = (
                    f"{system_prompt}\n\n"
                    "[HIDDEN_LONG_TERM_MEMORY_CONTEXT]\n"
                    f"{hidden_context}\n"
                    "[/HIDDEN_LONG_TERM_MEMORY_CONTEXT]"
                )

            llm_messages = [
                Message(role="system", content=system_prompt)
            ]
            # Usar apenas as últimas 10 mensagens para economizar tokens
            llm_messages.extend(self.message_history.get_recent_messages_for_llm(limit=10))
            
            # 4. Se incluir visÃ£o, adicionar imagens recentes ao contexto
            if include_vision and self.vision_buffer.has_images():
                vision_context = f"\n[CONTEXTO VISUAL: HÃ¡ {len(self.vision_buffer.images)} screenshot(s) recente(s) disponÃ­vel(is) para anÃ¡lise]"
                if llm_messages:
                    llm_messages[-1].content = (llm_messages[-1].content or "") + vision_context
                self.logger.info(f"[BRAIN] IncluÃ­do contexto visual no prompt")
            
            # 5. Obter ferramentas disponÃ­veis (se houver registry)
            tools = None
            if self.tool_registry and self.llm_provider.supports_tools():
                tools = self._get_tools_for_llm()
            elif self.llm_provider.supports_tools():
                # Mesmo sem registry, expÃµe a tool de mÃ­dia nativa da OSAutomation.
                tools = [self._build_tocar_youtube_tool_definition()]
            
            # 6. Processar com Function Calling automÃ¡tico
            self.logger.info(f"[BRAIN] Enviando para LLM ({self.llm_provider.name()})...")
            
            response = await self._process_with_tool_calls(
                messages=llm_messages,
                tools=tools,
                temperature=self.config.LLM_TEMPERATURE
            )
            
            # 7. Adicionar resposta ao histÃ³rico
            self.message_history.add(
                "assistant",
                content=response.text,
                tool_calls=response.tool_calls
            )
            
            # 8. Gerar Ã¡udio (futura integraÃ§Ã£o com voice/)
            audio = ""  # SerÃ¡ preenchido quando voice/ estiver pronto
            
            # 9. Retornar resposta
            self.logger.info(f"[BRAIN] Resposta gerada: {len(response.text)} chars")
            
            return BrainResponse(
                text=response.text,
                audio=audio,
                mode="responding"
            )
        
        except Exception as e:
            self.logger.error(f"[BRAIN] Erro ao processar: {type(e).__name__}: {e}")
            return BrainResponse(
                text=f"Desculpe, ocorreu um erro: {str(e)}",
                mode="error"
            )
    
    def _get_tools_for_llm(self) -> List[ToolDefinition]:
        """
        ObtÃ©m lista de ferramentas disponÃ­veis do registry.
        
        Converte ferramenta do nosso domÃ­nio (Tool) para formato genÃ©rico (ToolDefinition).
        """
        tools_defs = []
        
        try:
            all_tools = self.tool_registry.get_all_tools()
            
            for tool in all_tools:
                # Cada Tool deve ter:
                # - metadata.name
                # - metadata.description
                # - get_parameters() ou similar
                
                tool_def = ToolDefinition(
                    name=tool.metadata.name,
                    description=tool.metadata.description or f"Tool: {tool.metadata.name}",
                    parameters=tool.get_parameters() if hasattr(tool, 'get_parameters') else {}
                )
                tools_defs.append(tool_def)

            # Tool explÃ­cita e obrigatÃ³ria para mÃ­dia nativa (Function Calling robusto).
            if not any(t.name == "tocar_youtube_invisivel" for t in tools_defs):
                tools_defs.append(self._build_tocar_youtube_tool_definition())
        
        except Exception as e:
            self.logger.warning(f"[BRAIN] Erro ao obter ferramentas: {e}")
        
        return tools_defs if tools_defs else None

    def _build_tocar_youtube_tool_definition(self) -> ToolDefinition:
        """
        Schema canÃ´nico para tool de mÃ­dia nativa.

        ParÃ¢metro obrigatÃ³rio:
            - pesquisa (string)
        """
        return ToolDefinition(
            name="tocar_youtube_invisivel",
            description=(
                "Toca mÃºsica/vÃ­deo no YouTube via automaÃ§Ã£o nativa do sistema. "
                "Use imediatamente quando o usuÃ¡rio pedir para tocar mÃºsica."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pesquisa": {
                        "type": "string",
                        "description": (
                            "EXTRAIR APENAS O NOME DA MUSICA E DO ARTISTA.\n"
                            "\n"
                            "REGRAS RIGOROSAS:\n"
                            "1. Remova COMPLETAMENTE: pronomes (quero, toca, te peco), verbos de comando (toca, coloca, ponha), preposicoes (no, da, de, em), palavras decorativas (por favor, ai, isso, aquela).\n"
                            "2. Mantenha APENAS: nome da musica + nome do artista.\n"
                            "3. Ignore completamente frases como 'Quero que toque', 'toca no youtube', 'te peco que toque'.\n"
                            "\n"
                            "EXEMPLOS (ENTRADA -> PARAMETRO):\n"
                            "• 'Quero que toque the perfect pair da beabadobee' -> 'the perfect pair beabadobee'\n"
                            "• 'Toca numb do linkin park' -> 'numb linkin park'\n"
                            "• 'Coloca aquela musica bohemian rhapsody da queen' -> 'bohemian rhapsody queen'\n"
                            "• 'Por favor, toca blinding lights no youtube' -> 'blinding lights the weeknd'\n"
                            "• 'Play creep radiohead' -> 'creep radiohead'\n"
                            "\n"
                            "PADRAO: '[nome_musica] [artista]' - NADA MAIS."
                        ),
                    }
                },
                "required": ["pesquisa"],
            },
        )

    async def _process_with_tool_calls(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]],
        temperature: float,
    ) -> Response:
        """Loop robusto de function calling com execuÃ§Ã£o real de ferramentas."""
        max_iterations = 6
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            response = await self.llm_provider.generate(
                messages=messages,
                tools=tools,
                temperature=temperature,
            )

            if not response.tool_calls:
                return response

            # Registrar intenÃ§Ã£o de chamada do LLM antes de executar tools.
            messages.append(
                Message(
                    role="assistant",
                    content=response.text,
                    tool_calls=response.tool_calls,
                )
            )

            for tool_call in response.tool_calls:
                tool_result = await self._execute_tool_call(tool_call)
                messages.append(
                    Message(
                        role="tool",
                        tool_name=tool_call.get("name", "tool_result"),
                        tool_result=tool_result,
                    )
                )

        return Response(
            text="Limite de iteraÃ§Ãµes de ferramentas atingido. ExecuÃ§Ã£o interrompida com seguranÃ§a.",
            tool_calls=None,
            stop_reason="max_iterations",
        )

    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> str:
        """
        Executa tool call com validação de argumentos e fallback seguro.
        
        ⚡ SUPORTA HÍBRIDO SYNC/ASYNC:
        - Detecta automaticamente se a ferramenta é async ou sync
        - Ferramentas async: executa com await
        - Ferramentas sync: executa em thread paralela com asyncio.to_thread()
        
        Evita:
        1. TypeError ao fazer await em função síncrona
        2. Bloqueio do event loop do FastAPI com operações lentas de SO
        """
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments") or {}

        if not isinstance(arguments, dict):
            return "[ERRO] Argumentos da ferramenta inválidos (esperado objeto JSON)."

        # ===== CASE 1: Ferramenta de media (YouTube) =====
        if tool_name == "tocar_youtube_invisivel":
            pesquisa = str(arguments.get("pesquisa", "")).strip()
            if not pesquisa:
                return "[ERRO] Parâmetro obrigatório ausente: pesquisa"

            automation = self._get_automation()
            func = getattr(automation, "tocar_youtube_invisivel", None)
            
            if func is None:
                return f"[ERRO] Método 'tocar_youtube_invisivel' não encontrado em OSAutomation."
            
            # Detectar se é async ou sync usando inspect
            if inspect.iscoroutinefunction(func):
                # Ferramenta assíncrona: executar com await
                try:
                    return await func(pesquisa)
                except Exception as exc:
                    return f"[ERRO ao executar {tool_name}] {type(exc).__name__}: {exc}"
            else:
                # Ferramenta síncrona: executar em thread paralela (NÃO bloqueia event loop)
                try:
                    return await asyncio.to_thread(func, pesquisa)
                except Exception as exc:
                    return f"[ERRO ao executar {tool_name}] {type(exc).__name__}: {exc}"

        # ===== CASE 2: Ferramentas genéricas do Registry =====
        if not self.tool_registry:
            return f"[ERRO] Tool Registry não configurado para '{tool_name}'."

        try:
            result = await self.tool_registry.execute(tool_name, **arguments)

            if hasattr(result, "success") and hasattr(result, "output"):
                if bool(getattr(result, "success", False)):
                    return str(getattr(result, "output", "") or "")
                return str(getattr(result, "error", "") or "[TOOL_ERROR] Sem detalhes")

            return str(result)
        except Exception as exc:
            return f"[ERRO ao executar {tool_name}] {type(exc).__name__}: {exc}"

    def _get_automation(self):
        """Lazy load da OSAutomation para evitar custo de startup desnecessÃ¡rio."""
        if self._automation is not None:
            return self._automation

        try:
            from automation import OSAutomation
        except ImportError:
            from automation import OSAutomation

        self._automation = OSAutomation()
        return self._automation

    def _is_music_request(self, text: str) -> bool:
        text_norm = (text or "").strip().lower()
        if not text_norm:
            return False

        patterns = [
            r"\btoca(r)?\b",
            r"\btoque\b",
            r"\bcoloca\b",
            r"\breproduz(ir)?\b",
            r"\bplay\b",
        ]
        has_action = any(re.search(p, text_norm) for p in patterns)
        has_music = any(word in text_norm for word in ["mÃºsica", "musica", "song", "youtube", "spotify"])
        return has_action and has_music

    def _extract_music_query(self, text: str) -> str:
        """Extrai consulta de mÃºsica de comandos em linguagem natural."""
        if not text:
            return "mÃºsica relaxante"

        query = text.strip()
        query = re.sub(
            r"^(por favor\s+)?(quinta[- ]feira\s*[,:-]?\s*)?(toca(r)?|toque|coloca|reproduz(ir)?|play)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(r"^(uma\s+)?(mÃºsica|musica)\s+(de\s+)?", "", query, flags=re.IGNORECASE)
        query = query.strip(" .,!;:-")
        return query or text
    
    def inject_tool_registry(self, tool_registry: Any) -> None:
        """Injeta registry de ferramentas (para adicionar tools depois)."""
        self.tool_registry = tool_registry
        self.orchestrator.tool_registry = tool_registry
        self.logger.info(f"[BRAIN] Tool Registry injetado ({len(tool_registry.get_all_tools())} tools)")
    
    def clear_history(self) -> None:
        """Limpa histÃ³rico de conversa."""
        self.message_history.clear()
        self.vision_buffer.clear()
        self.logger.info("[BRAIN] HistÃ³rico limpo")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatÃ­sticas do Brain."""
        return {
            "llm_provider": self.llm_provider.name(),
            "message_count": len(self.message_history),
            "image_count": len(self.vision_buffer.images),
            "tool_support": self.llm_provider.supports_tools(),
            "vision_support": self.llm_provider.supports_vision(),
        }

