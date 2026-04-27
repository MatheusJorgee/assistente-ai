"""
Pipeline de áudio local: Wake Word (Porcupine) + VAD (webrtcvad) + STT (faster-whisper).

Garante zero-trace: nenhum byte de áudio sai da máquina antes do wake word
ser detectado. Após o wake word, VAD recorta a fala e faster-whisper transcreve
localmente. O resultado é publicado no AsyncEventBus como LoopEvent do tipo
"manual_command_requested", compatível com VoiceCommandOrchestrator.

Dependências opcionais (instalar quando necessário):
    pip install pvporcupine webrtcvad faster-whisper pyaudio numpy

Se qualquer dependência estiver ausente, o pipeline falha graciosamente
sem derrubar o resto do sistema.
"""

from __future__ import annotations

import asyncio
import threading
from abc import ABC, abstractmethod
from collections import deque
from enum import Enum, auto
from typing import Optional

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

try:
    from .. import get_logger
    from ..loop import AsyncEventBus, LoopEvent
except ImportError:
    from .. import get_logger
    from ..loop import AsyncEventBus, LoopEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Strategy de transcrição (STT) — swappable sem mudar o pipeline
# ---------------------------------------------------------------------------

class TranscriptionAdapter(ABC):
    @abstractmethod
    async def transcribe(self, pcm_bytes: bytes, sample_rate: int) -> str: ...

    @property
    @abstractmethod
    def available(self) -> bool: ...


