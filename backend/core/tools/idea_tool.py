"""
IdeaTool — inbox de ideias do Matheus (captura sem fricção).

"anota: ideia de vídeo sobre roguelikes" → guarda na hora. "minhas ideias de
vídeo" → lista. Categorize sozinha quando der (video, projeto, compra, geral).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

from ..inbox import ideas_store

logger = get_logger(__name__)


class IdeaTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="anotar_ideia",
                description=(
                    "Inbox de ideias do Matheus. Use acao=anotar SEMPRE que ele jogar uma "
                    "ideia/anotação rápida ('anota: ...', 'ideia de vídeo: ...', 'me lembra que "
                    "quero testar X'). Categorize sozinha (video, projeto, compra, jogo, geral). "
                    "Use acao=listar quando ele pedir as ideias dele (opcionalmente por categoria)."
                ),
                category="productivity",
                parameters=[
                    ToolParameter(name="acao", type="string", description="anotar, listar, arquivar",
                                  required=True, choices=["anotar", "listar", "arquivar"]),
                    ToolParameter(name="texto", type="string", description="A ideia (para anotar).", required=False),
                    ToolParameter(name="categoria", type="string",
                                  description="Categoria (video, projeto, compra, jogo, geral).", required=False),
                    ToolParameter(name="id", type="int", description="Para arquivar: id da ideia.", required=False),
                ],
                examples=[
                    "acao=anotar, texto=vídeo comparando engines de jogo, categoria=video",
                    "acao=listar, categoria=video",
                    "acao=listar",
                ],
                security_level=SecurityLevel.LOW,
                tags=["ideia", "inbox", "anotacao", "captura"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        acao = str(kwargs.get("acao", "")).strip().lower()
        if acao == "anotar":
            return bool(str(kwargs.get("texto", "")).strip())
        if acao == "arquivar":
            return kwargs.get("id") is not None
        return acao == "listar"

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()

        if acao == "anotar":
            texto = str(kwargs.get("texto", "")).strip()
            cat = str(kwargs.get("categoria", "geral")).strip() or "geral"
            iid = await asyncio.to_thread(ideas_store.anotar, texto, cat)
            return json.dumps({"ok": True, "id": iid, "categoria": cat,
                               "msg": f"Anotado em '{cat}'. Tá guardado."}, ensure_ascii=False)

        if acao == "listar":
            cat = str(kwargs.get("categoria", "")).strip() or None
            ideias = await asyncio.to_thread(ideas_store.listar, cat)
            if not ideias:
                return json.dumps({"ok": True, "ideias": [], "msg": "Sua caixa de ideias está vazia."}, ensure_ascii=False)
            return json.dumps({"ok": True, "ideias": [
                {"id": i["id"], "texto": i["texto"], "categoria": i["categoria"]} for i in ideias
            ]}, ensure_ascii=False)

        if acao == "arquivar":
            ok = await asyncio.to_thread(ideas_store.arquivar, int(kwargs.get("id")))
            return json.dumps({"ok": ok, "msg": "Arquivada." if ok else "Não achei essa ideia."}, ensure_ascii=False)

        raise ValueError(f"Ação desconhecida: {acao}")
