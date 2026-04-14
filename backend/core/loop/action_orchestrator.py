"""
Action Orchestrator: fecha o ciclo ReAct (Reason -> Act -> Observe).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

try:
    from .. import get_logger
    from .event_bus import AsyncEventBus, LoopEvent
except ImportError:
    from .. import get_logger
    from .event_bus import AsyncEventBus, LoopEvent

logger = get_logger(__name__)


class ActionOrchestrator:
    """
    Orquestra execuÃ§Ã£o de aÃ§Ãµes a partir de eventos autonomous_decision.

    Responsabilidades:
    - Executar tool calls no registry
    - Publicar action_completed/action_failed
    - Em falha, solicitar estratÃ©gia alternativa ao Brain (ReAct feedback)
    - Aplicar limite de passos (circuit breaker)
    """

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus,
        tool_registry: Any,
        brain: Any,
        max_steps: int = 3,
    ) -> None:
        self._bus = event_bus
        self._tool_registry = tool_registry
        self._brain = brain
        self._max_steps = max(1, max_steps)
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._bus.subscribe("autonomous_decision", self._on_autonomous_decision)
        logger.info("[ORCHESTRATOR] ActionOrchestrator iniciado")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._bus.unsubscribe("autonomous_decision", self._on_autonomous_decision)
        logger.info("[ORCHESTRATOR] ActionOrchestrator encerrado")

    async def _on_autonomous_decision(self, event: LoopEvent) -> None:
        if not self._running:
            return

        payload = event.payload or {}
        origin_event = str(payload.get("origin_event", "unknown"))

        initial_call = self._extract_tool_call(payload)
        if not initial_call:
            decision = str(payload.get("decision", "")).strip()
            await self._publish_failed(
                origin_event=origin_event,
                step=0,
                reason="DecisÃ£o sem tool_call executÃ¡vel",
                last_output=decision,
            )
            return

        current_call = initial_call
        last_output = ""

        for step in range(1, self._max_steps + 1):
            ok, output = await self._execute_tool_call(current_call)
            last_output = output

            if ok:
                await self._bus.publish(
                    LoopEvent(
                        type="action_completed",
                        payload={
                            "origin_event": origin_event,
                            "step": step,
                            "tool_call": current_call,
                            "output": output,
                        },
                        source="action_orchestrator",
                    )
                )
                logger.info(f"[ORCHESTRATOR] aÃ§Ã£o concluÃ­da em {step} passo(s)")
                return

            if step >= self._max_steps:
                break

            next_call = await self._request_alternative_tool_call(
                origin_event=origin_event,
                failed_call=current_call,
                failure_output=output,
                step=step,
            )
            if not next_call:
                await self._publish_failed(
                    origin_event=origin_event,
                    step=step,
                    reason="Brain nÃ£o forneceu estratÃ©gia alternativa executÃ¡vel",
                    last_output=output,
                )
                return

            current_call = next_call

        await self._publish_failed(
            origin_event=origin_event,
            step=self._max_steps,
            reason=f"MAX_STEPS atingido ({self._max_steps})",
            last_output=last_output,
        )

    async def _execute_tool_call(self, tool_call: dict[str, Any]) -> tuple[bool, str]:
        tool_name = str(tool_call.get("name", "")).strip()
        arguments = tool_call.get("arguments", {})
        if not tool_name:
            return False, "[TOOL_ERROR] tool_call sem nome"
        if not isinstance(arguments, dict):
            return False, "[TOOL_ERROR] arguments deve ser objeto"

        try:
            result = await self._tool_registry.execute(tool_name, **arguments)
        except Exception as exc:
            return False, f"[TOOL_ERROR] exceÃ§Ã£o no registry: {type(exc).__name__}: {exc}"

        success_attr = bool(getattr(result, "success", False)) if hasattr(result, "success") else True
        output_attr = str(getattr(result, "output", result) or "")
        error_attr = str(getattr(result, "error", "") or "")

        output = output_attr if output_attr else error_attr

        if not success_attr:
            return False, output or "[TOOL_ERROR] execuÃ§Ã£o falhou sem detalhes"

        upper = output.upper()
        if "[POLICY_BLOCKED]" in upper or "[TOOL_ERROR]" in upper or "[ERRO]" in upper:
            return False, output

        return True, output

    async def _request_alternative_tool_call(
        self,
        *,
        origin_event: str,
        failed_call: dict[str, Any],
        failure_output: str,
        step: int,
    ) -> Optional[dict[str, Any]]:
        prompt = (
            "[AUTONOMOUS_REACT_RECOVERY]\n"
            f"Evento original: {origin_event}\n"
            f"Tentativa: {step}\n"
            f"Tool call que falhou: {json.dumps(failed_call, ensure_ascii=False)}\n"
            f"Motivo da falha: {failure_output}\n\n"
            "ForneÃ§a UMA alternativa em JSON puro com este formato:\n"
            '{"tool_call": {"name": "nome_tool", "arguments": {}}}\n'
            "Se nÃ£o houver alternativa segura, responda exatamente: NADA"
        )

        try:
            brain_resp = await self._brain.ask(prompt, include_vision=False)
            text = (brain_resp.text or "").strip()
        except Exception as exc:
            logger.warning(f"[ORCHESTRATOR] Brain falhou no recovery: {exc}")
            return None

        if not text or text.upper() == "NADA":
            return None

        return self._extract_tool_call({"decision": text})

    async def _publish_failed(self, *, origin_event: str, step: int, reason: str, last_output: str) -> None:
        await self._bus.publish(
            LoopEvent(
                type="action_failed",
                payload={
                    "origin_event": origin_event,
                    "step": step,
                    "reason": reason,
                    "last_output": last_output,
                },
                source="action_orchestrator",
            )
        )
        logger.warning(f"[ORCHESTRATOR] aÃ§Ã£o falhou: {reason}")

    def _extract_tool_call(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        if isinstance(payload.get("tool_call"), dict):
            call = payload["tool_call"]
            if "name" in call:
                return {
                    "name": call.get("name"),
                    "arguments": call.get("arguments", {}) if isinstance(call.get("arguments", {}), dict) else {},
                }

        if isinstance(payload.get("tool_calls"), list) and payload["tool_calls"]:
            call = payload["tool_calls"][0]
            if isinstance(call, dict) and "name" in call:
                return {
                    "name": call.get("name"),
                    "arguments": call.get("arguments", {}) if isinstance(call.get("arguments", {}), dict) else {},
                }

        decision_text = str(payload.get("decision", "")).strip()
        if not decision_text:
            return None

        # Tenta JSON bruto com tool_call
        try:
            parsed = json.loads(decision_text)
            if isinstance(parsed, dict):
                if "tool_call" in parsed and isinstance(parsed["tool_call"], dict):
                    tc = parsed["tool_call"]
                    if "name" in tc:
                        return {
                            "name": tc.get("name"),
                            "arguments": tc.get("arguments", {}) if isinstance(tc.get("arguments", {}), dict) else {},
                        }
                if "name" in parsed:
                    return {
                        "name": parsed.get("name"),
                        "arguments": parsed.get("arguments", {}) if isinstance(parsed.get("arguments", {}), dict) else {},
                    }
        except json.JSONDecodeError:
            pass

        return None

