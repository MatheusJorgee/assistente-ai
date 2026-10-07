"""
ScheduleTool — agenda AÇÕES que rodam sozinhas (não só lembretes que falam).

O usuário diz "todo dia às 18h me dá o resumo do mercado" → no horário, o comando
passa pelo brain e o resultado é narrado. Diferente do `lembrete` (que apenas
avisa um texto), aqui a Quinta-Feira EXECUTA a tarefa.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, List

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

from ..scheduler import scheduled_store

logger = get_logger(__name__)

_DIAS = {"segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
         "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6}


class ScheduleTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="agendar_acao",
                description=(
                    "Agenda uma AÇÃO recorrente que VOCÊ executa sozinha no horário (não é "
                    "lembrete de texto — é tarefa que roda). Ex: 'todo dia 18h me dá o resumo "
                    "do mercado', 'toda sexta 20h me lembra de backup e abre a pasta'. O comando "
                    "agendado será processado por você no horário e o resultado é falado. Para "
                    "um lembrete simples de texto, use `lembrete`; para AÇÃO recorrente, use esta."
                ),
                category="automation",
                parameters=[
                    ToolParameter(name="acao", type="string", description="criar, listar, cancelar",
                                  required=True, choices=["criar", "listar", "cancelar"]),
                    ToolParameter(name="comando", type="string",
                                  description="O que fazer no horário, em linguagem natural (ex: 'me dá o resumo do mercado').",
                                  required=False),
                    ToolParameter(name="hora", type="string", description="Horário HH:MM (24h).", required=False),
                    ToolParameter(name="dias", type="string",
                                  description="Dias da semana separados por vírgula (ex: 'segunda,sexta'); vazio = todo dia.",
                                  required=False),
                    ToolParameter(name="id", type="int", description="Para cancelar: id da tarefa.", required=False),
                ],
                examples=[
                    "acao=criar, comando=me dá o resumo do mercado, hora=18:00",
                    "acao=criar, comando=lembra de fazer backup, hora=20:00, dias=sexta",
                    "acao=listar",
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["agendar", "rotina", "automacao", "cron"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        acao = str(kwargs.get("acao", "")).strip().lower()
        if acao == "criar":
            return bool(str(kwargs.get("comando", "")).strip()) and bool(str(kwargs.get("hora", "")).strip())
        if acao == "cancelar":
            return kwargs.get("id") is not None
        return acao == "listar"

    @staticmethod
    def _parse_dias(s: str) -> List[int]:
        out = []
        for parte in re.split(r"[,;]", (s or "").lower()):
            p = parte.strip()
            if p in _DIAS:
                out.append(_DIAS[p])
        return out

    @staticmethod
    def _norm_hora(s: str) -> str:
        s = (s or "").strip().replace("h", ":").rstrip(":")
        m = re.match(r"^(\d{1,2})(?::(\d{2}))?$", s)
        if m:
            return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"
        return s

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()

        if acao == "criar":
            comando = str(kwargs.get("comando", "")).strip()
            hora = self._norm_hora(str(kwargs.get("hora", "")))
            if not re.match(r"^\d{2}:\d{2}$", hora):
                return json.dumps({"ok": False, "erro": "Horário inválido (use HH:MM)."}, ensure_ascii=False)
            dias = self._parse_dias(str(kwargs.get("dias", "")))
            tid = await asyncio.to_thread(scheduled_store.criar, comando, hora, dias)
            quando = "todo dia" if not dias else "em dias específicos"
            return json.dumps(
                {"ok": True, "id": tid, "msg": f"Agendado: '{comando}' às {hora}, {quando}."},
                ensure_ascii=False,
            )

        if acao == "listar":
            ts = await asyncio.to_thread(scheduled_store.listar)
            return json.dumps({"ok": True, "tarefas": [
                {"id": t["id"], "comando": t["comando"], "hora": t["hora"], "dias": t.get("dias", [])} for t in ts
            ]}, ensure_ascii=False)

        if acao == "cancelar":
            ok = await asyncio.to_thread(scheduled_store.cancelar, int(kwargs.get("id")))
            return json.dumps({"ok": ok, "msg": "Cancelado." if ok else "Não achei essa tarefa."}, ensure_ascii=False)

        raise ValueError(f"Ação desconhecida: {acao}")
