"""
PowerShell Executor: execuÃ§Ã£o segura de comandos no Windows PowerShell.

Recursos:
- timeout
- dry-run
- captura de stdout/stderr
- integraÃ§Ã£o com PolicyEngine
"""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
import time
from typing import Mapping, Optional

try:
    from core.policy.policy_engine import OSAction, PolicyContext, PolicyEngine
except ImportError:
    from core.policy.policy_engine import OSAction, PolicyContext, PolicyEngine


MAX_CAPTURE_CHARS = 8000


@dataclass(frozen=True)
class PowerShellCommand:
    """Comando PowerShell e metadados de execuÃ§Ã£o."""

    script: str
    timeout_seconds: float = 15.0
    dry_run: bool = False
    cwd: Optional[str] = None


@dataclass(frozen=True)
class CommandExecutionResult:
    """Resultado padronizado da execuÃ§Ã£o de comando."""

    command: str
    return_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    dry_run: bool

    @property
    def success(self) -> bool:
        return self.return_code == 0 and not self.timed_out


class PowerShellExecutor:
    """Adapter de execuÃ§Ã£o PowerShell com validaÃ§Ã£o de policy."""

    def __init__(self, policy_engine: PolicyEngine) -> None:
        self._policy_engine = policy_engine

    def execute(
        self,
        command: PowerShellCommand,
        *,
        context: Optional[PolicyContext] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> CommandExecutionResult:
        """Executa (ou simula) um script PowerShell."""
        self._policy_engine.assert_allowed(
            OSAction.EXECUTE_POWERSHELL,
            command=command.script,
            context=context,
        )

        if command.dry_run:
            return CommandExecutionResult(
                command=command.script,
                return_code=0,
                stdout="[DRY-RUN] Comando validado, execuÃ§Ã£o nÃ£o realizada.",
                stderr="",
                duration_ms=0,
                timed_out=False,
                dry_run=True,
            )

        started = time.perf_counter()
        ps_args = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command.script,
        ]

        try:
            completed = subprocess.run(
                ps_args,
                capture_output=True,
                text=True,
                timeout=command.timeout_seconds,
                cwd=command.cwd,
                env=dict(env) if env else None,
                check=False,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CommandExecutionResult(
                command=command.script,
                return_code=completed.returncode,
                stdout=_truncate_output(completed.stdout),
                stderr=_truncate_output(completed.stderr),
                duration_ms=duration_ms,
                timed_out=False,
                dry_run=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            stdout = _truncate_output((exc.stdout or "") if isinstance(exc.stdout, str) else "")
            stderr = _truncate_output((exc.stderr or "") if isinstance(exc.stderr, str) else "")
            return CommandExecutionResult(
                command=command.script,
                return_code=124,
                stdout=stdout,
                stderr=stderr or "Timeout: comando excedeu tempo limite.",
                duration_ms=duration_ms,
                timed_out=True,
                dry_run=False,
            )


def _truncate_output(output: str) -> str:
    if len(output) <= MAX_CAPTURE_CHARS:
        return output
    return output[:MAX_CAPTURE_CHARS] + "\n...[output truncated]"

