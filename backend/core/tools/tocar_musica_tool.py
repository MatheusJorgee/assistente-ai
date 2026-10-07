"""
TocarMusicaTool: `tocar_youtube_invisivel` como ferramenta REGISTRADA.

Antes, o cérebro chamava a automação do YouTube direto (um caso especial dentro do brain), então tocar
música não passava pelo gate de aprovação, pela auditoria nem pelo registro de lacunas: se falhasse,
ninguém ficava sabendo. Agora é uma ferramenta comum do ToolRegistry.

A automação devolve texto simples também nos erros ("Erro ao iniciar YouTube: ..."); aqui isso vira o
padrão `[ERRO ...` que o resto do sistema reconhece.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter


class TocarMusicaTool(MotorTool):
    def __init__(self, obter_automacao: Callable[[], Any]) -> None:
        self._obter_automacao = obter_automacao
        super().__init__(
            metadata=ToolMetadata(
                name="tocar_youtube_invisivel",
                description=(
                    "Toca música/vídeo no YouTube via automação nativa do sistema. "
                    "Use imediatamente quando o usuário pedir para tocar música. "
                    "Parâmetro pesquisa: só 'nome da música artista' (ou 'título do álbum artista full album'). "
                    "Para 'novo/último álbum', descubra o título exato na web ANTES de chamar."
                ),
                category="media",
                parameters=[ToolParameter(name="pesquisa", type="string", description="Nome da música e do artista", required=True)],
                examples=["pesquisa=Numb Linkin Park"],
                security_level=SecurityLevel.LOW,
                tags=["youtube", "media", "music"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return bool(str(kwargs.get("pesquisa", "")).strip())

    async def execute(self, **kwargs: Any) -> str:
        pesquisa = str(kwargs.get("pesquisa", "")).strip()
        from ..media.escolha_video import pedido_vago
        if pedido_vago(pesquisa):
            return ("[BLOQUEADO] Pedido vago ('novo/último ...'): não sei qual é o mais recente. Pesquise na web o título exato "
                    "do álbum/single e chame de novo com 'título artista'.")
        automacao = self._obter_automacao()
        func = getattr(automacao, "tocar_youtube_invisivel", None)
        if func is None:
            return "[ERRO] Método 'tocar_youtube_invisivel' não encontrado em OSAutomation."
        try:
            if inspect.iscoroutinefunction(func):
                saida = await func(pesquisa)
            else:
                import asyncio
                saida = await asyncio.to_thread(func, pesquisa)
        except Exception as exc:
            return f"[ERRO] ao tocar '{pesquisa}': {type(exc).__name__}: {exc}"
        texto = str(saida or "")
        if texto.lower().startswith(("erro", "[erro")) and not texto.startswith("[ERRO"):
            return f"[ERRO] {texto}"
        return texto
