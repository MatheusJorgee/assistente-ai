"""
Telemetria estruturada (JSONL) para ferramentas host-level.

Padrão aplicado: Decorator + composição.
- O logger fica desacoplado da lógica de negócio.
- Cada tool envia evento estruturado após execução.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import asyncio
import json
from pathlib import Path
import threading
from typing import Any, Callable, Mapping, Optional


SENSITIVE_KEYS = {
    "content",
    "data",
    "password",
    "secret",
    "token",
    "api_key",
    "script",
}


@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    tool_name: str
    parameters: dict[str, Any]
    decision: str
    duration_ms: int
    success: bool
    message: str = ""


class AuditLogger:
    """Logger de auditoria em JSON Lines."""

    def __init__(self, log_file: Optional[str] = None) -> None:
        default_file = Path(".runtime") / "audit" / "host_audit.jsonl"
        self._log_file = Path(log_file) if log_file else default_file
        self._lock = threading.Lock()
        self._log_file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def log_file(self) -> Path:
        return self._log_file

    def write_event(self, event: AuditEvent) -> None:
        payload = asdict(event)
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with self._log_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolCallTelemetry:
    """Helper para gerar eventos de execução de tool com máscara de parâmetros."""

    logger: AuditLogger
    event_publisher: Optional[Callable[[dict[str, Any]], None]] = None

    def emit(
        self,
        *,
        tool_name: str,
        parameters: Mapping[str, Any],
        decision: str,
        duration_ms: int,
        success: bool,
        message: str = "",
    ) -> None:
        event = AuditEvent(
            timestamp=self.logger.now_iso(),
            tool_name=tool_name,
            parameters=self._mask_parameters(parameters),
            decision=decision,
            duration_ms=duration_ms,
            success=success,
            message=message,
        )
        self.logger.write_event(event)

        if self.event_publisher:
            payload = {
                "type": "audit_event",
                "timestamp": event.timestamp,
                "tool_name": event.tool_name,
                "parameters": event.parameters,
                "decision": event.decision,
                "duration_ms": event.duration_ms,
                "success": event.success,
                "message": event.message,
            }
            try:
                self.event_publisher(payload)
            except Exception:
                # Telemetria não deve quebrar execução principal.
                pass

    def _mask_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        masked: dict[str, Any] = {}
        for key, value in parameters.items():
            lowered = key.lower()
            if lowered in SENSITIVE_KEYS:
                masked[key] = "***masked***"
                continue

            if isinstance(value, str) and len(value) > 500:
                masked[key] = value[:500] + "...[truncated]"
                continue

            masked[key] = value

        return masked
