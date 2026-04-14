"""
v2_file_ops: thin tool para operaÃ§Ãµes de arquivo em sandbox controlado.
"""

from __future__ import annotations

from dataclasses import asdict
import time
from typing import Optional

try:
    from core import (
        FileSystemAdapter,
        PolicyContext,
        ToolCallTelemetry,
    )
    from core.tools.base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
except ImportError:
    from core import FileSystemAdapter, PolicyContext, ToolCallTelemetry
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter


class FileOpsTool(MotorTool):
    """
    Opera arquivos e diretÃ³rios dentro de uma sandbox aprovada por policy.

    AÃ§Ãµes:
    - read_file: lÃª conteÃºdo UTF-8 de arquivo permitido
    - write_file: escreve conteÃºdo UTF-8 em arquivo permitido
    - list_dir: lista conteÃºdo de diretÃ³rio permitido
    - delete: remove arquivo/diretÃ³rio permitido

    Regras para paths:
    - Preferir caminhos absolutos em Windows (ex: C:\\Users\\...)
    - Caminhos relativos tambÃ©m sÃ£o aceitos, mas resolvidos no host
    - Toda operaÃ§Ã£o Ã© validada pela sandbox do PolicyEngine
    """

    def __init__(self, fs_adapter: FileSystemAdapter, telemetry: Optional[ToolCallTelemetry] = None):
        self._fs = fs_adapter
        self._telemetry = telemetry
        super().__init__(
            metadata=ToolMetadata(
                name="v2_file_ops",
                description=(
                    "Executa operaÃ§Ãµes de leitura, escrita, listagem e deleÃ§Ã£o de arquivos "
                    "em diretÃ³rios sandbox aprovados pela polÃ­tica. Use para persistÃªncia "
                    "controlada e manipulaÃ§Ã£o de dados do agente sem acesso global ao disco."
                ),
                category="os",
                parameters=[
                    ToolParameter(
                        name="action",
                        type="string",
                        description="AÃ§Ã£o: read_file, write_file, list_dir ou delete.",
                        required=True,
                        choices=["read_file", "write_file", "list_dir", "delete"],
                    ),
                    ToolParameter(
                        name="path",
                        type="string",
                        description=(
                            "Caminho do arquivo/diretÃ³rio no Windows. Exemplo absoluto: "
                            "C:\\Users\\mathe\\Documents\\assistente-ai\\.runtime\\sandbox\\nota.txt"
                        ),
                        required=True,
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="ConteÃºdo para write_file (UTF-8).",
                        required=False,
                    ),
                    ToolParameter(
                        name="overwrite",
                        type="bool",
                        description="Para write_file: sobrescreve se jÃ¡ existir.",
                        required=False,
                        default=True,
                    ),
                    ToolParameter(
                        name="limit",
                        type="int",
                        description="Para list_dir: mÃ¡ximo de itens no retorno.",
                        required=False,
                        default=100,
                    ),
                    ToolParameter(
                        name="recursive",
                        type="bool",
                        description="Para delete: remove diretÃ³rios com conteÃºdo.",
                        required=False,
                        default=False,
                    ),
                ],
                examples=[
                    "action='write_file', path='C:\\Users\\mathe\\Documents\\assistente-ai\\.runtime\\sandbox\\teste.txt', content='OlÃ¡ Quinta-Feira'",
                    "action='read_file', path='C:\\Users\\mathe\\Documents\\assistente-ai\\.runtime\\sandbox\\teste.txt'",
                    "action='list_dir', path='C:\\Users\\mathe\\Documents\\assistente-ai\\.runtime\\sandbox', limit=20",
                    "action='delete', path='C:\\Users\\mathe\\Documents\\assistente-ai\\.runtime\\sandbox\\teste.txt'",
                ],
                security_level=SecurityLevel.CRITICAL,
                tags=["filesystem", "sandbox", "os", "v2"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        action = str(kwargs.get("action", "")).lower()
        path = kwargs.get("path")
        if action not in {"read_file", "write_file", "list_dir", "delete"}:
            return False
        if not isinstance(path, str) or not path.strip():
            return False
        if action == "write_file" and "content" not in kwargs:
            return False
        return True

    async def execute(self, **kwargs) -> str:
        started = time.perf_counter()
        action = str(kwargs["action"]).lower()
        path = str(kwargs["path"])
        context = PolicyContext(actor="llm", tags=frozenset({"tool:v2_file_ops", f"action:{action}"}))

        try:
            if action == "read_file":
                result = self._fs.read_file(path=path, context=context)
                self._emit(kwargs=kwargs, decision="ALLOW", success=True, duration_ms=_duration_ms(started), message="OK")
                return str(asdict(result))

            if action == "write_file":
                content = str(kwargs.get("content", ""))
                overwrite = bool(kwargs.get("overwrite", True))
                result = self._fs.write_file(
                    path=path,
                    content=content,
                    overwrite=overwrite,
                    context=context,
                )
                self._emit(kwargs=kwargs, decision="ALLOW", success=True, duration_ms=_duration_ms(started), message="OK")
                return str(asdict(result))

            if action == "list_dir":
                limit = int(kwargs.get("limit", 100))
                items = self._fs.list_directory(path=path, limit=limit, context=context)
                rows = [asdict(item) for item in items]
                self._emit(kwargs=kwargs, decision="ALLOW", success=True, duration_ms=_duration_ms(started), message="OK")
                return str({"success": True, "count": len(rows), "items": rows})

            if action == "delete":
                recursive = bool(kwargs.get("recursive", False))
                result = self._fs.delete_path(path=path, recursive=recursive, context=context)
                self._emit(kwargs=kwargs, decision="ALLOW", success=True, duration_ms=_duration_ms(started), message="OK")
                return str(asdict(result))

            self._emit(kwargs=kwargs, decision="ALLOW", success=False, duration_ms=_duration_ms(started), message="action invÃ¡lida")
            return "[TOOL_ERROR] action invÃ¡lida para v2_file_ops"

        except PermissionError as e:
            self._emit(kwargs=kwargs, decision="DENY", success=False, duration_ms=_duration_ms(started), message=str(e))
            return f"[POLICY_BLOCKED] OperaÃ§Ã£o de arquivo bloqueada pela policy sandbox: {e}"
        except Exception as e:
            self._emit(kwargs=kwargs, decision="ALLOW", success=False, duration_ms=_duration_ms(started), message=f"{type(e).__name__}: {e}")
            return f"[TOOL_ERROR] File ops falhou: {type(e).__name__}: {e}"

    def _emit(self, *, kwargs: dict, decision: str, success: bool, duration_ms: int, message: str) -> None:
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


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

