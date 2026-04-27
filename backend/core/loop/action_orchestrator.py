"""
Action Orchestrator: fecha o ciclo ReAct (Reason -> Act -> Observe).

Implementa Circuit Breaker + Heurística de Fallback para evitar consumo
desenfreado de tokens em caso de loop de erros.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta

try:
    from .. import get_logger
    from .event_bus import AsyncEventBus, LoopEvent
except ImportError:
    from .. import get_logger
    from .event_bus import AsyncEventBus, LoopEvent

logger = get_logger(__name__)


class ErrorType(Enum):
    """Classificação de tipos de erro para análise heurística."""
    MISSING_PARAMETER = "missing_parameter"
    INVALID_PARAMETER = "invalid_parameter"
    TOOL_NOT_FOUND = "tool_not_found"
    POLICY_BLOCKED = "policy_blocked"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class CircuitBreakerState:
    """Rastreamento de estado do Circuit Breaker para evitar loop infinito."""
    failed_attempts: int = 0
    last_failure_time: Optional[datetime] = None
    circuit_open: bool = False
    error_type_counts: dict[str, int] = field(default_factory=dict)
    
    def record_failure(self, error_type: ErrorType) -> None:
        """Registra uma falha e atualiza estado do circuit breaker."""
        self.failed_attempts += 1
        self.last_failure_time = datetime.now()
        self.error_type_counts[error_type.value] = self.error_type_counts.get(error_type.value, 0) + 1
        
        # Abrir circuito após 5 falhas do mesmo tipo
        if self.error_type_counts[error_type.value] >= 5:
            self.circuit_open = True
            logger.warning(
                f"[CIRCUIT_BREAKER] Circuito aberto após {self.failed_attempts} falhas. "
                f"Tipo dominante: {error_type.value} ({self.error_type_counts[error_type.value]}x)"
            )
    
    def is_open(self) -> bool:
        """Verifica se o circuit breaker está aberto."""
        return self.circuit_open
    
    def reset(self) -> None:
        """Reseta o estado do circuit breaker."""
        self.failed_attempts = 0
        self.circuit_open = False
        self.error_type_counts.clear()
        self.last_failure_time = None


class ErrorAnalyzer:
    """Análise heurística de erros para tentar recuperação sem LLM."""
    
    @staticmethod
    def classify_error(error_output: str) -> ErrorType:
        """Classifica o tipo de erro baseado no conteúdo."""
        upper = error_output.upper()
        
        # Padrões de detecção
        if any(x in upper for x in ["MISSING", "REQUIRED", "OBRIGATÓRIO", "AUSENTE"]):
            return ErrorType.MISSING_PARAMETER
        
        if any(x in upper for x in ["INVALID", "INVÁLIDO", "TYPE", "TIPO", "FORMAT", "FORMATO"]):
            return ErrorType.INVALID_PARAMETER
        
        if any(x in upper for x in ["NOT FOUND", "NÃO ENCONTR"]):
            return ErrorType.TOOL_NOT_FOUND
        
        if "[POLICY_BLOCKED]" in upper or "BLOCKED" in upper:
            return ErrorType.POLICY_BLOCKED
        
        if "TIMEOUT" in upper or "TEMPO LIMITE" in upper:
            return ErrorType.TIMEOUT
        
        if any(x in upper for x in ["NETWORK", "CONNECTION", "CONEXÃO"]):
            return ErrorType.NETWORK_ERROR
        
        return ErrorType.UNKNOWN
    
    @staticmethod
    def extract_missing_parameter(error_output: str, failed_call: dict[str, Any]) -> Optional[tuple[str, Any]]:
        """
        Tenta extrair o parâmetro faltante do erro e sugerir um valor padrão.
        
        Exemplo:
        - Error: "missing: 'search_query'"
        - Return: ("search_query", "[search]")
        """
        # Detectar qual parâmetro está faltando
        patterns = [
            r"'(\w+)'",  # 'param_name'
            r'"(\w+)"',  # "param_name"
            r":\s*(\w+)",  # : param_name
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, error_output)
            if matches:
                param_name = matches[0]
                # Se é um parâmetro conhecido, retornar valor padrão
                defaults = {
                    "search": "[search]",
                    "search_query": "[search]",
                    "query": "[search]",
                    "text": "[text]",
                    "message": "[message]",
                    "pesquisa": "[pesquisa]",
                }
                default_value = defaults.get(param_name, f"[{param_name}]")
                return param_name, default_value
        
        return None
    
    @staticmethod
    def try_recover_from_error(
        error_output: str,
        failed_call: dict[str, Any],
        error_type: ErrorType
    ) -> Optional[dict[str, Any]]:
        """
        Tenta recuperação heurística do erro sem chamar LLM.
        
        Returns:
            - dict com tool_call corrigida se sucesso
            - None se não conseguir recuperar
        """
        
        # Estratégia 1: Parâmetro faltante - adicionar padrão
        if error_type == ErrorType.MISSING_PARAMETER:
            result = ErrorAnalyzer.extract_missing_parameter(error_output, failed_call)
            if result:
                param_name, default_value = result
                recovered_call = failed_call.copy()
                recovered_call["arguments"] = failed_call.get("arguments", {}).copy()
                recovered_call["arguments"][param_name] = default_value
                logger.info(
                    f"[ERROR_ANALYZER] Recuperação heurística: adicionado {param_name}={default_value}"
                )
                return recovered_call
        
        # Estratégia 2: Tipo de parâmetro inválido - tentar parsear como string
        if error_type == ErrorType.INVALID_PARAMETER:
            if failed_call.get("arguments"):
                recovered_call = failed_call.copy()
                new_args = {}
                for k, v in failed_call["arguments"].items():
                    # Converter para string se for número/booleano
                    new_args[k] = str(v) if not isinstance(v, str) else v
                recovered_call["arguments"] = new_args
                # Só retornar se algo mudou
                if recovered_call != failed_call:
                    logger.info(f"[ERROR_ANALYZER] Recuperação heurística: argumentos convertidos para string")
                    return recovered_call
        
        # Estratégia 3: Ferramenta não existe - retornar None (não há retry)
        if error_type == ErrorType.TOOL_NOT_FOUND:
            logger.info(f"[ERROR_ANALYZER] Tool não encontrada - sem retry possível")
            return None
        
        # Estratégia 4: Bloqueado por política - retornar None (não há retry)
        if error_type == ErrorType.POLICY_BLOCKED:
            logger.info(f"[ERROR_ANALYZER] Bloqueado por política - sem retry possível")
            return None
        
        return None


class ActionOrchestrator:
    """
    Orquestra execução de ações a partir de eventos autonomous_decision.

    Responsabilidades:
    - Executar tool calls no registry
    - Publicar action_completed/action_failed
    - Em falha, tentar recuperação heurística ANTES de chamar Brain (Circuit Breaker)
    - Se heurística falhar, chamar Brain com versão light (ask_for_recovery)
    - Aplicar limite de passos e evitar loop infinito
    """

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus,
        tool_registry: Any,
        brain: Any,
        max_steps: int = 3,
        max_llm_fallbacks: int = 1,
    ) -> None:
        self._bus = event_bus
        self._tool_registry = tool_registry
        self._brain = brain
        self._max_steps = max(1, max_steps)
        self._max_llm_fallbacks = max(0, max_llm_fallbacks)  # 0 = nunca chamar LLM em fallback
        self._running = False
        self._circuit_breaker = CircuitBreakerState()
        self._error_analyzer = ErrorAnalyzer()

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
        
        # ===== PROTEÇÃO: Circuit Breaker aberto? =====
        if self._circuit_breaker.is_open():
            logger.warning(f"[ORCHESTRATOR] Circuit Breaker ABERTO - rejeitando execução")
            return

        payload = event.payload or {}
        origin_event = str(payload.get("origin_event", "unknown"))

        initial_call = self._extract_tool_call(payload)
        if not initial_call:
            decision = str(payload.get("decision", "")).strip()
            await self._publish_failed(
                origin_event=origin_event,
                step=0,
                reason="Decisão sem tool_call executável",
                last_output=decision,
            )
            return

        current_call = initial_call
        last_output = ""
        llm_recovery_used = 0

        for step in range(1, self._max_steps + 1):
            ok, output = await self._execute_tool_call(current_call)
            last_output = output

            if ok:
                # ===== SUCESSO: reseta circuit breaker =====
                self._circuit_breaker.reset()
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
                logger.info(f"[ORCHESTRATOR] ação concluída em {step} passo(s)")
                return
            
            # ===== FALHA: Tentar recuperação =====
            if step >= self._max_steps:
                break

            next_call = await self._request_alternative_tool_call(
                origin_event=origin_event,
                failed_call=current_call,
                failure_output=output,
                step=step,
                llm_recovery_attempts_left=self._max_llm_fallbacks - llm_recovery_used,
            )
            
            if not next_call:
                await self._publish_failed(
                    origin_event=origin_event,
                    step=step,
                    reason="Nenhuma estratégia alternativa disponível",
                    last_output=output,
                )
                return
            
            # Se LLM foi usado, incrementar contador
            if hasattr(next_call, "_used_llm") and next_call._used_llm:
                llm_recovery_used += 1
                delattr(next_call, "_used_llm")

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
            error_output = f"[TOOL_ERROR] exceção no registry: {type(exc).__name__}: {exc}"
            error_type = self._error_analyzer.classify_error(error_output)
            self._circuit_breaker.record_failure(error_type)
            return False, error_output

        success_attr = bool(getattr(result, "success", False)) if hasattr(result, "success") else True
        output_attr = str(getattr(result, "output", result) or "")
        error_attr = str(getattr(result, "error", "") or "")

        output = output_attr if output_attr else error_attr

        if not success_attr:
            final_output = output or "[TOOL_ERROR] execução falhou sem detalhes"
            error_type = self._error_analyzer.classify_error(final_output)
            self._circuit_breaker.record_failure(error_type)
            return False, final_output

        upper = output.upper()
        if "[POLICY_BLOCKED]" in upper or "[TOOL_ERROR]" in upper or "[ERRO]" in upper:
            error_type = self._error_analyzer.classify_error(output)
            self._circuit_breaker.record_failure(error_type)
            return False, output

        return True, output

    async def _request_alternative_tool_call(
        self,
        *,
        origin_event: str,
        failed_call: dict[str, Any],
        failure_output: str,
        step: int,
        llm_recovery_attempts_left: int = 1,
    ) -> Optional[dict[str, Any]]:
        """
        Tenta recuperação de falha seguindo estratégia Circuit Breaker + Heurística.
        
        Ordem de tentativa:
        1. Análise heurística (sem LLM, sem tokens)
        2. Se falhar, chamar Brain.ask_for_recovery() com histórico leve
        3. Se ainda falhar, retornar None
        """
        error_type = self._error_analyzer.classify_error(failure_output)
        
        logger.info(
            f"[ORCHESTRATOR] Falha no passo {step}: {error_type.value} "
            f"(sem parâmetro ou algo nos argumentos)"
        )
        
        # ===== ESTRATÉGIA 1: Análise Heurística (GRATUITA) =====
        heuristic_recovery = self._error_analyzer.try_recover_from_error(
            error_output=failure_output,
            failed_call=failed_call,
            error_type=error_type,
        )
        
        if heuristic_recovery:
            logger.info(f"[ORCHESTRATOR] ✅ Recuperação heurística bem-sucedida")
            return heuristic_recovery
        
        # ===== Se heurística falhou, verificar se LLM está permitido =====
        if llm_recovery_attempts_left <= 0:
            logger.info(
                f"[ORCHESTRATOR] ⚠️ Tentativas de LLM-recovery esgotadas. "
                f"Encerrando sem estratégia alternativa (economy mode)"
            )
            return None
        
        # ===== ESTRATÉGIA 2: Chamar Brain.ask_for_recovery() (LEVE) =====
        logger.info(f"[ORCHESTRATOR] Escalando para Brain.ask_for_recovery() (mode=leve)")
        
        try:
            next_call = await self._brain.ask_for_recovery(
                failed_tool_call=failed_call,
                error_output=failure_output,
                context_step=step,
            )
            
            if next_call:
                logger.info(f"[ORCHESTRATOR] ✅ Brain recovery bem-sucedida")
                # Marcar que usamos LLM (para accounting)
                next_call._used_llm = True
                return next_call
            
        except Exception as exc:
            logger.warning(f"[ORCHESTRATOR] Brain.ask_for_recovery() falhou: {exc}")
        
        logger.info(f"[ORCHESTRATOR] ❌ Nenhuma estratégia de recuperação disponível")
        return None

    async def _publish_failed(self, *, origin_event: str, step: int, reason: str, last_output: str) -> None:
        circuit_status = "OPEN" if self._circuit_breaker.is_open() else "CLOSED"
        await self._bus.publish(
            LoopEvent(
                type="action_failed",
                payload={
                    "origin_event": origin_event,
                    "step": step,
                    "reason": reason,
                    "last_output": last_output,
                    "circuit_breaker_status": circuit_status,
                    "total_failures": self._circuit_breaker.failed_attempts,
                },
                source="action_orchestrator",
            )
        )
        logger.warning(
            f"[ORCHESTRATOR] ação falhou: {reason} "
            f"[Circuit Breaker: {circuit_status}, Total falhas: {self._circuit_breaker.failed_attempts}]"
        )

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

    # ===== CIRCUIT BREAKER API =====
    
    def get_circuit_status(self) -> dict[str, Any]:
        """Retorna status atual do circuit breaker para monitoramento."""
        return {
            "open": self._circuit_breaker.is_open(),
            "failed_attempts": self._circuit_breaker.failed_attempts,
            "error_counts": self._circuit_breaker.error_type_counts,
            "last_failure_time": self._circuit_breaker.last_failure_time.isoformat() if self._circuit_breaker.last_failure_time else None,
        }
    
    def reset_circuit(self) -> None:
        """Reseta o circuit breaker (CUIDADO: uso manual apenas em recovery)."""
        old_status = self.get_circuit_status()
        self._circuit_breaker.reset()
        logger.info(f"[ORCHESTRATOR] Circuit Breaker resetado. Status anterior: {old_status}")

