"""
SkillsTool: skills de texto que o Matheus aprovou (B7).

  listar  -> nomes e descrições das skills aprovadas
  ler     -> o corpo de uma skill (instruções que valem para este pedido)
  propor  -> sugere uma skill NOVA ou uma edição de skill que eu criei. Vai para a fila: só passa a
             valer quando o Matheus aprova na tela. Esta ferramenta NUNCA aprova nada.

Quando propor: quando ele pedir "salva isso como skill/rotina" ou depois que ele te corrigir e o
jeito certo de fazer for reutilizável. Sem scripts: só instruções em texto.
"""

from __future__ import annotations

from typing import Any

from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
from ..policy.content_origin import fontes_contaminadas
from ..skills import get_skill_store


class SkillsTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="skills",
                description=(
                    "Skills de texto aprovadas pelo Matheus. acao=listar mostra as que existem; acao=ler "
                    "traz as instruções de uma (use quando o pedido combinar com a descrição); acao=propor "
                    "sugere uma skill nova (nome em minúsculas com hífen, descricao curta, corpo com as "
                    "instruções): ela só vale depois que ele aprovar na tela. Não é para executar código."
                ),
                category="learning",
                parameters=[
                    ToolParameter(name="acao", type="string", description="listar | ler | propor", required=True,
                                  choices=["listar", "ler", "propor"]),
                    ToolParameter(name="nome", type="string", description="Nome da skill (minúsculas e hífen)", required=False),
                    ToolParameter(name="descricao", type="string", description="Uma frase: quando usar", required=False),
                    ToolParameter(name="corpo", type="string", description="Instruções da skill em texto", required=False),
                ],
                examples=["acao='listar'", "acao='ler', nome='resumo-de-reuniao'"],
                security_level=SecurityLevel.LOW,
                tags=["skills", "aprendizado"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return str(kwargs.get("acao") or "").lower() in ("listar", "ler", "propor")

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao") or "").lower()
        loja = get_skill_store()
        if acao == "listar":
            itens = loja.listar()
            if not itens:
                return "Nenhuma skill aprovada ainda."
            return "\n".join(f"- {s['nome']}: {s['descricao']}" for s in itens)
        if acao == "ler":
            corpo = loja.ler(str(kwargs.get("nome") or ""))
            return corpo if corpo else "[ERRO] Skill não encontrada."
        if acao == "propor":
            ok, msg = loja.propor(
                str(kwargs.get("nome") or ""), str(kwargs.get("descricao") or ""), str(kwargs.get("corpo") or ""),
                contaminado=bool(fontes_contaminadas()),
            )
            return msg if ok else f"[ERRO] {msg}"
        return "[ERRO] acao inválida"
