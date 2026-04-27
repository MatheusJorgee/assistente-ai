"""
TOCAR_YOUTUBE_INVISIVEL_TOOL.PY - Ferramenta Isolada de Mídia
═══════════════════════════════════════════════════════════════════════════════

PADRÃO: Strategy Pattern (implementa interface Tool)
PRINCÍPIO: IoC + OCP (Inversão de Controle + Oberto/Fechado)

Responsabilidades:
✓ Detectar requisições de música
✓ Extrair query de contexto natural
✓ Validar parâmetros
✓ Executar reprodução via OSAutomation
✓ Reportar resultado

NÃO RESPONSÁVEL POR:
✗ Roteamento no Brain
✗ Lógica de conversa
✗ Gerenciamento de história
"""

import re
import asyncio
import inspect
import logging
from typing import Optional, Any, Dict
from dataclasses import dataclass

# Importações resilientes
try:
    from core.tool_registry import Tool, ToolMetadata
except ImportError:
    from backend.core.tool_registry import Tool, ToolMetadata

logger = logging.getLogger(__name__)


class TocarYoutubeInvisivelTool(Tool):
    """
    Ferramenta de Mídia: Toca música/vídeo no YouTube via automação.
    
    PADRÃO: Strategy Pattern
    - Encapsula lógica de detecção de música
    - Encapsula lógica de extração de query
    - Executa via OSAutomation
    
    INVERSÃO DE CONTROLE:
    - O Brain NÃO conhece esta ferramenta
    - O Brain chama ToolRegistry.execute()
    - ToolRegistry invoca esta ferramenta se necessário
    
    PRINCÍPIO ABERTO/FECHADO:
    - Aberto: Novos tipos de mídia podem herdar desta classe
    - Fechado: Não precisa modificar Brain ao adicionar novas ferramentas
    """
    
    def __init__(self):
        """Inicializa a ferramenta com metadados."""
        super().__init__(
            metadata=ToolMetadata(
                name="tocar_youtube_invisivel",
                description=(
                    "Toca música/vídeo no YouTube via automação nativa do sistema. "
                    "Detecta automaticamente requisições de mídia e extrai a consulta. "
                    "Use imediatamente quando o usuário pedir para reproduzir algo."
                ),
                version="2.0.0",
                tags=["media", "youtube", "audio", "streaming"],
            )
        )
        self._automation = None
    
    def validate_input(self, **kwargs) -> bool:
        """
        Valida parâmetros da requisição.
        
        Args:
            pesquisa: String com nome da música/artista
            
        Returns:
            bool: True se válido, False caso contrário
        """
        pesquisa = kwargs.get("pesquisa", "").strip()
        
        # Validações
        if not pesquisa:
            logger.warning("[YOUTUBE_TOOL] Parâmetro 'pesquisa' vazio")
            return False
        
        if len(pesquisa) > 500:
            logger.warning("[YOUTUBE_TOOL] Parâmetro 'pesquisa' muito longo (>500 chars)")
            return False
        
        # Detectar se contém apenas caracteres válidos
        if not re.match(r"^[\w\s\-\(\)\.,']+$", pesquisa, re.UNICODE):
            logger.warning(f"[YOUTUBE_TOOL] Parâmetro contém caracteres inválidos: {pesquisa}")
            return False
        
        return True
    
    async def execute(self, **kwargs) -> str:
        """
        Solicita reproducao publicando `media_playback_requested` no EventBus.

        O backend NAO toca mais o video localmente: o frontend intercepta o
        evento via WebSocket e renderiza um <iframe> YouTube ou <AudioPlayer>.

        Args:
            pesquisa: String com nome da musica/artista

        Returns:
            str: Mensagem textual confirmando o pedido.
        """
        pesquisa = kwargs.get("pesquisa", "").strip()
        if not pesquisa:
            return "[ERRO] Parametro 'pesquisa' vazio"

        media_payload: Dict[str, Any] = {
            "provider": "youtube",
            "video_id": None,
            "video_url": None,
            "search_query": pesquisa,
            "title": pesquisa,
            "autoplay": True,
        }

        # Bridge WebSocket (AsyncEventBus) - frontend recebe e toca.
        self.publish_runtime("media_playback_requested", media_payload)

        # EventBus interno para telemetria local.
        if self._event_bus:
            self._event_bus.emit("media_playback_requested", media_payload)

        logger.info(
            f"[YOUTUBE_TOOL] Evento media_playback_requested publicado: {pesquisa!r}"
        )
        return f"Reproduzindo no navegador do usuario: {pesquisa!r}"
    
    def get_parameters(self) -> Dict[str, Any]:
        """
        Retorna schema de parâmetros para Function Calling.
        
        Define como o LLM deve chamar esta ferramenta.
        """
        return {
            "type": "object",
            "properties": {
                "pesquisa": {
                    "type": "string",
                    "description": (
                        "Nome da música e artista.\n"
                        "\n"
                        "INSTRUÇÕES RIGOROSAS:\n"
                        "1. Remova: pronomes (quero, toca, te peço), verbos de comando, preposições (no, da, de, em), palavras decorativas (por favor, aí, isso, aquela).\n"
                        "2. Mantenha APENAS: nome da música + nome do artista.\n"
                        "3. Ignore frases como 'Quero que toque', 'toca no youtube', 'te peço que toque'.\n"
                        "\n"
                        "EXEMPLOS (ENTRADA → PARÂMETRO):\n"
                        "  • 'Quero que toque the perfect pair da beabadobee' → 'the perfect pair beabadobee'\n"
                        "  • 'Toca numb do linkin park' → 'numb linkin park'\n"
                        "  • 'Coloca aquela música bohemian rhapsody da queen' → 'bohemian rhapsody queen'\n"
                        "  • 'Por favor, toca blinding lights no youtube' → 'blinding lights the weeknd'\n"
                        "  • 'Play creep radiohead' → 'creep radiohead'\n"
                        "\n"
                        "PADRÃO: '[nome_música] [artista]' - NADA MAIS."
                    ),
                }
            },
            "required": ["pesquisa"],
        }
    
    @staticmethod
    def is_music_request(text: str) -> bool:
        """
        ★ MÉTODO ESTÁTICO: Detecta se uma mensagem é requisição de música.
        
        Pode ser usado por:
        1. Pipeline de pré-processamento (antes de chamar LLM)
        2. Validação em middleware
        3. Logging/Analytics
        
        Args:
            text: Mensagem de entrada
            
        Returns:
            bool: True se parece ser requisição de música
        """
        text_norm = (text or "").strip().lower()
        if not text_norm:
            return False

        # Padrões de comando de música
        patterns = [
            r"\btoca(r)?\b",
            r"\btoque\b",
            r"\bcoloca\b",
            r"\breproduz(ir)?\b",
            r"\bplay\b",
        ]
        has_action = any(re.search(p, text_norm) for p in patterns)
        
        # Palavras-chave de contexto de música
        music_keywords = [
            "música", "musica", "song", "youtube", "spotify",
            "áudio", "audio", "som", "canção", "track",
        ]
        has_music = any(word in text_norm for word in music_keywords)
        
        return has_action and has_music
    
    @staticmethod
    def extract_music_query(text: str) -> str:
        """
        ★ MÉTODO ESTÁTICO: Extrai consulta de música de linguagem natural.
        
        Pode ser usado por:
        1. Pipeline de pré-processamento
        2. Validação de parâmetros
        3. Verificação de intenção
        
        Args:
            text: Mensagem em linguagem natural
            
        Returns:
            str: Nome da música + artista extraído
        """
        if not text:
            return "música relaxante"

        query = text.strip()
        
        # Remover prefixos de comando
        query = re.sub(
            r"^(por favor\s+)?(quinta[- ]feira\s*[,:-]?\s*)?(toca(r)?|toque|coloca|reproduz(ir)?|play)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        )
        
        # Remover "uma música de..."
        query = re.sub(
            r"^(uma\s+)?(música|musica)\s+(de\s+)?",
            "",
            query,
            flags=re.IGNORECASE
        )
        
        # Limpar espaços e pontuação
        query = query.strip(" .,!;:-")
        
        return query or text
    
    def _get_automation(self):
        """Lazy load da OSAutomation."""
        if self._automation is not None:
            return self._automation

        try:
            from automation import OSAutomation
        except ImportError:
            try:
                from backend.automation import OSAutomation
            except ImportError:
                raise RuntimeError("OSAutomation não encontrada em imports")

        self._automation = OSAutomation()
        return self._automation


# Factory para registrar a ferramenta
def create_tocar_youtube_tool() -> TocarYoutubeInvisivelTool:
    """Factory que cria a instância da ferramenta."""
    return TocarYoutubeInvisivelTool()
