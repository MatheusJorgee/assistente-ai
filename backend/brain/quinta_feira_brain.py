"""
QUINTA_FEIRA_BRAIN.PY - Córtex Frontal (Orquestrador de IA)
============================================================

RESPONSABILIDADES:
- Recebe mensagem de texto/imagem do Gateway
- Gerencia histórico de conversa (buffer de contexto)
- Gerencia buffer de visão (imagens recentes)
- Injeta o LLMProvider (genérico)
- Injeta ToolRegistry (ferramentas disponíveis)
- Orquestra Function Calling automático
- Retorna JSON rígido: {"text": "...", "audio": "", "mode": "..."}

NÃO FAZ:
- Não faz automação (motor/)
- Não faz persistência (persistence/)
- Não faz captura de tela (motor/vision)
- Não faz síntese de voz (voice/)

PADRÃO: Facade + Dependency Injection
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

# ===== IMPORTAÇÕES RESILIENTES (funciona de qualquer cwd) =====
try:
    # Tentar importação absoluta (uvicorn backend.main:app do pai)
    from core import get_config, get_logger
    from core.llm_provider import (
        LLMProvider,
        Message,
        Response,
        ToolDefinition,
    )
    from core.gemini_provider import GeminiAdapter
    from core.memory.sliding_window_context import ConversationMemory, LLMCompressionStrategy
except ImportError:
    # Fallback: importação relativa (uvicorn main:app do backend/)
    from core import get_config, get_logger
    from core.llm_provider import (
        LLMProvider,
        Message,
        Response,
        ToolDefinition,
    )
    from core.gemini_provider import GeminiAdapter
    from core.memory.sliding_window_context import ConversationMemory, LLMCompressionStrategy

logger = get_logger(__name__)


@dataclass
class BrainResponse:
    """
    Resposta rígida do Brain para o Gateway.
    
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
    
    Usa LRU (Least Recently Used): mantém as últimas N imagens.
    
    Por quê?
    - Usuário manda screenshot
    - Pergunta "o que tem aí?"
    - Brain precisa saber qual screenshot é "aí"
    - Mantemos últimas 5 imagens para contexto
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
        """Retorna True se há imagens no buffer."""
        return len(self.images) > 0
    
    def get_latest(self) -> Optional[Dict[str, Any]]:
        """Retorna imagem mais recente."""
        return self.images[-1] if self.images else None


class MessageHistory:
    """
    Gerencia histórico de mensagens (contexto conversacional).
    
    Usa sliding window: mantém últimas N mensagens para não explodir
    encoding de tokens do LLM.
    """
    
    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages
        self.messages: List[Message] = []
    
    def add(self, role: str, content: Optional[str] = None, **kwargs) -> None:
        """Adiciona mensagem ao histórico."""
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        
        # Remover mensagens antigas se exceder limite
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
    
    def get_messages(self) -> List[Message]:
        """Retorna histórico completo."""
        return self.messages.copy()
    
    def clear(self) -> None:
        """Limpa histórico."""
        self.messages.clear()
    
    def __len__(self) -> int:
        return len(self.messages)


class QuintaFeiraBrain:
    """
    Córtex Frontal: Orquestrador de IA.
    
    FLUXO PRINCIPAL:
    
    Gateway envia: {"message": "Olá", "image_data": null}
           â"‚
           â"œâ"€ brain.ask(message, image_data)
           â"‚
           â"œâ"€ Processar imagem (se houver)
           â"‚
           â"œâ"€ Adicionar ao histórico
           â"‚
           â"œâ"€ Injetar tools do ToolRegistry
           â"‚
           â"œâ"€ Chamar LLMProvider.generate()
           â"‚  (pode ser Gemini, Ollama, etc)
           â"‚
           â"œâ"€ Se função calling, orquestrar
           â"‚
           â""â"€ Retornar BrainResponse
                   â"‚
                   â""â"€ Gateway formata em JSON
    """
    
    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        tool_registry: Optional[Any] = None,
    ):
        """
        Args:
            llm_provider: Implementação de LLM (ex: GeminiAdapter)
                         Se None, usa default Gemini
            tool_registry: Registry de ferramentas (ex: ToolRegistry)
                          Opcional, será injetado depois
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

        # Gerenciadores de contexto
        self.message_history = ConversationMemory(
            max_messages=20,
            compress_trigger=16,
            keep_after_compress=4,
        )
        self.vision_buffer = VisionBuffer(max_images=5)
        
        # System Prompt (personalidade da Quinta-Feira)
        self.system_prompt = self._build_system_prompt()
        
        self.logger.info(f"[BRAIN] Inicializado com LLM: {self.llm_provider.name()}")
        self.logger.info(f"[BRAIN] Vision support: {self.llm_provider.supports_vision()}")
        self.logger.info(f"[BRAIN] Tools support: {self.llm_provider.supports_tools()}")
    
    def _build_system_prompt(self) -> str:
        """Constrói system prompt com personalidade da Quinta-Feira."""
        return """[DIRETRIZ DE SISTEMA CRÍTICA]
