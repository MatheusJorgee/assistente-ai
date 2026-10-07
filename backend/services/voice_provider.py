"""
Voice Provider - Síntese de voz em cadeia de qualidade.

Estratégia (melhor disponível primeiro):
- ElevenLabs (premium, requer chave paga) se ELEVENLABS_API_KEY existir
- Edge TTS (voz NEURAL feminina pt-BR, gratuita, sem chave) — o padrão real
- pyttsx3 (local/robótica, sem internet) como último recurso
- Cache de audio já sintetizado
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
        Sintetiza texto em áudio.
        
        Args:
            text: Texto a sintetizar
        
        Returns:
            bytes: Ãudio em formato MP3 ou WAV
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
        import os
        self.api_key = api_key or self._get_api_key()
        # Voz configurável; default Rachel. Modelo multilingual: pt-BR natural.
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "") or "21m00Tcm4TlvDq8ikWAM"
        self.base_url = "https://api.elevenlabs.io/v1"
        self._cache = {}  # Cache de audio sintetizado
    
    def _get_api_key(self) -> str:
        """Obtém chave da API de variáveis de ambiente."""
        import os
        key = os.getenv("ELEVENLABS_API_KEY", "")
        
        if not key:
            logger.warning("[VOICE] ElevenLabs API key não encontrada, usando fallback")
            return ""
        
        return key
    
    async def synthesize(self, text: str) -> bytes:
        """Sintetiza usando ElevenLabs API."""
        
        if not HAS_AIOHTTP:
            raise RuntimeError("aiohttp não está instalado. Instale com: pip install aiohttp. Usando fallback pyttsx3.")
        
        # Verificar cache
        cache_key = hash(text)
        if cache_key in self._cache:
            logger.debug("[VOICE] Retornando áudio do cache")
            return self._cache[cache_key]
        
        if not self.api_key:
            raise RuntimeError("ElevenLabs API key não configurada")
        
        try:
            logger.info(f"[VOICE] Sintetizando com ElevenLabs ({len(text)} chars)...")
            
            url = f"{self.base_url}/text-to-speech/{self.voice_id}"
            
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",  # monolingual_v1 só fala inglês
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
            
            logger.info(f"[VOICE] Síntese completa ({len(audio_bytes)} bytes)")
            return audio_bytes
        
        except Exception as e:
            logger.error(f"[VOICE] Erro ao sintetizar: {str(e)}")
            raise
    
    def name(self) -> str:
        return "ElevenLabs"


class EdgeTTSProvider(VoiceProvider):
    """
    Voz NEURAL da Quinta-Feira (gratuita, sem chave): Microsoft Edge TTS.

    Voz padrão: pt-BR-FranciscaNeural — feminina, natural, brasileira.
    Alternativa: pt-BR-ThalitaMultilingualNeural. Configurável via EDGE_TTS_VOICE.
    """

    def __init__(self, voice: Optional[str] = None, rate: Optional[str] = None):
        import os
        self.voice = voice or os.getenv("EDGE_TTS_VOICE", "pt-BR-FranciscaNeural")
        self.rate = rate or os.getenv("EDGE_TTS_RATE", "+8%")
        self._cache: Dict[int, bytes] = {}

        try:
            import edge_tts  # noqa: F401
            self.available = True
        except ImportError:
            logger.warning("[VOICE] edge-tts não instalado (pip install edge-tts)")
            self.available = False

    async def synthesize(self, text: str) -> bytes:
        if not self.available:
            raise RuntimeError("edge-tts não instalado")

        cache_key = hash(text)
        if cache_key in self._cache:
            logger.debug("[VOICE] EdgeTTS: áudio do cache")
            return self._cache[cache_key]

        import edge_tts
        logger.info(f"[VOICE] Sintetizando com EdgeTTS/{self.voice} ({len(text)} chars)...")
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        audio = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]

        if not audio:
            raise RuntimeError("EdgeTTS não retornou áudio")

        if len(self._cache) > 64:  # cache simples com teto
            self._cache.clear()
        self._cache[cache_key] = audio
        logger.info(f"[VOICE] Síntese EdgeTTS completa ({len(audio)} bytes)")
        return audio

    def name(self) -> str:
        return f"EdgeTTS ({self.voice})"


_pyttsx3_lock = asyncio.Lock()  # pyttsx3 não é thread-safe — serializa chamadas


class PyTTSX3Provider(VoiceProvider):
    """Provider usando pyttsx3 (local, sem internet)."""

    def __init__(self, voice_index: int = 0):
        """
        Inicializa provider pyttsx3.
        
        Args:
            voice_index: Ãndice da voz a usar (0 ou 1)
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
            logger.warning("[VOICE] pyttsx3 não está instalado, síntese desabilitada")
            self.engine = None
    
    async def synthesize(self, text: str) -> bytes:
        """Sintetiza usando pyttsx3 (local)."""

        if not self.engine:
            raise RuntimeError("pyttsx3 não disponível")

        async with _pyttsx3_lock:
            return await self._do_synthesize(text)

    async def _do_synthesize(self, text: str) -> bytes:
        try:
            import tempfile
            logger.info(f"[VOICE] Sintetizando com pyttsx3 ({len(text)} chars)...")

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                output_path = Path(tmp.name)

            def generate():
                self.engine.save_to_file(text, str(output_path))
                self.engine.runAndWait()

            await asyncio.to_thread(generate)

            if output_path.exists() and output_path.stat().st_size > 0:
                audio_bytes = output_path.read_bytes()
                output_path.unlink()
                logger.info(f"[VOICE] Síntese pyttsx3 completa ({len(audio_bytes)} bytes)")
                return audio_bytes
            else:
                if output_path.exists():
                    output_path.unlink()
                raise RuntimeError("Falha ao gerar áudio com pyttsx3")
        
        except Exception as e:
            logger.error(f"[VOICE] Erro ao sintetizar: {str(e)}")
            raise
    
    def name(self) -> str:
        return "pyttsx3"


