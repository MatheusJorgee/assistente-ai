"""
ClipboardTool — injeta conteúdo no clipboard do host sem arquivos temporários.

Backend padrão: PyperclipBackend (multiplataforma).
Swap via inject_backend() para testes ou plataformas específicas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Adapter de clipboard — swappable via inject_backend()
# ---------------------------------------------------------------------------

class ClipboardBackend(ABC):
    @abstractmethod
    def write(self, text: str) -> None: ...

    @abstractmethod
    def read(self) -> str: ...


class PyperclipBackend(ClipboardBackend):
    """Multiplataforma: win32/macOS/Linux via pyperclip."""

    def write(self, text: str) -> None:
        import pyperclip
        pyperclip.copy(text)

    def read(self) -> str:
        import pyperclip
        return pyperclip.paste()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class ClipboardTool(MotorTool):
    """Injeta texto no clipboard do host para colar em qualquer aplicativo."""

    def __init__(self) -> None:
        self._backend: ClipboardBackend = PyperclipBackend()
        super().__init__(
            metadata=ToolMetadata(
                name="clipboard_inject",
                description=(
                    "Injeta texto no clipboard do host. "
                    "Use para preparar respostas longas, código ou rascunhos "
                    "antes de o usuário colar em qualquer aplicativo."
                ),
                category="system",
                parameters=[
                    ToolParameter(
                        name="content",
                        type="string",
                        description="Texto a injetar. Pode ser código, markdown, JSON, etc.",
                        required=True,
                    ),
                    ToolParameter(
                        name="format",
                        type="string",
                        description="Hint de formato para notificação: plain, markdown ou code.",
                        required=False,
                        default="plain",
                        choices=["plain", "markdown", "code"],
                    ),
                ],
                examples=[
                    'content="def hello(): pass", format="code"',
                    'content="Prezado cliente, ...", format="plain"',
                ],
                security_level=SecurityLevel.LOW,
                tags=["clipboard", "host", "zero-trace"],
            )
        )

    def inject_backend(self, backend: ClipboardBackend) -> None:
        """Permite substituir o backend (útil em testes)."""
        self._backend = backend

    def validate_input(self, **kwargs) -> bool:
        content = kwargs.get("content")
        return isinstance(content, str) and bool(content.strip())

    async def execute(self, **kwargs) -> str:
        content: str = str(kwargs["content"])
        fmt: str = str(kwargs.get("format", "plain"))

        self._backend.write(content)

        preview = content[:80] + "…" if len(content) > 80 else content
        logger.info("[CLIPBOARD] %d chars injetados (formato: %s)", len(content), fmt)
        return (
            f"Clipboard atualizado — {len(content)} chars, formato: {fmt}. "
            f"Preview: {preview!r}"
        )
