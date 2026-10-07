"""
FileSearchTool — "acha aquele arquivo pra mim".

Busca por nome/extensão nas pastas do usuário (Desktop, Documentos, Downloads,
Vídeos, Imagens, Música) — escopo seguro, não vasculha o sistema inteiro.
Ranqueia por recência (o mais provável é o que ele mexeu por último).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

logger = get_logger(__name__)

# Extensões por categoria pra buscas tipo "aquele vídeo", "aquele projeto"
_CATEGORIAS = {
    "video": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".prproj", ".veg"},
    "imagem": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".psd", ".bmp"},
    "documento": {".pdf", ".docx", ".doc", ".txt", ".md", ".odt"},
    "planilha": {".xlsx", ".xls", ".csv"},
    "audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
    "codigo": {".py", ".js", ".ts", ".tsx", ".java", ".cpp", ".c", ".html", ".css"},
    "projeto": {".prproj", ".veg", ".aep", ".blend", ".psd"},
}

_IGNORAR_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "AppData", ".cache"}


def _pastas_base() -> List[Path]:
    home = Path.home()
    nomes = ["Desktop", "Área de Trabalho", "Documents", "Documentos", "Downloads",
             "Videos", "Vídeos", "Pictures", "Imagens", "Music", "Músicas"]
    out = []
    for n in nomes:
        p = home / n
        if p.exists() and p.is_dir():
            out.append(p)
    return out or [home]


def _buscar_sync(termo: str, categoria: str, limite: int, max_varredura: int = 60000) -> List[Dict[str, Any]]:
    termo_low = termo.strip().lower()
    exts = _CATEGORIAS.get(categoria.lower()) if categoria else None
    resultados: List[Dict[str, Any]] = []
    vistos = 0

    for base in _pastas_base():
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _IGNORAR_DIRS and not d.startswith(".")]
            for nome in files:
                vistos += 1
                if vistos > max_varredura:
                    break
                nl = nome.lower()
                ext = os.path.splitext(nl)[1]
                if exts and ext not in exts:
                    continue
                if termo_low and termo_low not in nl:
                    continue
                if not termo_low and not exts:
                    continue
                caminho = os.path.join(root, nome)
                try:
                    st = os.stat(caminho)
                    resultados.append({
                        "nome": nome,
                        "caminho": caminho,
                        "modificado": st.st_mtime,
                        "tamanho_mb": round(st.st_size / (1024 * 1024), 2),
                    })
                except OSError:
                    continue
            if vistos > max_varredura:
                break

    resultados.sort(key=lambda r: r["modificado"], reverse=True)
    for r in resultados[:limite]:
        r["modificado_em"] = time.strftime("%d/%m/%Y %H:%M", time.localtime(r.pop("modificado")))
    return resultados[:limite]


class FileSearchTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="buscar_arquivo",
                description=(
                    "Acha arquivos nas pastas do usuário (Desktop, Documentos, Downloads, "
                    "Vídeos, Imagens, Música) por parte do nome e/ou categoria. Use quando "
                    "ele pedir pra encontrar/achar/localizar um arquivo, projeto, vídeo, "
                    "documento ('acha aquele projeto de vídeo', 'cadê meu currículo'). "
                    "Retorna os mais recentes primeiro com o caminho completo."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="termo",
                        type="string",
                        description="Parte do nome do arquivo a procurar (ex: 'currículo', 'aniversário').",
                        required=False,
                    ),
                    ToolParameter(
                        name="categoria",
                        type="string",
                        description="Opcional: video, imagem, documento, planilha, audio, codigo, projeto.",
                        required=False,
                        choices=["video", "imagem", "documento", "planilha", "audio", "codigo", "projeto"],
                    ),
                    ToolParameter(
                        name="limite",
                        type="int",
                        description="Máximo de resultados (padrão 8).",
                        required=False,
                        default=8,
                    ),
                ],
                examples=[
                    "termo=currículo",
                    "termo=aniversário, categoria=video",
                    "categoria=projeto",
                ],
                security_level=SecurityLevel.LOW,
                tags=["arquivo", "busca", "filesystem", "encontrar"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return bool(str(kwargs.get("termo", "")).strip()) or bool(str(kwargs.get("categoria", "")).strip())

    async def execute(self, **kwargs: Any) -> str:
        import json
        termo = str(kwargs.get("termo", "")).strip()
        categoria = str(kwargs.get("categoria", "")).strip()
        limite = int(kwargs.get("limite", 8) or 8)

        resultados = await asyncio.to_thread(_buscar_sync, termo, categoria, limite)
        if not resultados:
            alvo = termo or categoria
            return json.dumps(
                {"ok": True, "resultados": [], "msg": f"Não achei nada parecido com '{alvo}' nas suas pastas."},
                ensure_ascii=False,
            )
        return json.dumps({"ok": True, "resultados": resultados}, ensure_ascii=False)
