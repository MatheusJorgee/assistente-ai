"""
Worker autonomo em background orientado a eventos do Event Bus.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

try:
    from .event_bus import AsyncEventBus, LoopEvent
    from .. import get_logger
except ImportError:
    from .event_bus import AsyncEventBus, LoopEvent
    from .. import get_logger

logger = get_logger(__name__)


class AutonomousWorker:
    """
    Worker de decisoes proativas.

    Regras principais:
    - event-driven: nao cria polling interno
    - throttling por cooldown
    - evita chamar brain.ask repetidamente quando a ultima resposta foi vazia
    """

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus,
        brain: Any,
        memory_manager: Optional[Any] = None,
        audit_file: str | Path = ".runtime/audit/host_audit.jsonl",
        tick_interval_seconds: int = 20,
        cooldown_seconds: int = 30,
        max_audit_lines: int = 10,
        memory_context_limit: int = 5,
    ) -> None:
        self._bus = event_bus
        self._brain = brain
        self._memory_manager = memory_manager
        self._audit_file = Path(audit_file)
        self._tick_interval_seconds = max(5, tick_interval_seconds)
        self._cooldown_seconds = max(5, cooldown_seconds)
        self._max_audit_lines = max(1, max_audit_lines)
        self._memory_context_limit = max(1, memory_context_limit)

        # Eventos que devem acordar o worker.
        self._event_triggers = (
            "user_idle",
            "manual_command_completed",
            "voice_response_spoken",
            "active_window_changed",
        )

        self._running = False
        self._paused = False
        self._semaphore = asyncio.Semaphore(1)

        self._last_brain_call_ts = 0.0
        self._last_event_signature = ""
        self._last_response_empty = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def pause(self) -> None:
        if not self._running:
            return
        self._paused = True
        logger.info("[AUTONOMOUS] Worker pausado por comando externo")

    async def resume(self) -> None:
        if not self._running:
            return
        self._paused = False
        logger.info("[AUTONOMOUS] Worker retomado por comando externo")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        for event_type in self._event_triggers:
            self._bus.subscribe(event_type, self._on_event)

        logger.info("[AUTONOMOUS] Worker iniciado (event-driven)")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False

        for event_type in self._event_triggers:
            self._bus.unsubscribe(event_type, self._on_event)

        logger.info("[AUTONOMOUS] Worker encerrado")

    async def _on_event(self, event: LoopEvent) -> None:
        if not self._running or self._paused:
            return

        event_signature = self._build_event_signature(event)
        if not self._should_query_brain(event, event_signature):
            return

        async with self._semaphore:
            audit_tail = self._read_audit_tail()
            memory_context = await self._build_memory_context(event)

            prompt = (
                "[AUTONOMOUS_LOOP_INVISIBLE_PROMPT]\n"
                f"Evento: {event.type}\n"
                f"Payload: {event.payload}\n"
                "Ultimos eventos de auditoria do host:\n"
                f"{audit_tail}\n\n"
                "Voce deve decidir se existe alguma acao proativa segura. "
                "Se nao houver acao necessaria, responda EXATAMENTE: NADA."
            )

            try:
                now = asyncio.get_running_loop().time()
                response = await self._brain.ask(
                    prompt,
                    include_vision=False,
                    hidden_context=memory_context,
                )
                text = (response.text or "").strip()
                self._last_brain_call_ts = now
            except Exception as exc:
                logger.warning(f"[AUTONOMOUS] Falha ao consultar brain: {exc}")
                return

            if not text or text.upper() == "NADA":
                self._last_event_signature = event_signature
                self._last_response_empty = True
                logger.info(f"[AUTONOMOUS] Evento '{event.type}' processado sem acao proativa")
                return

            await self._bus.publish(
                LoopEvent(
                    type="autonomous_decision",
                    payload={
                        "origin_event": event.type,
                        "decision": text,
                    },
                    source="autonomous_worker",
                )
            )

            self._last_event_signature = event_signature
            self._last_response_empty = False
            logger.info("[AUTONOMOUS] Decisao proativa publicada")

    def _build_event_signature(self, event: LoopEvent) -> str:
        payload = event.payload if isinstance(event.payload, dict) else {}
        relevant = {
            "event": event.type,
            "source": event.source,
            "active_window": payload.get("active_window"),
            "command": payload.get("command"),
            "origin": payload.get("origin"),
            "spoken": payload.get("spoken"),
        }
        try:
            return json.dumps(relevant, sort_keys=True, ensure_ascii=False)
        except Exception:
            return f"{event.type}:{event.source}"

    def _should_query_brain(self, event: LoopEvent, event_signature: str) -> bool:
        if event.type not in self._event_triggers:
            return False

        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_brain_call_ts
        changed = event_signature != self._last_event_signature

        if self._last_response_empty and not changed:
            logger.debug(
                "[AUTONOMOUS] Evento repetido ignorado apos resposta vazia: %s",
                event.type,
            )
            return False

        if elapsed < self._cooldown_seconds and not changed:
            logger.debug(
                "[AUTONOMOUS] Cooldown ativo (%ss restantes) para evento %s",
                int(self._cooldown_seconds - elapsed),
                event.type,
            )
            return False

        return True

    def _read_audit_tail(self) -> str:
        if not self._audit_file.exists():
            return "(sem telemetria ainda)"

        try:
            lines = self._audit_file.read_text(encoding="utf-8").splitlines()
            if not lines:
                return "(sem telemetria ainda)"
            return "\n".join(lines[-self._max_audit_lines :])
        except Exception as exc:
            return f"(erro ao ler telemetria: {exc})"

    async def _build_memory_context(self, event: LoopEvent) -> str:
        if not self._memory_manager:
            return "(memoria indisponivel)"

        try:
            query_tokens = [event.type]
            payload = event.payload if isinstance(event.payload, dict) else {}
            for key in ("origin_event", "decision", "command", "tool", "tool_name"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    query_tokens.append(value.strip())

            query = " ".join(query_tokens)[:300]

            semantic = await self._memory_manager.retrieve_memory(
                memory_type="semantic",
                limit=self._memory_context_limit,
            )
            searched = await self._memory_manager.search_memory(
                query=query,
                memory_type="all",
                limit=self._memory_context_limit,
            )

            return (
                "Memorias semanticas recentes:\n"
                f"{json.dumps(semantic, ensure_ascii=False)}\n\n"
                "Memorias relevantes para o evento atual:\n"
                f"{json.dumps(searched, ensure_ascii=False)}"
            )
        except Exception as exc:
            logger.warning(f"[AUTONOMOUS] Falha ao montar contexto de memoria: {exc}")
            return "(erro ao consultar memoria)"

