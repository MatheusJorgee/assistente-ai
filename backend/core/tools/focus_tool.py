"""
FocusTool — o coach de foco (pomodoro) da Quinta-Feira.

"vamos focar 25 minutos" / "modo foco de 1 hora" → inicia ciclos. Ela protege de
distração durante o foco e avisa as viradas (a entrega das viradas é do monitor).
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

from ..focus import focus_store

logger = get_logger(__name__)


class FocusTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="foco",
                description=(
                    "Coach de foco (pomodoro). Use quando o Matheus quiser focar/trabalhar com "
                    "ciclos cronometrados ('bora focar', 'modo foco 25 minutos', 'sessão de foco'). "
                    "acao=iniciar (com foco_min/pausa_min/ciclos opcionais), parar, status. Durante "
                    "o foco ela segura as distrações e te avisa quando é hora da pausa."
                ),
                category="productivity",
                parameters=[
                    ToolParameter(name="acao", type="string", description="iniciar, parar, status",
                                  required=True, choices=["iniciar", "parar", "status"]),
                    ToolParameter(name="foco_min", type="int", description="Minutos de foco por ciclo (padrão 25).", required=False, default=25),
                    ToolParameter(name="pausa_min", type="int", description="Minutos de pausa (padrão 5).", required=False, default=5),
                    ToolParameter(name="ciclos", type="int", description="Quantos ciclos (padrão 4).", required=False, default=4),
                ],
                examples=["acao=iniciar, foco_min=25", "acao=iniciar, foco_min=50, pausa_min=10, ciclos=3", "acao=status", "acao=parar"],
                security_level=SecurityLevel.LOW,
                tags=["foco", "pomodoro", "produtividade", "concentracao"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return str(kwargs.get("acao", "")).strip().lower() in ("iniciar", "parar", "status")

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()

        if acao == "iniciar":
            foco = int(kwargs.get("foco_min", 25) or 25)
            pausa = int(kwargs.get("pausa_min", 5) or 5)
            ciclos = int(kwargs.get("ciclos", 4) or 4)
            est = await asyncio.to_thread(focus_store.iniciar, foco, pausa, ciclos)
            return json.dumps(
                {"ok": True, "msg": f"Sessão de foco começou: {foco}min focado, {pausa}min de pausa, {ciclos} ciclos. "
                 f"Vou segurar as distrações e te aviso na virada.", "estado": {k: est[k] for k in ('fase','foco_min','pausa_min','ciclos_alvo')}},
                ensure_ascii=False,
            )

        if acao == "parar":
            ok = await asyncio.to_thread(focus_store.parar)
            return json.dumps({"ok": ok, "msg": "Sessão de foco encerrada." if ok else "Não tinha sessão ativa."}, ensure_ascii=False)

        if acao == "status":
            st = await asyncio.to_thread(focus_store.status)
            if not st.get("ativo"):
                return json.dumps({"ok": True, "ativo": False, "msg": "Nenhuma sessão de foco rolando agora."}, ensure_ascii=False)
            return json.dumps({"ok": True, "ativo": True, "fase": st.get("fase"),
                               "restante_min": st.get("restante_min"), "ciclos_feitos": st.get("ciclos_feitos")}, ensure_ascii=False)

        raise ValueError(f"Ação desconhecida: {acao}")
