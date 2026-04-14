"""
Voice Provider - SÃ­ntese de voz com ElevenLabs + fallback pyttsx3.

EstratÃ©gia:
- ElevenLabs (IA, qualidade premium) como primÃ¡rio
- pyttsx3 (local, sem internet) como fallback
- Cache de audio jÃ¡ sintetizado
- Async nativo
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import asyncio
import json
from pathlib import Path
import base64

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    from core import get_logger, get_config
except ImportError:
    from core import get_logger, get_config

logger = get_logger(__name__)


class VoiceProvider(ABC):
    """Interface base para provedores de voz."""
    
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Sintetiza texto em Ã¡udio.
        
        Args:
            text: Texto a sintetizar
        
        Returns:
            bytes: Ãudio em formato MP3 ou WAV
        """
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Retorna nome do provider."""
        pass


class ElevenLabsProvider(VoiceProvider):
    """Provider usando ElevenLabs API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa provider ElevenLabs.
        
        Args:
            api_key: Chave da API (default: env ELEVENLABS_API_KEY)
        """
        self.api_key = api_key or self._get_api_key()
        self.voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel (voz padrÃ£o)
        self.base_url = "https://api.elevenlabs.io/v1"
        self._cache = {}  # Cache de audio sintetizado
    
    def _get_api_key(self) -> str:
        """ObtÃ©m chave da API de variÃ¡veis de ambiente."""
        import os
        key = os.getenv("ELEVENLABS_API_KEY", "")
        
        if not key:
            logger.warning("[VOICE] ElevenLabs API key nÃ£o encontrada, usando fallback")
            return ""
        
        return key
    
    async def synthesize(self, text: str) -> bytes:
        """Sintetiza usando ElevenLabs API."""
        
        if not HAS_AIOHTTP:
            raise RuntimeError("aiohttp nÃ£o estÃ¡ instalado. Instale com: pip install aiohttp. Usando fallback pyttsx3.")
        
        # Verificar cache
        cache_key = hash(text)
        if cache_key in self._cache:
            logger.debug("[VOICE] Retornando Ã¡udio do cache")
            return self._cache[cache_key]
        
        if not self.api_key:
            raise RuntimeError("ElevenLabs API key nÃ£o configurada")
        
        try:
            logger.info(f"[VOICE] Sintetizando com ElevenLabs ({len(text)} chars)...")
            
            url = f"{self.base_url}/text-to-speech/{self.voice_id}"
            
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            
            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers, timeout=30) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        raise RuntimeError(f"ElevenLabs error: {resp.status} - {error}")
                    
                    audio_bytes = await resp.read()
            
            # Cachear resultado
            self._cache[cache_key] = audio_bytes
            
            logger.info(f"[VOICE] SÃ­ntese completa ({len(audio_bytes)} bytes)")
            return audio_bytes
        
        except Exception as e:
            logger.error(f"[VOICE] Erro ao sintetizar: {str(e)}")
            raise
    
    def name(self) -> str:
        return "ElevenLabs"


class PyTTSX3Provider(VoiceProvider):
    """Provider usando pyttsx3 (local, sem internet)."""
    
    def __init__(self, voice_index: int = 0):
        """
        Inicializa provider pyttsx3.
        
        Args:
            voice_index: Ãndice da voz a usar (0 ou 1)
        """
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.voice_index = voice_index
            
            # Configurar velocidade e volume
            self.engine.setProperty("rate", 150)  # Velocidade
            self.engine.setProperty("volume", 0.9)  # Volume
            
            # Selecionar voz
            voices = self.engine.getProperty("voices")
            if voice_index < len(voices):
                self.engine.setProperty("voice", voices[voice_index].id)
            
            logger.info("[VOICE] pyttsx3 inicializado")
        
        except ImportError:
            logger.warning("[VOICE] pyttsx3 nÃ£o estÃ¡ instalado, sÃ­ntese desabilitada")
            self.engine = None
    
    async def synthesize(self, text: str) -> bytes:
        """Sintetiza usando pyttsx3 (local)."""
        
        if not self.engine:
            raise RuntimeError("pyttsx3 nÃ£o disponÃ­vel")
        
        try:
            logger.info(f"[VOICE] Sintetizando com pyttsx3 ({len(text)} chars)...")
            
            # Salvar temporariamente em arquivo
            output_path = Path("/tmp/quinta_feira_audio.mp3")
            
            # pyttsx3 Ã© sÃ­ncrono, entÃ£o rodamos em thread
            def generate():
                self.engine.save_to_file(text, str(output_path))
                self.engine.runAndWait()
            
            await asyncio.to_thread(generate)
            
            # Ler arquivo
            if output_path.exists():
                audio_bytes = output_path.read_bytes()
                output_path.unlink()  # Deletar temp
                
                logger.info(f"[VOICE] SÃ­ntese pyttsx3 completa ({len(audio_bytes)} bytes)")
                return audio_bytes
            else:
                raise RuntimeError("Falha ao gerar Ã¡udio com pyttsx3")
        
        except Exception as e:
            logger.error(f"[VOICE] Erro ao sintetizar: {str(e)}")
            raise
    
    def name(self) -> str:
        return "pyttsx3"


class VoiceManager:
    """Gerenciador de voz com fallback automÃ¡tico."""
    
    def __init__(self):
        """Inicializa manager com ElevenLabs + fallback pyttsx3."""
        self.primary = None
        self.fallback = None
        
        # Tentar ElevenLabs
        try:
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if api_key:
                self.primary = ElevenLabsProvider(api_key)
                logger.info("[VOICE] Usando ElevenLabs como provider primÃ¡rio")
        except Exception as e:
            logger.warning(f"[VOICE] NÃ£o foi possÃ­vel usar ElevenLabs: {e}")
        
        # Sempre ter fallback
        try:
            self.fallback = PyTTSX3Provider()
            logger.info("[VOICE] Fallback pyttsx3 disponÃ­vel")
        except Exception as e:
            logger.warning(f"[VOICE] pyttsx3 nÃ£o disponÃ­vel: {e}")
    
    async def synthesize(self, text: str) -> bytes:
        """
        Sintetiza com fallback automÃ¡tico.
        
        Tenta ElevenLabs primeiro, cai para pyttsx3 se falhar.
        """
        
        # Tentar provider primÃ¡rio
        if self.primary:
            try:
                return await self.primary.synthesize(text)
            except Exception as e:
                logger.warning(f"[VOICE] Erro no provider primÃ¡rio, tentando fallback: {e}")
        
        # Fallback para pyttsx3
        if self.fallback:
            try:
                return await self.fallback.synthesize(text)
            except Exception as e:
                logger.error(f"[VOICE] Erro no fallback tambÃ©m: {e}")
                raise RuntimeError("Nenhum provider de voz disponÃ­vel")
        
        raise RuntimeError("Nenhum provider de voz configurado")
    
    def get_active_provider(self) -> str:
        """Retorna nome do provider ativo."""
        if self.primary:
            return self.primary.name()
        elif self.fallback:
            return self.fallback.name()
        return "Nenhum"


# Singleton global
_voice_manager = None

async def get_voice_manager() -> VoiceManager:
    """Factory para obter gerenciador de voz (singleton)."""
    global _voice_manager
    if _voice_manager is None:
        _voice_manager = VoiceManager()
    return _voice_manager


# Import necessÃ¡rio
import os

