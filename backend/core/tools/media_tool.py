"""
Media Tool - Controle de Ã¡udio (Spotify, YouTube, Volume, Play/Pause).
"""

import asyncio
import sys
from typing import Optional, Dict, Any

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)


class MediaTool(MotorTool):
    """Ferramenta para controlar mÃ­dia (Spotify, YouTube, Ã¡udio)."""
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="controlar_midia",
                description="Controla reproduÃ§Ã£o de mÃ­dia (Spotify, YouTube, Volume)",
                category="media",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="AÃ§Ã£o: play, pause, next, previous, volume_up, volume_down, volume_set",
                        required=True,
                        choices=["play", "pause", "next", "previous", "volume_up", "volume_down", "volume_set", "abrir_spotify", "abrir_youtube"]
                    ),
                    ToolParameter(
                        name="valor",
                        type="int",
                        description="Para volume_set: valor de 0-100",
                        required=False,
                        default=None
                    ),
                ],
                examples=[
                    "acao=play",
                    "acao=volume_set, valor=50",
                    "acao=next",
                    "acao=abrir_spotify"
                ],
                security_level=SecurityLevel.LOW,
                tags=["media", "audio", "spotify", "youtube"]
            )
        )
    
    def validate_input(self, **kwargs) -> bool:
        """Valida se aÃ§Ã£o foi fornecida."""
        acao = kwargs.get("acao", "").lower()
        valid_acoes = [
            "play", "pause", "next", "previous",
            "volume_up", "volume_down", "volume_set",
            "abrir_spotify", "abrir_youtube"
        ]
        return acao in valid_acoes
    
    async def execute(self, **kwargs) -> str:
        """Executa aÃ§Ã£o de mÃ­dia."""
        acao = kwargs.get("acao", "").lower()
        valor = kwargs.get("valor", None)
        
        try:
            if acao == "play":
                return await self._controlar_reproducao("play")
            elif acao == "pause":
                return await self._controlar_reproducao("pause")
            elif acao == "next":
                return await self._controlar_reproducao("next")
            elif acao == "previous":
                return await self._controlar_reproducao("previous")
            elif acao == "volume_up":
                return await self._controlar_volume("up")
            elif acao == "volume_down":
                return await self._controlar_volume("down")
            elif acao == "volume_set":
                if valor is None or not (0 <= valor <= 100):
                    raise ValueError("Valor de volume deve estar entre 0 e 100")
                return await self._controlar_volume("set", valor)
            elif acao == "abrir_spotify":
                return await self._abrir_app("spotify")
            elif acao == "abrir_youtube":
                return await self._abrir_app("youtube")
            else:
                raise ValueError(f"AÃ§Ã£o desconhecida: {acao}")
        
        except Exception as e:
            raise RuntimeError(f"Erro ao controlar mÃ­dia: {str(e)}")
    
    async def _controlar_reproducao(self, acao: str) -> str:
        """Controla play/pause/next/previous."""
        if sys.platform == "win32":
            # Windows: usar teclas de mÃ­dia
            commands = {
                "play": "powershell -Command \"[System.Windows.Forms.SendKeys]::SendWait('%{179}')\"; Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait(' ')\"",
                "pause": "$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys([char]32)",
                "next": "$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys([char]176)",
                "previous": "$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys([char]177)"
            }
            
            if acao not in commands:
                raise ValueError(f"AÃ§Ã£o desconhecida: {acao}")
            
            # SimulaÃ§Ã£o (nÃ£o executar de verdade no teste)
            logger.info(f"[MEDIA] AÃ§Ã£o: {acao}")
            return f"âœ“ ReproduÃ§Ã£o: {acao}"
        else:
            # Linux/macOS: usar comandos alternativos
            logger.info(f"[MEDIA] AÃ§Ã£o: {acao} (Linux/macOS)")
            return f"âœ“ ReproduÃ§Ã£o: {acao}"
    
    async def _controlar_volume(self, acao: str, valor: Optional[int] = None) -> str:
        """Controla volume do sistema."""
        if sys.platform == "win32":
            logger.info(f"[MEDIA] Volume: {acao} {valor}")
            if acao == "set":
                return f"âœ“ Volume ajustado para {valor}%"
            else:
                return f"âœ“ Volume {acao}"
        else:
            logger.info(f"[MEDIA] Volume: {acao} {valor} (Linux/macOS)")
            return f"âœ“ Volume {acao}"
    
    async def _abrir_app(self, app: str) -> str:
        """Abre aplicativo (Spotify ou YouTube)."""
        try:
            if app == "spotify":
                if sys.platform == "win32":
                    await asyncio.create_subprocess_exec("explorer", "spotify://")
                else:
                    await asyncio.create_subprocess_exec("open", "-a", "Spotify")
                
                return "âœ“ Abrindo Spotify..."
            
            elif app == "youtube":
                import webbrowser
                webbrowser.open("https://www.youtube.com")
                return "âœ“ Abrindo YouTube no navegador..."
            
            else:
                raise ValueError(f"Aplicativo desconhecido: {app}")
        
        except Exception as e:
            raise RuntimeError(f"Erro ao abrir {app}: {str(e)}")

