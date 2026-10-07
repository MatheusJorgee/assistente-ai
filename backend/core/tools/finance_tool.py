"""
FinanceTool — o co-piloto financeiro da Quinta-Feira.

Cota ativos em tempo real (cripto via Binance, moedas via AwesomeAPI, sem chave)
e gerencia a WATCHLIST: ativos que ela passa a acompanhar e avisar sozinha
quando o preço se mexe além do limite (entrega pelo ProactiveMonitor).
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

from ..finance import cotar, formatar, conhece, watchlist_store

logger = get_logger(__name__)


class FinanceTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="financas",
                description=(
                    "Cotações em tempo real e watchlist de investimentos. Use para: "
                    "consultar preço de cripto (bitcoin, ethereum, solana...) ou moeda "
                    "(dólar, euro); adicionar um ativo à watchlist pra ela ACOMPANHAR e "
                    "avisar sozinha quando mexer; listar ou remover da watchlist. "
                    "Quando comentar um ativo, considere também mostrar o gráfico com "
                    "`mostrar_no_visor` (tipo='grafico')."
                ),
                category="finance",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="cotar, acompanhar, parar_de_acompanhar, listar",
                        required=True,
                        choices=["cotar", "acompanhar", "parar_de_acompanhar", "listar"],
                    ),
                    ToolParameter(
                        name="ativo",
                        type="string",
                        description="Nome do ativo: 'bitcoin', 'ethereum', 'dólar', 'euro', etc.",
                        required=False,
                    ),
                    ToolParameter(
                        name="limite_pct",
                        type="number",
                        description="Para acompanhar: variação % que dispara aviso (padrão 3).",
                        required=False,
                        default=3.0,
                    ),
                ],
                examples=[
                    "acao=cotar, ativo=bitcoin",
                    "acao=acompanhar, ativo=dólar, limite_pct=2",
                    "acao=listar",
                ],
                security_level=SecurityLevel.LOW,
                tags=["financas", "cripto", "dolar", "investimento", "cotacao"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        acao = str(kwargs.get("acao", "")).strip().lower()
        if acao in ("cotar", "acompanhar", "parar_de_acompanhar"):
            return bool(str(kwargs.get("ativo", "")).strip())
        return acao == "listar"

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()
        ativo = str(kwargs.get("ativo", "")).strip()

        if acao == "cotar":
            cot = await cotar(ativo)
            if not cot:
                return json.dumps(
                    {"ok": False, "erro": f"Não conheço o ativo '{ativo}'. Tente cripto (bitcoin, ethereum) ou moeda (dólar, euro)."},
                    ensure_ascii=False,
                )
            return json.dumps({"ok": True, "resumo": formatar(cot), **cot}, ensure_ascii=False)

        if acao == "acompanhar":
            cot = await cotar(ativo)
            if not cot:
                return json.dumps(
                    {"ok": False, "erro": f"Não consegui cotar '{ativo}' — confira o nome."},
                    ensure_ascii=False,
                )
            limite = float(kwargs.get("limite_pct", 3.0) or 3.0)
            ok = await asyncio.to_thread(
                watchlist_store.adicionar, cot["nome"], cot["tipo"], cot["simbolo"], limite
            )
            await asyncio.to_thread(watchlist_store.marcar_preco_avisado, cot["simbolo"], cot["preco"])
            return json.dumps(
                {"ok": ok, "resumo": formatar(cot),
                 "msg": f"Pronto, vou ficar de olho em {cot['nome']} e te aviso se mexer mais que {limite:.0f}%."},
                ensure_ascii=False,
            )

        if acao == "parar_de_acompanhar":
            ok = await asyncio.to_thread(watchlist_store.remover, ativo)
            return json.dumps(
                {"ok": ok, "msg": "Parei de acompanhar." if ok else "Esse não estava na watchlist."},
                ensure_ascii=False,
            )

        if acao == "listar":
            itens = await asyncio.to_thread(watchlist_store.listar)
            if not itens:
                return json.dumps({"ok": True, "watchlist": [], "msg": "A watchlist está vazia."}, ensure_ascii=False)
            # cota cada um pra dar o estado atual
            linhas = []
            for it in itens:
                cot = await cotar(it["simbolo"])
                if cot:
                    cot["nome"] = it["nome"]  # usa o nome amigável guardado, não o símbolo
                    linhas.append(formatar(cot))
                else:
                    linhas.append(f"{it['nome']}: (cotação indisponível)")
            return json.dumps({"ok": True, "watchlist": linhas}, ensure_ascii=False)

        raise ValueError(f"Ação desconhecida: {acao}")
