"""
FileSystem Adapter: operações de arquivos com sandbox por policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


from .undo import UndoManager, get_undo


@dataclass(frozen=True)
class FileReadResult:
    path: str
    content: str
    size_bytes: int


@dataclass(frozen=True)
class FileWriteResult:
    path: str
    bytes_written: int
    created: bool


@dataclass(frozen=True)
class FileDeleteResult:
    path: str
    deleted: bool
    was_directory: bool


@dataclass(frozen=True)
class DirectoryEntry:
    name: str
    path: str
    is_dir: bool
    size_bytes: int


class FileSystemAdapter:
    """Porta de filesystem com validação de policy por path."""

    def __init__(self, policy_engine: PolicyEngine, undo: Optional[UndoManager] = None) -> None:
        self._policy_engine = policy_engine
        self._undo = undo if undo is not None else get_undo()

    @property
    def undo(self) -> UndoManager:
        return self._undo

    def read_file(self, path: str, *, context: Optional[PolicyContext] = None) -> FileReadResult:
        resolved = self._resolve(path)
        self._policy_engine.assert_allowed(OSAction.FILE_READ, path=str(resolved), context=context)

        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Arquivo não encontrado: {resolved}")

        content = resolved.read_text(encoding="utf-8")
        return FileReadResult(path=str(resolved), content=content, size_bytes=len(content.encode("utf-8")))

    def write_file(
        self,
        path: str,
        content: str,
        *,
        overwrite: bool = True,
        context: Optional[PolicyContext] = None,
    ) -> FileWriteResult:
        resolved = self._resolve(path)
        self._policy_engine.assert_allowed(OSAction.FILE_WRITE, path=str(resolved), context=context)

        existed = resolved.exists()
        if existed and not overwrite:
            raise FileExistsError(f"Arquivo já existe e overwrite=False: {resolved}")

        recibo = self._undo.antes_de_escrever(resolved)  # None = grande demais: não dá para desfazer
        resolved.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        resolved.write_bytes(data)
        self._undo.depois_de_escrever(recibo)
        return FileWriteResult(path=str(resolved), bytes_written=len(data), created=not existed)

    def list_directory(
        self,
        path: str,
        *,
        limit: int = 100,
        context: Optional[PolicyContext] = None,
    ) -> list[DirectoryEntry]:
        resolved = self._resolve(path)
        self._policy_engine.assert_allowed(OSAction.FILE_LIST, path=str(resolved), context=context)

        if not resolved.exists() or not resolved.is_dir():
            raise NotADirectoryError(f"Diretório inválido: {resolved}")

        entries: list[DirectoryEntry] = []
        for item in sorted(resolved.iterdir(), key=lambda p: p.name.lower())[: max(1, min(limit, 500))]:
            size = 0
            if item.is_file():
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
            entries.append(
                DirectoryEntry(
                    name=item.name,
                    path=str(item),
                    is_dir=item.is_dir(),
                    size_bytes=size,
                )
            )
        return entries

    def delete_path(
        self,
        path: str,
        *,
        recursive: bool = False,
        context: Optional[PolicyContext] = None,
    ) -> FileDeleteResult:
        resolved = self._resolve(path)
        self._policy_engine.assert_allowed(OSAction.FILE_DELETE, path=str(resolved), context=context)

        if not resolved.exists():
            return FileDeleteResult(path=str(resolved), deleted=False, was_directory=False)

        # Apagar = mover para a quarentena (B1): dá para restaurar; o expurgo apaga de verdade.
        if resolved.is_file():
            self._undo.apagar_para_quarentena(resolved)
            return FileDeleteResult(path=str(resolved), deleted=True, was_directory=False)

        if resolved.is_dir():
            if not recursive and any(resolved.iterdir()):
                raise OSError(f"Diretório não vazio (use recursive): {resolved}")
            self._undo.apagar_para_quarentena(resolved)
            return FileDeleteResult(path=str(resolved), deleted=True, was_directory=True)

        return FileDeleteResult(path=str(resolved), deleted=False, was_directory=False)

    @staticmethod
    def _resolve(path: str) -> Path:
        return Path(path).expanduser().resolve()