Você TEM UMA FERRAMENTA chamada `memorizar_informacao`.
É ESTRITAMENTE PROIBIDO responder ao usuário dizendo "Anotei" ou "Guardei"
sem antes ter efetivamente executado a ferramenta `memorizar_informacao`.
Se o usuário relatar um fato novo (preferência, dor, evento do dia), PARE,
chame a ferramenta de memória e SÓ DEPOIS gere sua resposta em texto.
[FIM DA DIRETRIZ CRÍTICA]

Você é o Sistema Operativo Quinta-Feira, uma IA operacional criada por Matheus.

Características:
- Brilhante e pragmática, com humor seco
- Direta ao ponto, sem robótica ("Como uma IA...")
- Sem emojis, sem frase de rodapé
- Focada em resolver problemas de engenharia
    - Você NÃO é um chatbot passivo: você executa ações reais por ferramentas

Contexto:
- Você tem acesso a ferramentas (terminal, aplicativos, busca)
- Pode processar imagens (prints de tela)
- Pode controlar música (Spotify, YouTube)
- Mantém contexto da conversa
- Você possui memória de longo prazo via ferramenta `memory_manager`

Uso esperado de memória:
- Use `memory_manager` com action=save_memory para salvar fatos estáveis do usuário/host
- Prefira memory_type=semantic para preferências persistentes (ex: pasta padrão, linguagem)
- Use memory_type=episodic para eventos relevantes de execução/falhas/decisões
- Antes de assumir contexto antigo, consulte retrieve_memory/search_memory quando necessário

============================================================
DIRETRIZ DE MEMÓRIA OBRIGATÓRIA (LEIA E CUMPRA SEMPRE):
============================================================
Você possui ferramentas de memória (ex: `salvar_memoria_obsidian`, `memory_manager`, `anotar_memoria`).
TODA VEZ que o usuário compartilhar uma informação nova (um fato sobre si mesmo, um estado
de humor, um evento do dia, uma preferência ou um plano), VOCÊ DEVE OBRIGATORIAMENTE
chamar a ferramenta de memória apropriada para registrar esse fato ANTES de responder.

REGRAS CRÍTICAS:
- Fatos imutáveis/permanentes (alergias, vínculos, preferências fixas): use `salvar_memoria_obsidian`.
- Fatos voláteis/do dia (dores, humor, refeições, eventos temporários): use a ferramenta de memória diária/curto prazo.
- Nunca confie apenas no contexto da conversa. Se o usuário disser "hoje estou com dor", GRAVE.
  Se disser "gosto de azul", GRAVE. Se disser "comi pizza no almoço", GRAVE.
- GRAVE PRIMEIRO, RESPONDA DEPOIS. NÃO pergunte se pode gravar — simplesmente grave.
============================================================

Regras obrigatórias de execução:
- Nunca digas ao utilizador que não consegues fazer algo ou que precisas que ele abra um programa manualmente,
  a menos que não exista ferramenta disponível para a ação solicitada.
- Se o pedido for para tocar música, usa IMEDIATAMENTE a ferramenta `tocar_youtube_invisivel`.
- Ao usar ferramenta, executa primeiro e depois responde de forma objetiva com resultado real.

Quando não souber:
- Diga "não sei" e por quê
- Sugira próximos passos
- Não invente informações

