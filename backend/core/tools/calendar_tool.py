"""
CalendarTool — a Google Agenda do Matheus nos olhos dela.

Lê os compromissos via endereço iCal privado (CALENDAR_ICS_URL no .env), sem
OAuth. Para AGENDAR algo novo, ela usa a ferramenta `lembrete` (local) — então
aqui o foco é CONSULTAR a agenda real ("o que tenho hoje?", "tô livre amanhã?").
"""

from __future__ import annotations

import json
from typing import Any

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger, get_config
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger, get_config

from ..calendar import proximos_eventos, eventos_de_hoje, formatar

logger = get_logger(__name__)


class CalendarTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="agenda",
                description=(
                    "Consulta a Google Agenda do Matheus (compromissos reais). Use quando "
                    "ele perguntar o que tem na agenda, se está livre, os compromissos de "
                    "hoje/da semana. Para CRIAR um lembrete novo, use a ferramenta `lembrete` "
                    "em vez desta."
                ),
                category="productivity",
                parameters=[
                    ToolParameter(
                        name="periodo",
                        type="string",
                        description="'hoje' ou 'semana' (próximos 7 dias).",
                        required=False,
                        default="hoje",
                        choices=["hoje", "semana"],
                    ),
                ],
                examples=["periodo=hoje", "periodo=semana"],
                security_level=SecurityLevel.LOW,
                tags=["agenda", "calendario", "compromissos", "google"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        url = getattr(get_config(), "CALENDAR_ICS_URL", "")
        if not url:
            return json.dumps(
                {"ok": False, "configurar": True,
                 "msg": ("A Google Agenda ainda não está conectada. Para ligar: no Google Agenda, "
                         "Configurações → sua agenda → 'Endereço secreto no formato iCal', copie o "
                         "link e coloque em CALENDAR_ICS_URL no .env. Enquanto isso, posso usar "
                         "lembretes locais.")},
                ensure_ascii=False,
            )

        periodo = str(kwargs.get("periodo", "hoje")).strip().lower()
        if periodo == "semana":
            eventos = await proximos_eventos(url, dias=7)
            titulo = "Próximos 7 dias"
        else:
            eventos = await eventos_de_hoje(url)
            titulo = "Hoje"

        if not eventos:
            return json.dumps(
                {"ok": True, "periodo": titulo, "eventos": [], "msg": f"{titulo}: nenhum compromisso na agenda."},
                ensure_ascii=False,
            )
        return json.dumps(
            {"ok": True, "periodo": titulo, "eventos": [formatar(e) for e in eventos]},
            ensure_ascii=False,
        )
