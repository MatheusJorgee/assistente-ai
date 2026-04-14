"""
OS Tools (v2): thin tools que conectam o cÃ©rebro aos adapters de host.

Estas ferramentas foram desenhadas para function calling semÃ¢ntico:
- descriÃ§Ãµes claras para o LLM decidir quando usar
- parÃ¢metros explÃ­citos e previsÃ­veis
- retorno amigÃ¡vel em caso de bloqueio por policy
"""

from __future__ import annotations

from dataclasses import asdict
import time
from typing import Optional

try:
    from core import (
        OSAction,
        PolicyContext,
        PolicyEngine,
        PowerShellCommand,
        PowerShellExecutor,
        ProcessAdapter,
        ProcessStartRequest,
        ToolCallTelemetry,
        get_logger,
    )
    from core.tools.base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
except ImportError:
    from core import (
        OSAction,
        PolicyContext,
        PolicyEngine,
        PowerShellCommand,
        PowerShellExecutor,
        ProcessAdapter,
        ProcessStartRequest,
        ToolCallTelemetry,
        get_logger,
    )
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter

logger = get_logger(__name__)


class OSCommandTool(MotorTool):
    """
    Executa comandos PowerShell no host Windows com seguranÃ§a e auditoria.

    Quando usar:
    - consultar estado do sistema via cmdlets (ex: Get-Process, Get-Service)
    - operaÃ§Ãµes administrativas permitidas pela policy

    Quando NÃƒO usar:
    - aÃ§Ãµes destrutivas, shutdown/restart, deleÃ§Ã£o recursiva forÃ§ada
    - comandos fora da polÃ­tica vigente
    """

    def __init__(self, executor: PowerShellExecutor, telemetry: Optional[ToolCallTelemetry] = None):
        self._executor = executor
        self._telemetry = telemetry
        super().__init__(
            metadata=ToolMetadata(
                name="v2_os_command",
                description=(
                    "Executa script PowerShell no host Windows com controle de timeout, "
                    "modo de simulaÃ§Ã£o (dry-run) e enforcement de polÃ­ticas de seguranÃ§a. "
                    "Retorna stdout e stderr de forma segura para tomada de decisÃ£o do agente."
                ),
                category="os",
                parameters=[
                    ToolParameter(
                        name="script",
                        type="string",
                        description=(
                            "Script PowerShell a executar. Use comandos explÃ­citos e curtos, "
                            "por exemplo: Get-Process | Select-Object -First 5"
                        ),
                        required=True,
                    ),
                    ToolParameter(
                        name="timeout_seconds",
                        type="int",
                        description="Tempo limite em segundos para execuÃ§Ã£o do comando.",
                        required=False,
                        default=15,
                    ),
                    ToolParameter(
                        name="dry_run",
                        type="bool",
                        description=(
                            "Se true, apenas valida e simula sem executar no sistema."
                        ),
                        required=False,
                        default=False,
                    ),
                ],
                examples=[
                    "script='Get-Process | Sort-Object CPU -Descending | Select-Object -First 5'",
                    "script='Get-Service | Where-Object {$_.Status -eq \"Running\"} | Select-Object -First 10'",
                    "script='New-Item -ItemType Directory -Path $env:USERPROFILE\\Desktop\\teste_quinta_feira'",
                ],
                security_level=SecurityLevel.CRITICAL,
                tags=["os", "powershell", "automation", "v2"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        script = kwargs.get("script")
        return isinstance(script, str) and bool(script.strip())

    async def execute(self, **kwargs) -> str:
        started = time.perf_counter()
        script = kwargs["script"].strip()
        timeout_seconds = float(kwargs.get("timeout_seconds", 15))
        dry_run = bool(kwargs.get("dry_run", False))

        try:
            result = self._executor.execute(
                PowerShellCommand(
                    script=script,
                    timeout_seconds=timeout_seconds,
                    dry_run=dry_run,
                ),
                context=PolicyContext(actor="llm", tags=frozenset({"tool:v2_os_command"})),
            )
        except PermissionError as e:
            self._emit_telemetry(
                kwargs=kwargs,
                decision="DENY",
                success=False,
                duration_ms=_duration_ms(started),
                message=str(e),
            )
            return f"[POLICY_BLOCKED] AÃ§Ã£o bloqueada pela polÃ­tica de seguranÃ§a: {e}"
        except Exception as e:
            self._emit_telemetry(
                kwargs=kwargs,
                decision="ALLOW",
                success=False,
                duration_ms=_duration_ms(started),
                message=f"{type(e).__name__}: {e}",
            )
            return f"[TOOL_ERROR] Falha ao executar comando PowerShell: {type(e).__name__}: {e}"

        payload = {
            "success": result.success,
            "dry_run": result.dry_run,
            "timed_out": result.timed_out,
            "return_code": result.return_code,
            "duration_ms": result.duration_ms,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        self._emit_telemetry(
            kwargs=kwargs,
            decision="ALLOW",
            success=result.success,
            duration_ms=result.duration_ms,
            message="OK" if result.success else "ExecuÃ§Ã£o com falha",
        )
        return str(payload)

    def _emit_telemetry(
        self,
        *,
        kwargs: dict,
        decision: str,
        success: bool,
        duration_ms: int,
        message: str,
    ) -> None:
        if not self._telemetry:
            return
        self._telemetry.emit(
            tool_name=self.metadata.name,
            parameters=kwargs,
            decision=decision,
            duration_ms=duration_ms,
            success=success,
            message=message,
        )


class ProcessControlTool(MotorTool):
    """
    Controla e inspeciona processos do host via ProcessAdapter.

    AÃ§Ãµes disponÃ­veis:
    - list: lista processos (opcionalmente ordenando por memÃ³ria)
    - start: inicia um processo
    - stop: finaliza processo por PID

    ObservaÃ§Ã£o para o LLM:
    - Para diagnÃ³stico de consumo de RAM, use action='list' com sort_by='memory'.
    """

    def __init__(
        self,
        process_adapter: ProcessAdapter,
        policy_engine: PolicyEngine,
        telemetry: Optional[ToolCallTelemetry] = None,
    ):
        self._process_adapter = process_adapter
        self._policy = policy_engine
        self._telemetry = telemetry
        super().__init__(
            metadata=ToolMetadata(
                name="v2_process_control",
                description=(
                    "Lista, inicia e finaliza processos no host de forma segura. "
                    "Ideal para diagnÃ³stico de consumo de memÃ³ria/CPU e orquestraÃ§Ã£o "
                    "de processos auxiliares do agente."
                ),
                category="os",
                parameters=[
                    ToolParameter(
                        name="action",
                        type="string",
                        description="AÃ§Ã£o desejada: list, start ou stop.",
                        required=True,
                        choices=["list", "start", "stop"],
                    ),
                    ToolParameter(
                        name="limit",
                        type="int",
                        description="Quantidade mÃ¡xima de processos no resultado de list.",
                        required=False,
                        default=20,
                    ),
                    ToolParameter(
                        name="sort_by",
                        type="string",
                        description="CritÃ©rio de ordenaÃ§Ã£o para list: memory ou name.",
                        required=False,
                        default="memory",
                        choices=["memory", "name"],
                    ),
                    ToolParameter(
                        name="executable",
                        type="string",
                        description="ExecutÃ¡vel para action=start (ex: notepad.exe).",
                        required=False,
                    ),
                    ToolParameter(
                        name="args",
                        type="list",
                        description="Lista de argumentos para action=start.",
                        required=False,
                        default=[],
                    ),
                    ToolParameter(
                        name="pid",
                        type="int",
                        description="PID para action=stop.",
                        required=False,
                    ),
                    ToolParameter(
                        name="force",
                        type="bool",
                        description="Se true, encerra processo com forÃ§a em action=stop.",
                        required=False,
                        default=True,
                    ),
                ],
                examples=[
                    "action='list', sort_by='memory', limit=10",
                    "action='start', executable='notepad.exe', args=[]",
                    "action='stop', pid=1234, force=true",
                ],
                security_level=SecurityLevel.CRITICAL,
                tags=["os", "process", "diagnostics", "v2"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        action = str(kwargs.get("action", "")).lower()
        if action not in {"list", "start", "stop"}:
            return False
        if action == "start":
            executable = kwargs.get("executable")
            return isinstance(executable, str) and bool(executable.strip())
        if action == "stop":
            pid = kwargs.get("pid")
            return isinstance(pid, int) and pid > 0
        return True

    async def execute(self, **kwargs) -> str:
        started = time.perf_counter()
        action = str(kwargs.get("action", "")).lower()
        context = PolicyContext(actor="llm", tags=frozenset({"tool:v2_process_control", f"action:{action}"}))

        try:
            if action == "list":
                result = self._execute_list(kwargs, context)
                self._emit_telemetry(kwargs=kwargs, decision="ALLOW", success=True, duration_ms=_duration_ms(started), message="OK")
                return result
            if action == "start":
                result = self._execute_start(kwargs, context)
                self._emit_telemetry(kwargs=kwargs, decision="ALLOW", success=True, duration_ms=_duration_ms(started), message="OK")
                return result
            if action == "stop":
                result = self._execute_stop(kwargs, context)
                self._emit_telemetry(kwargs=kwargs, decision="ALLOW", success=True, duration_ms=_duration_ms(started), message="OK")
                return result
            self._emit_telemetry(kwargs=kwargs, decision="ALLOW", success=False, duration_ms=_duration_ms(started), message="action invÃ¡lida")
            return "[TOOL_ERROR] action invÃ¡lida. Use list, start ou stop."
        except PermissionError as e:
            self._emit_telemetry(kwargs=kwargs, decision="DENY", success=False, duration_ms=_duration_ms(started), message=str(e))
            return f"[POLICY_BLOCKED] AÃ§Ã£o de processo bloqueada pela polÃ­tica: {e}"
        except Exception as e:
            self._emit_telemetry(kwargs=kwargs, decision="ALLOW", success=False, duration_ms=_duration_ms(started), message=f"{type(e).__name__}: {e}")
            return f"[TOOL_ERROR] Falha em process control: {type(e).__name__}: {e}"

    def _execute_list(self, kwargs: dict, context: PolicyContext) -> str:
        self._policy.assert_allowed(OSAction.PROCESS_LIST, context=context)

        processes = self._process_adapter.list_processes(context=context)
        sort_by = str(kwargs.get("sort_by", "memory")).lower()
        limit = int(kwargs.get("limit", 20))
        limit = max(1, min(limit, 200))

        if sort_by == "memory":
            processes = sorted(processes, key=lambda p: _memory_kb(p.mem_usage), reverse=True)
        else:
            processes = sorted(processes, key=lambda p: p.image_name.lower())

        rows = []
        for proc in processes[:limit]:
            rows.append(
                {
                    "pid": proc.pid,
                    "name": proc.image_name,
                    "memory": proc.mem_usage,
                    "session": proc.session_name,
                }
            )

        return str({"success": True, "count": len(rows), "items": rows})

    def _execute_start(self, kwargs: dict, context: PolicyContext) -> str:
        executable = str(kwargs["executable"]).strip()
        args = kwargs.get("args") or []
        if not isinstance(args, list):
            return "[TOOL_ERROR] args deve ser uma lista de strings."

        result = self._process_adapter.start_process(
            ProcessStartRequest(
                executable=executable,
                args=tuple(str(a) for a in args),
            ),
            context=context,
        )
        return str(asdict(result))

    def _execute_stop(self, kwargs: dict, context: PolicyContext) -> str:
        pid = int(kwargs["pid"])
        force = bool(kwargs.get("force", True))

        result = self._process_adapter.stop_process(
            pid=pid,
            force=force,
            context=context,
        )
        return str(asdict(result))


def _memory_kb(mem_usage: str) -> int:
    """Converte strings do tasklist (ex: '12,345 K') para inteiro em KB."""
    numeric = "".join(ch for ch in mem_usage if ch.isdigit())
    if not numeric:
        return 0
    try:
        return int(numeric)
    except ValueError:
        return 0


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

