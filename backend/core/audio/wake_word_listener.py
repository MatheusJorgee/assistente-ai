"""
Wake Word Listener + Voice Command Orchestrator.

- WakeWordListener: captura audio continuo em thread dedicada e publica
  manual_command_requested no Event Bus.
- VoiceCommandOrchestrator: consome comandos de voz, consulta o Brain e
  reproduz resposta via TTS.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

try:
    from .. import get_logger
    from ..loop import AsyncEventBus, LoopEvent
except ImportError:
    from .. import get_logger
    from ..loop import AsyncEventBus, LoopEvent

try:
    from ..audio.audio_adapter import AudioAdapter
except ImportError:
    from ..audio.audio_adapter import AudioAdapter

logger = get_logger(__name__)


class WakeWordListener:
    """Listener de wake word em background, isolado do event loop."""

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus,
        audio_adapter: AudioAdapter,
        wake_words: tuple[str, ...] = ("quinta-feira", "quinta feira", "friday"),
        poll_interval_seconds: float = 0.2,
    ) -> None:
        self._event_bus = event_bus
        self._audio = audio_adapter
        self._wake_words = tuple(w.lower() for w in wake_words)
        self._poll_interval_seconds = max(0.05, poll_interval_seconds)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._main_loop = asyncio.get_running_loop()

        availability = self._audio.availability
        logger.info(
            "[WAKE] Listener iniciando | STT=%s TTS=%s",
            availability.stt_available,
            availability.tts_available,
        )
        if availability.details:
            logger.info(f"[WAKE] {availability.details}")

        self._thread = threading.Thread(target=self._thread_main, name="wake_word_listener", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("[WAKE] Listener encerrado")

    def _thread_main(self) -> None:
        while self._running:
            try:
                phrase = self._run_listen_blocking(timeout=2.0, phrase_time_limit=6.0)
                if not phrase:
                    continue

                normalized = phrase.lower().strip()
                wake = self._match_wake_word(normalized)
                if not wake:
                    continue

                command = self._extract_command_after_wake(phrase, wake)
                if not command:
                    command = self._run_listen_blocking(timeout=3.0, phrase_time_limit=8.0)

                command = (command or "").strip()
                if not command:
                    continue

                self._publish_from_thread(
                    LoopEvent(
                        type="manual_command_requested",
                        payload={
                            "command": command,
                            "origin": "voice",
                            "wake_word": wake,
                            "raw_phrase": phrase,
                        },
                        source="wake_word_listener",
                    )
                )
            except Exception as exc:
                logger.debug(f"[WAKE] loop erro: {exc}")

    def _run_listen_blocking(self, *, timeout: float, phrase_time_limit: float) -> Optional[str]:
        if not self._main_loop:
            return None

        future = asyncio.run_coroutine_threadsafe(
            self._audio.listen_once(timeout=timeout, phrase_time_limit=phrase_time_limit),
            self._main_loop,
        )
        try:
            text = future.result(timeout=timeout + phrase_time_limit + 2.0)
            return (text or "").strip() or None
        except Exception:
            return None

    def _publish_from_thread(self, event: LoopEvent) -> None:
        if not self._main_loop:
            return
        asyncio.run_coroutine_threadsafe(self._event_bus.publish(event), self._main_loop)

    def _match_wake_word(self, phrase: str) -> Optional[str]:
        for wake in self._wake_words:
            if wake in phrase:
                return wake
        return None

    @staticmethod
    def _extract_command_after_wake(original_phrase: str, wake_word: str) -> str:
        lowered = original_phrase.lower()
        idx = lowered.find(wake_word)
        if idx < 0:
            return ""
        start = idx + len(wake_word)
        return original_phrase[start:].strip(" ,.:;!?-")


class VoiceCommandOrchestrator:
    """Executa comandos originados por wake word e fecha ciclo via TTS."""

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus,
        brain: Any,
        audio_adapter: AudioAdapter,
    ) -> None:
        self._event_bus = event_bus
        self._brain = brain
        self._audio = audio_adapter
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._event_bus.subscribe("manual_command_requested", self._on_manual_command)
        logger.info("[VOICE_ORCH] Orchestrator de voz iniciado")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._event_bus.unsubscribe("manual_command_requested", self._on_manual_command)
        logger.info("[VOICE_ORCH] Orchestrator de voz encerrado")

    async def _on_manual_command(self, event: LoopEvent) -> None:
        if not self._running:
            return
        if event.source != "wake_word_listener":
            return

        command = str((event.payload or {}).get("command", "")).strip()
        if not command:
            return

        await self._event_bus.publish(
            LoopEvent(
                type="manual_command_processing",
                payload={"command": command, "origin": "voice"},
                source="voice_command_orchestrator",
            )
        )

        try:
            response = await self._brain.ask(command, include_vision=False)
            response_text = (response.text or "").strip()

            await self._event_bus.publish(
                LoopEvent(
                    type="manual_command_completed",
                    payload={"command": command, "response": response_text, "origin": "voice"},
                    source="voice_command_orchestrator",
                )
            )

            spoken = await self._audio.speak_text(response_text)
            await self._event_bus.publish(
                LoopEvent(
                    type="voice_response_spoken",
                    payload={"command": command, "spoken": spoken},
                    source="voice_command_orchestrator",
                )
            )
        except Exception as exc:
            await self._event_bus.publish(
                LoopEvent(
                    type="manual_command_failed",
                    payload={"command": command, "origin": "voice", "error": str(exc)},
                    source="voice_command_orchestrator",
                )
            )

