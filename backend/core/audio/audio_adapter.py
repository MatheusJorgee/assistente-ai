"""
Ports and Adapters para entrada/saida de audio.

Objetivo:
- desacoplar STT/TTS das bibliotecas concretas
- expor interface async sem bloquear o event loop
- evitar persistencia de audio em disco (usa memoria apenas)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
import threading

try:
    import pyttsx3  # type: ignore
except Exception:
    pyttsx3 = None

try:
    import speech_recognition as sr  # type: ignore
except Exception:
    sr = None

try:
    from core import get_logger
except ImportError:
    from core import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class AudioAvailability:
    stt_available: bool
    tts_available: bool
    details: str = ""


class SpeechRecognitionSTTAdapter:
    """Adapter STT usando SpeechRecognition (Google Web Speech)."""

    def __init__(self, language: str = "pt-BR") -> None:
        self._language = language
        self._recognizer = sr.Recognizer() if sr else None

    @property
    def available(self) -> bool:
        return self._recognizer is not None and sr is not None

    def transcribe_from_microphone(self, *, timeout: float = 2.0, phrase_time_limit: float = 6.0) -> Optional[str]:
        if not self.available:
            return None

        assert sr is not None
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

            text = self._recognizer.recognize_google(audio, language=self._language)
            cleaned = (text or "").strip()
            return cleaned or None
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except Exception as exc:
            logger.debug(f"[AUDIO][STT] erro transcricao: {exc}")
            return None


class Pyttsx3TTSAdapter:
    """Adapter TTS local com pyttsx3 sem escrever arquivos temporarios."""

    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()

        if pyttsx3 is None:
            return

        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 170)
            self._engine.setProperty("volume", 0.9)
        except Exception as exc:
            logger.warning(f"[AUDIO][TTS] pyttsx3 indisponivel: {exc}")
            self._engine = None

    @property
    def available(self) -> bool:
        return self._engine is not None

    def speak_text(self, text: str) -> bool:
        if not self.available:
            return False

        phrase = (text or "").strip()
        if not phrase:
            return False

        with self._lock:
            try:
                self._engine.say(phrase)
                self._engine.runAndWait()
                return True
            except Exception as exc:
                logger.warning(f"[AUDIO][TTS] falha ao falar: {exc}")
                return False


class AudioAdapter:
    """
    Facade de audio para o runtime.

    Todo I/O potencialmente bloqueante roda em executor para nao travar asyncio.
    """

    def __init__(
        self,
        *,
        stt: Optional[SpeechRecognitionSTTAdapter] = None,
        tts: Optional[Pyttsx3TTSAdapter] = None,
    ) -> None:
        self._stt = stt or SpeechRecognitionSTTAdapter()
        self._tts = tts or Pyttsx3TTSAdapter()

    @property
    def availability(self) -> AudioAvailability:
        details = []
        if not self._stt.available:
            details.append("STT indisponivel (instale speech_recognition e dependencias de microfone)")
        if not self._tts.available:
            details.append("TTS indisponivel (instale pyttsx3)")
        return AudioAvailability(
            stt_available=self._stt.available,
            tts_available=self._tts.available,
            details="; ".join(details),
        )

    async def listen_once(self, *, timeout: float = 2.0, phrase_time_limit: float = 6.0) -> Optional[str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._stt.transcribe_from_microphone(timeout=timeout, phrase_time_limit=phrase_time_limit),
        )

    async def speak_text(self, text: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._tts.speak_text(text))