class VoiceManager:
    """Gerenciador de voz: cadeia de qualidade com fallback automático."""

    def __init__(self):
        """Monta a cadeia: ElevenLabs (se chave) → EdgeTTS (neural grátis) → pyttsx3."""
        self.providers: list[VoiceProvider] = []

        # 1. ElevenLabs (premium, opcional)
        try:
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if api_key:
                self.providers.append(ElevenLabsProvider(api_key))
                logger.info("[VOICE] ElevenLabs na cadeia (primário)")
        except Exception as e:
            logger.warning(f"[VOICE] Não foi possível usar ElevenLabs: {e}")

        # 2. Edge TTS — a voz natural padrão da Quinta-Feira (feminina pt-BR)
        try:
            edge = EdgeTTSProvider()
            if edge.available:
                self.providers.append(edge)
                logger.info(f"[VOICE] {edge.name()} na cadeia")
        except Exception as e:
            logger.warning(f"[VOICE] EdgeTTS indisponível: {e}")

        # 3. pyttsx3 — último recurso (offline, robótico)
        try:
            self.providers.append(PyTTSX3Provider())
            logger.info("[VOICE] Fallback pyttsx3 disponível")
        except Exception as e:
            logger.warning(f"[VOICE] pyttsx3 não disponível: {e}")

    async def synthesize(self, text: str) -> bytes:
        """Sintetiza com o melhor provider disponível, caindo na cadeia se falhar."""
        last_error: Optional[Exception] = None
        for provider in self.providers:
            try:
                return await provider.synthesize(text)
            except Exception as e:
                last_error = e
                logger.warning(f"[VOICE] {provider.name()} falhou, tentando próximo: {e}")
        raise RuntimeError(f"Nenhum provider de voz disponível ({last_error})")

    def get_active_provider(self) -> str:
        """Retorna nome do primeiro provider da cadeia (o preferido)."""
        return self.providers[0].name() if self.providers else "Nenhum"


# Singleton global
_voice_manager = None

async def get_voice_manager() -> VoiceManager:
    """Factory para obter gerenciador de voz (singleton)."""
    global _voice_manager
    if _voice_manager is None:
        _voice_manager = VoiceManager()
    return _voice_manager


# Import necessário
import os

