"""
Event Bus assíncrono (Pub/Sub) para runtime autônomo.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
import uuid


EventHandler = Callable[["LoopEvent"], Awaitable[None] | None]


@dataclass(frozen=True)
class LoopEvent:
    """Evento canônico do runtime autônomo."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class AsyncEventBus:
    """
    Event Bus assíncrono com dispatch em background.

    Características:
    - publish não bloqueante via asyncio.Queue
    - subscribe por tipo de evento e wildcard '*'
    - stop gracioso com drenagem da fila
    """

    def __init__(self, *, queue_maxsize: int = 1000) -> None:
        self._subscribers: Dict[str, list[EventHandler]] = {}
        self._queue: asyncio.Queue[LoopEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._running = False
        self._dispatcher_task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self._inflight_tasks: set[asyncio.Task[Any]] = set()

    @property
    def is_running(self) -> bool:
        return self._running

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._subscribers:
            return
        self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h != handler]

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop(), name="autonomous_event_dispatcher")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()

        if self._dispatcher_task:
            await self._dispatcher_task
            self._dispatcher_task = None

        if self._inflight_tasks:
            await asyncio.gather(*self._inflight_tasks, return_exceptions=True)

    async def publish(self, event: LoopEvent) -> None:
        await self._queue.put(event)

    async def _dispatch_loop(self) -> None:
        while self._running or not self._queue.empty():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if self._stop_event.is_set() and self._queue.empty():
                    break
                continue

            handlers = [*self._subscribers.get(event.type, []), *self._subscribers.get("*", [])]
            for handler in handlers:
                try:
                    result = handler(event)
                    if asyncio.iscoroutine(result):
                        task = asyncio.create_task(result)
                        self._inflight_tasks.add(task)
                        task.add_done_callback(self._inflight_tasks.discard)
                except Exception:
                    # Não deixamos um subscriber quebrar o bus.
                    continue
            self._queue.task_done()
