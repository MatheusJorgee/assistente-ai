"""
PendenciasTool: as coisas que o Matheus deixou em aberto (ver core/learning/pendencias.py).

  listar    -> o que está aberto
  adicionar -> anota uma pendência ("anota como pendência: decidir o plano de saúde")
  resolver  -> ele disse que já resolveu
  dispensar -> ele disse que não importa mais
"""

from __future__ import annotations

from typing import Any

from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
from ..learning.pendencias import get_pendencias


class PendenciasTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="pendencias",
                description=(
                    "Pendências do Matheus (coisas que ele quer fazer/decidir e ficaram em aberto). acao=listar mostra as "
                    "abertas; acao=adicionar anota uma (texto + proximo_passo opcional); acao=resolver ou dispensar fecha "
                    "uma (por id); acao=preparo traz o resumo que ela preparou de madrugada para a pendência (por id). Use quando ele pedir para anotar algo em aberto, disser que resolveu ou que não importa mais."
                ),
                category="learning",
                parameters=[
                    ToolParameter(name="acao", type="string", description="listar | adicionar | resolver | dispensar", required=True,
                                  choices=["listar", "adicionar", "resolver", "dispensar", "preparo"]),
                    ToolParameter(name="texto", type="string", description="adicionar: a pendência em uma frase", required=False),
                    ToolParameter(name="proximo_passo", type="string", description="adicionar: algo útil que você poderia fazer", required=False),
                    ToolParameter(name="id", type="string", description="resolver/dispensar: id da pendência (veja em listar)", required=False),
                ],
                examples=["acao='listar'", "acao='adicionar', texto='decidir a viagem de dezembro'"],
                security_level=SecurityLevel.LOW,
                tags=["pendencias", "aprendizado"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return str(kwargs.get("acao") or "").lower() in ("listar", "adicionar", "resolver", "dispensar", "preparo")

    async def execute(self, **kwargs: Any) -> str:
        loja = get_pendencias()
        acao = str(kwargs.get("acao") or "").lower()
        if acao == "listar":
            abertas = loja.listar("aberta")
            return "\n".join(f"- [{p['id']}] {p['texto']}" + (f" (próximo passo: {p['proximo_passo']})" if p["proximo_passo"] else "") for p in abertas) or "Nenhuma pendência aberta."
        if acao == "adicionar":
            pid = loja.adicionar(str(kwargs.get("texto") or ""), str(kwargs.get("proximo_passo") or ""), origem="usuario")
            return f"Anotado como pendência [{pid}]." if pid else "[ERRO] Não anotei: texto curto demais, já existe algo parecido, ou há pendências demais abertas."
        if acao == "preparo":
            from ..learning.bastidor import ler_preparo
            return ler_preparo(str(kwargs.get("id") or "")) or "[ERRO] Ainda não há resumo preparado para essa pendência."
        ok = loja.decidir(str(kwargs.get("id") or ""), "resolvida" if acao == "resolver" else "dispensada")
        return "Feito." if ok else "[ERRO] Não achei essa pendência aberta (use acao=listar para ver os ids)."