============================================================
DIRETRIZ VIP (CONTATOS FIXADOS NO WHATSAPP):
============================================================
Contatos com is_pinned=true sao alta prioridade absoluta.
Ao reportar novidades do WhatsApp, trate-os PRIMEIRO com tom de secretaria executiva que antecipa necessidades.
Se houver dados no campo contexto_obsidian para esse contato, cruze com o status atual do WhatsApp
e mencione proativamente qualquer coisa relevante para hoje.
Exemplo: "O Paulo (fixado) tem mensagem nova. Pelo Obsidian, ele e alergico a frutos do mar
-- se for marcar algo com ele hoje, leve isso em conta."
NUNCA ignore um contato fixado no resumo, mesmo que nao tenha mensagens novas.
============================================================
"""
    
    async def initialize(self) -> None:
        """ Inicializa componentes na startup."""
        await self.llm_provider.initialize()
        self.message_history.inject_strategy(
            LLMCompressionStrategy(self.llm_provider)
        )
        self.logger.info("[BRAIN] ✔ Inicializado com sucesso")
    
    async def ask(
        self,
        message: str,
        image_data: Optional[bytes] = None,
        include_vision: bool = False,
        hidden_context: Optional[str] = None,
    ) -> BrainResponse:
        """
        Processa pergunta do usuário e retorna resposta.
        
        Args:
            message: Texto da pergunta
            image_data: Imagem (bytes) se usuário enviou
            include_vision: Se True, inclui buffer de visão no contexto
            
        Returns:
            BrainResponse ({"text": "...", "mode": "..."})
        """
        try:
            # Roteamento determinístico para mídia: evita degradação de persona/chatbot.
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
            
            # 2. Adicionar mensagem do usuário ao histórico
            self.message_history.add("user", content=message)
            
            # 3. Preparar lista de mensagens para LLM
            # Sempre começar com system prompt (inclui long-term summary se houver)
            system_prompt = self.message_history.build_system_prompt(self.system_prompt)
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
            llm_messages.extend(self.message_history.get_messages())
            
            # 4. Se incluir visão, adicionar imagens recentes ao contexto
            if include_vision and self.vision_buffer.has_images():
                vision_context = f"\n[CONTEXTO VISUAL: Há {len(self.vision_buffer.images)} screenshot(s) recente(s) disponível(is) para análise]"
                if llm_messages:
                    llm_messages[-1].content = (llm_messages[-1].content or "") + vision_context
                self.logger.info(f"[BRAIN] Incluído contexto visual no prompt")
            
            # 5. Obter ferramentas disponíveis (se houver registry)
            tools = None
            if self.tool_registry and self.llm_provider.supports_tools():
                tools = self._get_tools_for_llm()
            elif self.llm_provider.supports_tools():
                # Mesmo sem registry, expõe a tool de mídia nativa da OSAutomation.
                tools = [self._build_tocar_youtube_tool_definition()]
            
            # 6. Processar com Function Calling automático
            self.logger.info(f"[BRAIN] Enviando para LLM ({self.llm_provider.name()})...")
            
            response = await self._process_with_tool_calls(
                messages=llm_messages,
                tools=tools,
                temperature=self.config.LLM_TEMPERATURE
            )
            
            # 7. Adicionar resposta ao histórico
            self.message_history.add(
                "assistant",
                content=response.text,
                tool_calls=response.tool_calls
            )
            
            # 8. Gerar áudio (futura integração com voice/)
            audio = ""  # Será preenchido quando voice/ estiver pronto
            
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
        Obtém lista de ferramentas disponíveis do registry.
        
        Converte ferramenta do nosso domínio (Tool) para formato genérico (ToolDefinition).
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

            # Tool explícita e obrigatória para mídia nativa (Function Calling robusto).
            if not any(t.name == "tocar_youtube_invisivel" for t in tools_defs):
                tools_defs.append(self._build_tocar_youtube_tool_definition())
        
        except Exception as e:
            self.logger.warning(f"[BRAIN] Erro ao obter ferramentas: {e}")
        
        return tools_defs if tools_defs else None

    def _build_tocar_youtube_tool_definition(self) -> ToolDefinition:
        """
        Schema canônico para tool de mídia nativa.

        Parâmetro obrigatório:
            - pesquisa (string)
        """
        return ToolDefinition(
            name="tocar_youtube_invisivel",
            description=(
                "Toca música/vídeo no YouTube via automação nativa do sistema. "
                "Use imediatamente quando o usuário pedir para tocar música."
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
        """Loop robusto de function calling com execução real de ferramentas."""
        max_iterations = 6
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            response = await self.llm_provider.generate(
                messages=messages,
                tools=tools,
                temperature=temperature,
            )

            print("\n--- INÍCIO: RESPOSTA CRUA DA LLM ---")
            print(response)
            print(f"tool_calls: {getattr(response, 'tool_calls', None)}")
            print(f"text: {getattr(response, 'text', None)!r}")
            print("--- FIM: RESPOSTA CRUA DA LLM ---\n")

            if not response.tool_calls:
                return response

            # Registrar intenção de chamada do LLM antes de executar tools.
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
            text="Limite de iterações de ferramentas atingido. Execução interrompida com segurança.",
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
                    output = str(getattr(result, "output", "") or "")
                else:
                    return str(getattr(result, "error", "") or "[TOOL_ERROR] Sem detalhes")
            else:
                output = str(result)

            # Enriquecer VIPs com contexto do Obsidian após triagem do WhatsApp
            resolved = self._aliases_resolve(tool_name) if hasattr(self, "_aliases_resolve") else tool_name
            if resolved in {"whatsapp", "triagem_whatsapp"} or arguments.get("acao") == "triagem":
                try:
                    import json as _json
                    triagem = _json.loads(output)
                    for contato in triagem.get("vip_contacts", []):
                        contexto = recuperar_memoria_nuclear(contato.get("nome", ""))
                        contato["contexto_obsidian"] = contexto if contexto else ""
                    output = _json.dumps(triagem, ensure_ascii=False)
                except Exception:
                    pass

            return output
        except Exception as exc:
            return f"[ERRO ao executar {tool_name}] {type(exc).__name__}: {exc}"

    def _get_automation(self):
        """Lazy load da OSAutomation para evitar custo de startup desnecessário."""
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
        has_music = any(word in text_norm for word in ["música", "musica", "song", "youtube", "spotify"])
        return has_action and has_music

    def _extract_music_query(self, text: str) -> str:
        """Extrai consulta de música de comandos em linguagem natural."""
        if not text:
            return "música relaxante"

        query = text.strip()
        query = re.sub(
            r"^(por favor\s+)?(quinta[- ]feira\s*[,:-]?\s*)?(toca(r)?|toque|coloca|reproduz(ir)?|play)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(r"^(uma\s+)?(música|musica)\s+(de\s+)?", "", query, flags=re.IGNORECASE)
        # Remove referências de plataforma: "no youtube", "pelo spotify", etc.
        query = re.sub(
            r"\b(no|na|pelo?|via)\s+(youtube|spotify|deezer|soundcloud|apple\s+music)\b",
            "",
            query,
            flags=re.IGNORECASE,
        )
        # Remove preposições soltas de artista: "do", "da", "de" no final
        query = re.sub(r"\s+(do|da|de)\s*$", "", query, flags=re.IGNORECASE)
        query = query.strip(" .,!;:-")
        return query or text
    
    def inject_tool_registry(self, tool_registry: Any) -> None:
        """Injeta registry de ferramentas (para adicionar tools depois)."""
        self.tool_registry = tool_registry
        self.logger.info(f"[BRAIN] Tool Registry injetado ({len(tool_registry.get_all_tools())} tools)")
    
    def clear_history(self) -> None:
        """Limpa histórico de conversa."""
        self.message_history.clear()
        self.vision_buffer.clear()
        self.logger.info("[BRAIN] Histórico limpo")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do Brain."""
        return {
            "llm_provider": self.llm_provider.name(),
            "message_count": len(self.message_history),
            "image_count": len(self.vision_buffer.images),
            "tool_support": self.llm_provider.supports_tools(),
            "vision_support": self.llm_provider.supports_vision(),
        }

