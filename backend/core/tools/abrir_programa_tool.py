"""
AbrirProgramaTool — abre um programa/jogo/aplicativo instalado pelo NOME.

Estratégia (Windows): procura atalhos (.lnk/.url) no Menu Iniciar (todos os
usuários + usuário atual) e na Área de Trabalho, faz match difuso pelo nome e
lança o melhor resultado com os.startfile. Funciona para apps comuns e jogos
(Steam/Epic criam atalhos no Menu Iniciar), sem precisar do caminho do .exe.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

# Apps de sistema/UWP que não têm atalho .lnk — lançados por comando/URI.
_APPS_CONHECIDOS = {
    "calculadora": "calc", "calculator": "calc", "calc": "calc",
    "bloco de notas": "notepad", "notepad": "notepad",
    "paint": "mspaint", "mspaint": "mspaint",
    "explorador de arquivos": "explorer", "explorador": "explorer", "explorer": "explorer",
    "prompt de comando": "cmd", "cmd": "cmd", "terminal": "wt",
    "configuracoes": "ms-settings:", "configurações": "ms-settings:",
    "loja": "ms-windows-store:", "microsoft store": "ms-windows-store:",
    "camera": "microsoft.windows.camera:", "câmera": "microsoft.windows.camera:",
}

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)


def _search_dirs() -> List[Path]:
    dirs = []
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    appdata = os.environ.get("APPDATA", "")
    userprofile = os.environ.get("USERPROFILE", "")
    public = os.environ.get("PUBLIC", r"C:\Users\Public")

    dirs.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if appdata:
        dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if userprofile:
        dirs.append(Path(userprofile) / "Desktop")
    dirs.append(Path(public) / "Desktop")
    return [d for d in dirs if d.exists()]


def _tokens(s: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def _find_shortcuts(nome: str) -> List[Tuple[int, Path]]:
    """Retorna [(score, caminho)] de atalhos que casam com o nome, melhor primeiro."""
    alvo = _tokens(nome)
    if not alvo:
        return []

    candidatos: List[Tuple[int, Path]] = []
    for base in _search_dirs():
        for path in base.rglob("*"):
            if path.suffix.lower() not in (".lnk", ".url", ".exe"):
                continue
            nome_arq = _tokens(path.stem)
            if not nome_arq:
                continue

            # Score: quantos tokens do alvo aparecem no nome do arquivo
            hits = sum(1 for t in alvo if any(t == n or t in n for n in nome_arq))
            if hits == 0:
                continue
            score = hits * 10
            if alvo == nome_arq:
                score += 100  # match exato
            elif all(t in nome_arq for t in alvo):
                score += 50   # todos os tokens presentes
            score -= abs(len(nome_arq) - len(alvo))  # penaliza nomes muito diferentes
            candidatos.append((score, path))

    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos


_CHARS_DE_SHELL = re.compile(r'["&|<>^%`;\r\n]')


def _nome_seguro(nome: str) -> bool:
    """Nome de programa legítimo não tem aspas, &, |, <, >, ^, %, ; nem quebra de linha."""
    return bool(nome) and not _CHARS_DE_SHELL.search(nome)


def _abrir_sync(nome: str) -> str:
    # 1. Atalhos do Menu Iniciar / Desktop (cobre jogos Steam/Epic e apps instalados)
    candidatos = _find_shortcuts(nome)
    if candidatos:
        score, melhor = candidatos[0]
        try:
            os.startfile(str(melhor))  # type: ignore[attr-defined]
            alternativas = [p.stem for s, p in candidatos[1:4] if s >= score - 10]
            extra = f" (alternativas: {', '.join(alternativas)})" if alternativas else ""
            logger.info(f"[ABRIR] Abrindo '{melhor.stem}' (score={score}) para nome={nome!r}")
            return f"Abrindo {melhor.stem}.{extra}"
        except Exception as exc:
            logger.warning(f"[ABRIR] Falha ao abrir atalho {melhor}: {exc}")

    # 2. Apps de sistema/UWP conhecidos (calculadora, paint, configurações...)
    chave = nome.lower().strip()
    comando = _APPS_CONHECIDOS.get(chave)
    if comando:
        try:
            os.startfile(comando)  # type: ignore[attr-defined]
            logger.info(f"[ABRIR] App de sistema '{nome}' -> {comando}")
            return f"Abrindo {nome}."
        except Exception as exc:
            logger.warning(f"[ABRIR] Falha em app de sistema {comando}: {exc}")

    # 3. Fallback: ShellExecute direto (resolve PATH e execution aliases), SEM cmd.exe.
    # O nome vem do LLM: com `start "" "{nome}"` + shell=True, aspas/&/| virariam comandos.
    if _nome_seguro(nome):
        try:
            os.startfile(nome)  # type: ignore[attr-defined]
            logger.info(f"[ABRIR] Tentando via ShellExecute: {nome!r}")
            return f"Tentando abrir {nome}."
        except Exception:
            pass
    else:
        logger.warning(f"[ABRIR] Nome recusado por conter caracteres de shell: {nome!r}")

    return (
        f"Não encontrei nenhum programa instalado com o nome '{nome}'. "
        "Verifique se está instalado ou tente o nome exato do atalho."
    )


class AbrirProgramaTool(MotorTool):
    """Abre um programa, jogo ou aplicativo instalado pelo nome."""

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="abrir_programa",
                description=(
                    "Abre/inicia um PROGRAMA, JOGO ou APLICATIVO já instalado no computador, "
                    "pelo nome (ex: 'Dead by Daylight', 'Spotify', 'Discord', 'Steam', 'calculadora'). "
                    "Use SEMPRE que o usuário pedir para abrir/iniciar/rodar um app ou jogo. "
                    "Funciona para jogos de Steam/Epic. NÃO use para sites (use o navegador)."
                ),
                category="os",
                parameters=[
                    ToolParameter(
                        name="nome",
                        type="string",
                        description="Nome do programa/jogo a abrir (ex: 'Dead by Daylight').",
                        required=True,
                    ),
                ],
                examples=[
                    "nome='Dead by Daylight'",
                    "nome='Spotify'",
                    "nome='calculadora'",
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["os", "launch", "app", "game"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        nome = kwargs.get("nome") or kwargs.get("programa") or kwargs.get("nome_programa")
        return isinstance(nome, str) and bool(nome.strip())

    async def execute(self, **kwargs) -> str:
        nome = str(kwargs.get("nome") or kwargs.get("programa") or kwargs.get("nome_programa") or "").strip()
        if not nome:
            return "[ERRO] Nome do programa não fornecido."
        return await asyncio.to_thread(_abrir_sync, nome)
