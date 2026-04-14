"""
Process Adapter: abstraÃ§Ã£o para operaÃ§Ãµes de processo no host.

Fornece um contrato tipado para listar/iniciar/finalizar processos no Windows,
respeitando PolicyEngine.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import subprocess
from typing import Optional

try:
    from ..policy.policy_engine import OSAction, PolicyContext, PolicyEngine
except ImportError:
    try:
        from core.policy.policy_engine import OSAction, PolicyContext, PolicyEngine
    except ImportError:
        OSAction = None
        PolicyContext = None
        PolicyEngine = None


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    image_name: str
    session_name: str
    session_num: str
    mem_usage: str


@dataclass(frozen=True)
class ProcessStartRequest:
    executable: str
    args: tuple[str, ...] = ()
    cwd: Optional[str] = None


@dataclass(frozen=True)
class ProcessStartResult:
    pid: int
    started: bool
    command_line: str


@dataclass(frozen=True)
class ProcessStopResult:
    pid: int
    stopped: bool
    return_code: int
    stderr: str


class ProcessAdapter:
    """Porta de processos (contrato de baixo nÃ­vel para OS host)."""

    def __init__(self, policy_engine: PolicyEngine) -> None:
        self._policy_engine = policy_engine

    def list_processes(self, *, context: Optional[PolicyContext] = None) -> list[ProcessInfo]:
        self._policy_engine.assert_allowed(OSAction.PROCESS_LIST, context=context)

        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Falha ao listar processos: {completed.stderr.strip()}")

        reader = csv.reader(io.StringIO(completed.stdout))
        processes: list[ProcessInfo] = []
        for row in reader:
            if len(row) < 5:
                continue
            pid_str = row[1].replace(",", "").strip()
            if not pid_str.isdigit():
                continue
            processes.append(
                ProcessInfo(
                    pid=int(pid_str),
                    image_name=row[0].strip(),
                    session_name=row[2].strip(),
                    session_num=row[3].strip(),
                    mem_usage=row[4].strip(),
                )
            )
        return processes

    def start_process(
        self,
        request: ProcessStartRequest,
        *,
        context: Optional[PolicyContext] = None,
    ) -> ProcessStartResult:
        command_text = " ".join((request.executable, *request.args)).strip()
        self._policy_engine.assert_allowed(
            OSAction.PROCESS_START,
            command=command_text,
            context=context,
        )

        proc = subprocess.Popen(
            [request.executable, *request.args],
            cwd=request.cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return ProcessStartResult(
            pid=proc.pid,
            started=True,
            command_line=command_text,
        )

    def stop_process(
        self,
        pid: int,
        *,
        force: bool = True,
        context: Optional[PolicyContext] = None,
    ) -> ProcessStopResult:
        self._policy_engine.assert_allowed(
            OSAction.PROCESS_STOP,
            command=f"pid={pid}",
            context=context,
        )

        args = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            args.append("/F")

        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )

        return ProcessStopResult(
            pid=pid,
            stopped=completed.returncode == 0,
            return_code=completed.returncode,
            stderr=completed.stderr.strip(),
        )

    def is_running(self, pid: int, *, context: Optional[PolicyContext] = None) -> bool:
        self._policy_engine.assert_allowed(OSAction.PROCESS_LIST, context=context)

        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return False

        return str(pid) in completed.stdout

