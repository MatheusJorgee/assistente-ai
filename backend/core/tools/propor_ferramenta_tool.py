"""
ProporFerramentaTool: a Quinta PROPÕE uma ferramenta nova (código + testes) quando percebe que falta uma
capacidade. A proposta vai para a quarentena: nada executa, e só vale depois que o Matheus lê o código,
roda os testes e aprova na tela. Esta ferramenta NUNCA aprova, testa nem carrega nada.
"""

from __future__ import annotations

from typing import Any

from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
from ..policy.content_origin import fontes_contaminadas
from ..plugins import get_plugin_store


class ProporFerramentaTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="propor_ferramenta",
                description=(
                    "Propõe uma FERRAMENTA NOVA em Python quando falta uma capacidade (ex.: você falhou várias vezes "
                    "por não ter como fazer X). acao=propor com nome (minúsculas e _), descricao, codigo e testes. "
                    "O código: importa só módulos simples (json, re, math, datetime, asyncio...) e "
                    "`from core.tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel`; define uma "
                    "classe MotorTool com metadata.name == 'agente_<nome>', validate_input e `async execute` e "
                    "termina com `TOOLS = [MinhaFerramenta()]`. Os testes são funções test_* que usam a variável "
                    "`plugin` e asserts. Sem os, subprocess, eval/exec, open ou escrita em arquivos. "
                    "acao=listar mostra as já aprovadas. NADA vale até o Matheus testar e aprovar."
                ),
                category="learning",
                parameters=[
                    ToolParameter(name="acao", type="string", description="propor | listar", required=True, choices=["propor", "listar"]),
                    ToolParameter(name="nome", type="string", description="nome da ferramenta (minúsculas e _)", required=False),
                    ToolParameter(name="descricao", type="string", description="uma frase: o que faz", required=False),
                    ToolParameter(name="codigo", type="string", description="código Python da ferramenta", required=False),
                    ToolParameter(name="testes", type="string", description="funções test_* que usam `plugin`", required=False),
                ],
                examples=["acao='listar'"],
                security_level=SecurityLevel.LOW,
                tags=["aprendizado", "ferramentas"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return str(kwargs.get("acao") or "").lower() in ("propor", "listar")

    async def execute(self, **kwargs: Any) -> str:
        loja = get_plugin_store()
        if str(kwargs.get("acao") or "").lower() == "listar":
            aprov = loja.aprovadas()
            return "\n".join(f"- agente_{n}" + (" (leitura)" if v.get("leitura") else "") for n, v in aprov.items()) or "Nenhuma ferramenta aprovada ainda."
        ok, msg = loja.propor(str(kwargs.get("nome") or ""), str(kwargs.get("descricao") or ""),
                              str(kwargs.get("codigo") or ""), str(kwargs.get("testes") or ""),
                              contaminado=bool(fontes_contaminadas()))
        return msg if ok else f"[ERRO] {msg}"