class FasterWhisperAdapter(TranscriptionAdapter):
    """
    Transcrição local via faster-whisper (GGML int8, roda em CPU).
    Sem chamadas de rede: audio nunca sai da máquina.
    """

    def __init__(self, model_size: str = "small", language: str = "pt") -> None:
        self._language = language
        self._model = None
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info("[WHISPER] Modelo '%s' carregado (cpu/int8)", model_size)
        except ImportError:
            logger.warning("[WHISPER] faster-whisper não instalado; STT desativado")
        except Exception as exc:
            logger.warning("[WHISPER] Falha ao carregar modelo: %s", exc)

    @property
    def available(self) -> bool:
        return self._model is not None

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int) -> str:
        if not self._model:
            return ""

        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        buf.seek(0)

        loop = asyncio.get_running_loop()
        try:
            segments, _ = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(buf, language=self._language),
            )
            return " ".join(s.text for s in segments).strip()
        except Exception as exc:
            logger.warning("[WHISPER] Erro na transcrição: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Estado interno (máquina de estados simples)
# ---------------------------------------------------------------------------

class _State(Enum):
    IDLE = auto()        # só wake word — CPU mínima
    CAPTURING = auto()   # gravando áudio após wake word
    PROCESSING = auto()  # enviando para STT


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

class LocalAudioPipeline:
    """
    Pipeline de áudio totalmente local.

    Substitui WakeWordListener quando pvporcupine + webrtcvad + faster-whisper
    estiverem instalados. Publica o mesmo evento "manual_command_requested"
    que VoiceCommandOrchestrator já consome.

    Fluxo:
        Mic (contínuo) → Porcupine (wake word, ~0% CPU)
            └─ wake word detectado
                └─ pre-buffer + captura com VAD
                    └─ silêncio ≥ SILENCE_FRAMES_LIMIT
                        └─ faster-whisper (local)
                            └─ EventBus("manual_command_requested")
    """

    SAMPLE_RATE = 16_000
    VAD_AGGRESSIVENESS = 2        # 0 (permissivo) – 3 (agressivo)
    PRE_BUFFER_FRAMES = 12        # ~360 ms antes do wake word (evita cortar início)
    SILENCE_FRAMES_LIMIT = 35     # ~1.05 s de silêncio → fim da fala

    def __init__(
        self,
        event_bus: AsyncEventBus,
        stt_adapter: TranscriptionAdapter,
        porcupine_access_key: str,
        wake_words: Optional[list[str]] = None,
    ) -> None:
        self._bus = event_bus
        self._stt = stt_adapter
        self._access_key = porcupine_access_key
        self._wake_words = wake_words or ["jarvis"]
        self._state = _State.IDLE
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Inicializados dentro da thread de áudio para não travar o construtor
        self._porcupine = None
        self._vad = None
        self._frame_len: int = 512

        self._pre_buffer: deque[bytes] = deque(maxlen=self.PRE_BUFFER_FRAMES)
        self._capture_buffer: list[bytes] = []
        self._silence_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        if not _NUMPY_AVAILABLE:
            logger.error("[AUDIO_PIPELINE] numpy não encontrado; pipeline não pode iniciar")
            return

        self._running = True
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="local_audio_pipeline"
        )
        self._thread.start()
        logger.info("[AUDIO_PIPELINE] Iniciado (wake words: %s)", self._wake_words)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("[AUDIO_PIPELINE] Encerrado")

    # ------------------------------------------------------------------
    # Thread de áudio — nunca acessa o event loop diretamente
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            import pvporcupine
            import webrtcvad
            import pyaudio
        except ImportError as exc:
            logger.error("[AUDIO_PIPELINE] Dependência ausente: %s", exc)
            self._running = False
            return

        try:
            self._porcupine = pvporcupine.create(
                access_key=self._access_key,
                keywords=self._wake_words,
            )
        except Exception as exc:
            logger.error("[AUDIO_PIPELINE] Falha ao iniciar Porcupine: %s", exc)
            self._running = False
            return

        self._frame_len = self._porcupine.frame_length
        self._vad = webrtcvad.Vad(self.VAD_AGGRESSIVENESS)

        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=self.SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self._frame_len,
        )
        logger.info("[AUDIO_PIPELINE] Microfone aberto (frame_len=%d)", self._frame_len)

        try:
            while self._running:
                raw = stream.read(self._frame_len, exception_on_overflow=False)
                self._process_frame(raw)
        finally:
            stream.close()
            pa.terminate()
            self._porcupine.delete()
            logger.info("[AUDIO_PIPELINE] Recursos de áudio liberados")

    def _process_frame(self, raw: bytes) -> None:
        pcm = np.frombuffer(raw, dtype=np.int16)

        if self._state is _State.IDLE:
            self._pre_buffer.append(raw)
            idx = self._porcupine.process(pcm)
            if idx >= 0:
                self._on_wake_word()

        elif self._state is _State.CAPTURING:
            self._capture_buffer.append(raw)
            # webrtcvad exige frames de 10/20/30 ms; 30 ms @ 16 kHz int16 = 960 bytes
            vad_frame = raw[:960]
            if len(vad_frame) == 960:
                try:
                    is_speech = self._vad.is_speech(vad_frame, self.SAMPLE_RATE)
                except Exception:
                    is_speech = True

                if is_speech:
                    self._silence_count = 0
                else:
                    self._silence_count += 1
                    if self._silence_count >= self.SILENCE_FRAMES_LIMIT:
                        self._on_speech_end()

    def _on_wake_word(self) -> None:
        self._state = _State.CAPTURING
        self._capture_buffer = list(self._pre_buffer)  # inclui pre-buffer
        self._silence_count = 0
        logger.info("[AUDIO_PIPELINE] Wake word detectada; capturando...")
        self._publish(LoopEvent(
            type="wake_word_detected",
            payload={},
            source="local_audio_pipeline",
        ))

    def _on_speech_end(self) -> None:
        self._state = _State.PROCESSING
        audio_bytes = b"".join(self._capture_buffer)
        self._capture_buffer = []
        self._silence_count = 0
        logger.info("[AUDIO_PIPELINE] Fim da fala (%d bytes); enviando para STT", len(audio_bytes))
        asyncio.run_coroutine_threadsafe(
            self._transcribe_and_dispatch(audio_bytes), self._loop
        )

    async def _transcribe_and_dispatch(self, audio: bytes) -> None:
        try:
            text = await self._stt.transcribe(audio, self.SAMPLE_RATE)
            if text:
                logger.info("[AUDIO_PIPELINE] Transcrito: %r", text)
                await self._bus.publish(LoopEvent(
                    type="manual_command_requested",
                    payload={
                        "command": text,
                        "origin": "voice",
                        "wake_word": self._wake_words[0],
                        "raw_phrase": text,
                    },
                    source="local_audio_pipeline",
                ))
        except Exception as exc:
            logger.error("[AUDIO_PIPELINE] Erro no dispatch: %s", exc)
        finally:
            self._state = _State.IDLE

    def _publish(self, event: LoopEvent) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._bus.publish(event), self._loop)
