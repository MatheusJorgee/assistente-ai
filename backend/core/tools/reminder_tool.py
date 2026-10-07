"""
ReminderTool — a agenda viva da Quinta-Feira.

Cria/lista/cancela lembretes pontuais ("amanhã às 15h") e datas anuais
(aniversários). A entrega é proativa: o monitor fala o lembrete na hora,
sem ninguém pedir.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

from ..proactive import reminders_store

logger = get_logger(__name__)


def _parse_data_hora(s: str) -> float:
    """ISO 'YYYY-MM-DD HH:MM' (ou só data → 09:00). Levanta ValueError se inválida."""
    s = (s or "").strip().replace("T", " ")
    if len(s) == 10:  # só data
        s += " 09:00"
    dt = datetime.fromisoformat(s)
    return dt.timestamp()


def _parse_mmdd(s: str) -> str:
    """Aceita 'MM-DD', 'DD/MM' ou data completa; retorna 'MM-DD'."""
    s = (s or "").strip()
    if "/" in s:  # DD/MM brasileiro
        partes = s.split("/")
        return f"{int(partes[1]):02d}-{int(partes[0]):02d}"
    if len(s) == 5 and "-" in s:  # MM-DD
        mm, dd = s.split("-")
        return f"{int(mm):02d}-{int(dd):02d}"
    dt = datetime.fromisoformat(s.replace("T", " ")[:10])
    return dt.strftime("%m-%d")


class ReminderTool(MotorTool):
    """Lembretes pontuais e datas anuais (aniversários) com entrega proativa."""

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="lembrete",
                description=(
                    "Cria, lista e cancela LEMBRETES que serão avisados em voz alta na "
                    "hora certa. Use quando o usuário pedir para ser lembrado de algo "
                    "('me lembra de X amanhã às 15h') E TAMBÉM espontaneamente quando uma "
                    "data importante aparecer na conversa (aniversário de alguém, "
                    "consulta, prazo) — nesse caso crie sem pedir permissão e mencione "
                    "que anotou. Para aniversários e datas que se repetem todo ano, use "
                    "anual=true com a data em data_anual. Converta expressões relativas "
                    "('amanhã', 'daqui 2 horas') usando a data/hora do CONTEXTO DO AGORA."
                ),
                category="productivity",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="criar, listar ou cancelar",
                        required=True,
                        choices=["criar", "listar", "cancelar"],
                    ),
                    ToolParameter(
                        name="texto",
                        type="string",
                        description="O que lembrar (ex: 'renovar o boleto da internet', 'aniversário da Yngrid').",
                        required=False,
                    ),
                    ToolParameter(
                        name="em_minutos",
                        type="int",
                        description=(
                            "PREFERIDO para tempo relativo: daqui a quantos minutos avisar "
                            "('daqui 2 minutos'→2, 'em meia hora'→30, 'daqui 2 horas'→120). "
                            "O servidor calcula o horário exato — NÃO calcule você."
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="data_hora",
                        type="string",
                        description="Para horário ABSOLUTO: 'YYYY-MM-DD HH:MM' (24h). Só data = 09:00.",
                        required=False,
                    ),
                    ToolParameter(
                        name="anual",
                        type="bool",
                        description="true para data que repete todo ano (aniversário).",
                        required=False,
                        default=False,
                    ),
                    ToolParameter(
                        name="data_anual",
                        type="string",
                        description="Para anual=true: a data no formato 'MM-DD' ou 'DD/MM' (ex: aniversário 09/09 → '09-09' ou '09/09').",
                        required=False,
                    ),
                    ToolParameter(
                        name="id",
                        type="int",
                        description="Para cancelar: o id do lembrete (veja em listar).",
                        required=False,
                    ),
                ],
                examples=[
                    "acao=criar, texto=pagar o boleto, data_hora=2026-06-13 15:00",
                    "acao=criar, texto=aniversário da Yngrid, anual=true, data_anual=09/09",
                    "acao=listar",
                    "acao=cancelar, id=3",
                ],
                security_level=SecurityLevel.LOW,
                tags=["lembrete", "agenda", "aniversario", "reminder"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        acao = str(kwargs.get("acao", "")).strip().lower()
        if acao == "criar":
            return bool(str(kwargs.get("texto", "")).strip())
        if acao == "cancelar":
            return kwargs.get("id") is not None
        return acao == "listar"

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()

        if acao == "criar":
            texto = str(kwargs.get("texto", "")).strip()
            anual = bool(kwargs.get("anual", False))
            try:
                if anual:
                    fonte = str(kwargs.get("data_anual") or kwargs.get("data_hora") or "")
                    mmdd = _parse_mmdd(fonte)
                    rid = await asyncio.to_thread(
                        reminders_store.criar, texto, None, mmdd, "chat"
                    )
                    return json.dumps(
                        {"ok": True, "id": rid, "tipo": "anual", "data": mmdd,
                         "msg": f"Anotado: '{texto}' todo ano em {mmdd[3:]}/{mmdd[:2]}."},
                        ensure_ascii=False,
                    )
                em_minutos = kwargs.get("em_minutos")
                if em_minutos is not None and int(em_minutos) > 0:
                    # Tempo relativo: o servidor faz a conta (LLM erra aritmética de relógio)
                    import time as _time
                    due = _time.time() + int(em_minutos) * 60
                else:
                    data_hora = str(kwargs.get("data_hora", "")).strip()
                    if not data_hora:
                        return json.dumps(
                            {"ok": False, "erro": "Informe em_minutos (relativo) ou data_hora (YYYY-MM-DD HH:MM), ou anual=true com data_anual."},
                            ensure_ascii=False,
                        )
                    due = _parse_data_hora(data_hora)
                rid = await asyncio.to_thread(reminders_store.criar, texto, due, None, "chat")
                quando = datetime.fromtimestamp(due).strftime("%d/%m às %H:%M")
                return json.dumps(
                    {"ok": True, "id": rid, "tipo": "pontual", "quando": quando,
                     "msg": f"Anotado: vou te lembrar de '{texto}' em {quando}."},
                    ensure_ascii=False,
                )
            except ValueError as exc:
                return json.dumps({"ok": False, "erro": f"Data inválida: {exc}"}, ensure_ascii=False)

        if acao == "listar":
            itens = await asyncio.to_thread(reminders_store.listar_pendentes)
            for it in itens:
                if it.get("due_ts"):
                    it["quando"] = datetime.fromtimestamp(it["due_ts"]).strftime("%d/%m/%Y %H:%M")
                it.pop("due_ts", None)
            return json.dumps({"ok": True, "lembretes": itens}, ensure_ascii=False)

        if acao == "cancelar":
            ok = await asyncio.to_thread(reminders_store.cancelar, int(kwargs.get("id")))
            return json.dumps(
                {"ok": ok, "msg": "Cancelado." if ok else "Não achei esse lembrete."},
                ensure_ascii=False,
            )

        raise ValueError(f"Ação desconhecida: {acao}")
