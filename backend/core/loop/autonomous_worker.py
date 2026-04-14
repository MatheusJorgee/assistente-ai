"""
Worker autÃ´nomo em background para reagir a eventos do Event Bus.
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
    Worker de decisÃµes proativas.

    Fluxo inicial:
    - assina eventos timer_tick e user_idle
    - lÃª Ãºltimas linhas de telemetria
    - pergunta ao Brain se deve agir
    - publica evento autonomous_decision quando houver aÃ§Ã£o
    """

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus,
        brain: Any,
        memory_manager: Optional[Any] = None,
        audit_file: str | Path = ".runtime/audit/host_audit.jsonl",
        tick_interval_seconds: int = 20,
        max_audit_lines: int = 10,
        memory_context_limit: int = 5,
    ) -> None:
        self._bus = event_bus
        self._brain = brain
        self._memory_manager = memory_manager
        self._audit_file = Path(audit_file)
        self._tick_interval_seconds = max(5, tick_interval_seconds)
        self._max_audit_lines = max(1, max_audit_lines)
        self._memory_context_limit = max(1, memory_context_limit)

        self._running = False
        self._paused = False
        self._ticker_task: Optional[asyncio.Task[None]] = None
        self._semaphore = asyncio.Semaphore(1)

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

        self._bus.subscribe("timer_tick", self._on_event)
        self._bus.subscribe("user_idle", self._on_event)

        self._ticker_task = asyncio.create_task(self._ticker_loop(), name="autonomous_tick_loop")
        logger.info("[AUTONOMOUS] Worker iniciado")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False

        self._bus.unsubscribe("timer_tick", self._on_event)
        self._bus.unsubscribe("user_idle", self._on_event)

        if self._ticker_task:
            self._ticker_task.cancel()
            try:
                await self._ticker_task
            except asyncio.CancelledError:
                pass
            self._ticker_task = None

        logger.info("[AUTONOMOUS] Worker encerrado")

    async def _ticker_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._tick_interval_seconds)
            if not self._running:
                break
            if self._paused:
                continue
            await self._bus.publish(
                LoopEvent(
                    type="timer_tick",
                    payload={"interval_seconds": self._tick_interval_seconds},
                    source="autonomous_worker",
                )
            )

    async def _on_event(self, event: LoopEvent) -> None:
        if not self._running:
            return
        if self._paused:
            return

        async with self._semaphore:
            audit_tail = self._read_audit_tail()
            memory_context = await self._build_memory_context(event)

            prompt = (
                "[AUTONOMOUS_LOOP_INVISIBLE_PROMPT]\n"
                f"Evento: {event.type}\n"
                f"Payload: {event.payload}\n"
                "Ãšltimos eventos de auditoria do host:\n"
                f"{audit_tail}\n\n"
                "VocÃª deve decidir se existe alguma aÃ§Ã£o proativa segura. "
                "Se nÃ£o houver aÃ§Ã£o necessÃ¡ria, responda EXATAMENTE: NADA."
            )

            try:
                response = await self._brain.ask(
                    prompt,
                    include_vision=False,
                    hidden_context=memory_context,
                )
                text = (response.text or "").strip()
            except Exception as exc:
                logger.warning(f"[AUTONOMOUS] Falha ao consultar brain: {exc}")
                return

            if not text or text.upper() == "NADA":
                logger.info(f"[AUTONOMOUS] Evento '{event.type}' processado sem aÃ§Ã£o proativa")
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
            logger.info("[AUTONOMOUS] DecisÃ£o proativa publicada")

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
            return "(memÃ³ria indisponÃ­vel)"

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
                "MemÃ³rias semÃ¢nticas recentes:\n"
                f"{json.dumps(semantic, ensure_ascii=False)}\n\n"
                "MemÃ³rias relevantes para o evento atual:\n"
                f"{json.dumps(searched, ensure_ascii=False)}"
            )
        except Exception as exc:
            logger.warning(f"[AUTONOMOUS] Falha ao montar contexto de memÃ³ria: {exc}")
            return "(erro ao consultar memÃ³ria)"

