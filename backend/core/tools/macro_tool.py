"""
MacroTool — cria e roda "modos"/cenas (um comando dispara vários passos).

Criar: o LLM define os passos como chamadas de ferramenta. Ex.:
  acao=criar, nome="edição", passos=[{"ferramenta":"abrir_programa","args":{"nome":"Premiere"}},
                                      {"ferramenta":"controlar_midia","args":{"acao":"pause"}}]
Rodar: executa os passos em ordem via o registry de ferramentas.

O registry é injetado no startup (set_registry).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, List

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

from ..macros import macros_store

logger = get_logger(__name__)


class MacroTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="macro",
                description=(
                    "Cria e executa MACROS/MODOS — uma sequência de ações disparada por um "
                    "comando só (ex: 'modo edição', 'prepara meu setup de live'). "
                    "Para CRIAR (acao=criar): defina os passos como chamadas de ferramenta no "
                    "campo `passos` (lista JSON de {ferramenta, args}); use ferramentas que "
                    "existem (abrir_programa, controlar_midia, etc). "
                    "Para RODAR (acao=rodar): execute uma macro salva pelo nome. "
                    "Quando o Matheus descrever uma rotina ('quando eu for editar, abre X e Y'), "
                    "CRIE a macro. Quando ele pedir 'modo X'/'roda a macro X', RODE."
                ),
                category="automation",
                parameters=[
                    ToolParameter(name="acao", type="string", description="criar, rodar, listar, remover",
                                  required=True, choices=["criar", "rodar", "listar", "remover"]),
                    ToolParameter(name="nome", type="string", description="Nome da macro/modo.", required=False),
                    ToolParameter(name="passos", type="string",
                                  description="Para criar: JSON com lista de passos [{\"ferramenta\":\"...\",\"args\":{...}}].",
                                  required=False),
                    ToolParameter(name="descricao", type="string", description="Descrição curta da macro.", required=False),
                ],
                examples=[
                    'acao=criar, nome=edição, passos=[{"ferramenta":"abrir_programa","args":{"nome":"Premiere"}}]',
                    "acao=rodar, nome=edição",
                    "acao=listar",
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["macro", "modo", "automacao", "rotina"],
            )
        )
        self._registry = None

    def set_registry(self, registry: Any) -> None:
        self._registry = registry

    def validate_input(self, **kwargs: Any) -> bool:
        acao = str(kwargs.get("acao", "")).strip().lower()
        if acao == "criar":
            return bool(str(kwargs.get("nome", "")).strip()) and bool(str(kwargs.get("passos", "")).strip())
        if acao in ("rodar", "remover"):
            return bool(str(kwargs.get("nome", "")).strip())
        return acao == "listar"

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()

        if acao == "criar":
            nome = str(kwargs.get("nome", "")).strip()
            try:
                passos = kwargs.get("passos")
                if isinstance(passos, str):
                    passos = json.loads(passos)
                if not isinstance(passos, list) or not passos:
                    return json.dumps({"ok": False, "erro": "passos inválidos (esperado lista JSON)."}, ensure_ascii=False)
            except Exception as exc:
                return json.dumps({"ok": False, "erro": f"passos não são JSON válido: {exc}"}, ensure_ascii=False)
            ok = await asyncio.to_thread(macros_store.salvar, nome, passos, str(kwargs.get("descricao", "")).strip())
            return json.dumps({"ok": ok, "msg": f"Modo '{nome}' criado com {len(passos)} passo(s)."}, ensure_ascii=False)

        if acao == "rodar":
            nome = str(kwargs.get("nome", "")).strip()
            macro = await asyncio.to_thread(macros_store.buscar, nome)
            if not macro:
                return json.dumps({"ok": False, "erro": f"Não tenho um modo chamado '{nome}'."}, ensure_ascii=False)
            if not self._registry:
                return json.dumps({"ok": False, "erro": "Registry não disponível."}, ensure_ascii=False)
            resultados = []
            for passo in macro.get("passos", []):
                ferr = str(passo.get("ferramenta", "")).strip()
                args = passo.get("args", {}) or {}
                if not ferr:
                    continue
                try:
                    r = await self._registry.execute(ferr, **args)
                    out = getattr(r, "output", None) or getattr(r, "error", None) or str(r)
                    resultados.append(f"{ferr}: {str(out)[:60]}")
                except Exception as exc:
                    resultados.append(f"{ferr}: ERRO {str(exc)[:50]}")
            return json.dumps(
                {"ok": True, "modo": macro["nome"], "executados": resultados,
                 "msg": f"Rodei o modo '{macro['nome']}' ({len(resultados)} passo(s))."},
                ensure_ascii=False,
            )

        if acao == "listar":
            return json.dumps({"ok": True, "macros": await asyncio.to_thread(macros_store.listar)}, ensure_ascii=False)

        if acao == "remover":
            ok = await asyncio.to_thread(macros_store.remover, str(kwargs.get("nome", "")).strip())
            return json.dumps({"ok": ok, "msg": "Removido." if ok else "Não achei esse modo."}, ensure_ascii=False)

        raise ValueError(f"Ação desconhecida: {acao}")
