"""
PeopleTool — a Quinta-Feira como secretária que conhece a turma do Matheus.

Registra e consulta as pessoas da vida dele. Use ESPONTANEAMENTE: quando ele
contar algo sobre alguém ("a Yngrid é minha namorada", "o Pradu é alérgico a
camarão"), grave sem pedir permissão. Quando ele perguntar de alguém, consulte.
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

from ..people import people_store

logger = get_logger(__name__)


class PeopleTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="pessoas",
                description=(
                    "Memória das pessoas da vida do Matheus (CRM pessoal): quem são, "
                    "apelidos, relação, fatos importantes, aniversário, último contato. "
                    "REGISTRE espontaneamente (acao=salvar) sempre que ele revelar algo "
                    "sobre alguém — namorada, amigo, família, colega, uma alergia, um gosto. "
                    "CONSULTE (acao=consultar) quando ele mencionar/perguntar de alguém. "
                    "acao=listar mostra todo mundo; acao=esquecidos mostra quem ele não "
                    "fala há tempo."
                ),
                category="memory",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="salvar, consultar, listar, esquecidos",
                        required=True,
                        choices=["salvar", "consultar", "listar", "esquecidos"],
                    ),
                    ToolParameter(name="nome", type="string", description="Nome da pessoa.", required=False),
                    ToolParameter(name="relacao", type="string", description="Relação (namorada, amigo, mãe, colega...).", required=False),
                    ToolParameter(name="apelidos", type="string", description="Apelidos separados por vírgula.", required=False),
                    ToolParameter(name="fatos", type="string", description="Fato(s) sobre a pessoa, separados por '; '.", required=False),
                    ToolParameter(name="aniversario", type="string", description="Aniversário em MM-DD ou DD/MM.", required=False),
                ],
                examples=[
                    "acao=salvar, nome=Yngrid, relacao=namorada, aniversario=09/09",
                    "acao=salvar, nome=Pradu, fatos=alérgico a camarão",
                    "acao=consultar, nome=Yngrid",
                    "acao=esquecidos",
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["pessoas", "crm", "relacionamento", "contatos"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        acao = str(kwargs.get("acao", "")).strip().lower()
        if acao in ("salvar", "consultar"):
            return bool(str(kwargs.get("nome", "")).strip())
        return acao in ("listar", "esquecidos")

    @staticmethod
    def _norm_mmdd(s: str) -> str:
        s = (s or "").strip()
        if "/" in s:
            p = s.split("/")
            return f"{int(p[1]):02d}-{int(p[0]):02d}" if len(p) >= 2 else s
        return s

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()

        if acao == "salvar":
            nome = str(kwargs.get("nome", "")).strip()
            apel = [a.strip() for a in str(kwargs.get("apelidos", "")).split(",") if a.strip()]
            fatos = [f.strip() for f in str(kwargs.get("fatos", "")).replace(",", ";").split(";") if f.strip()]
            aniv = self._norm_mmdd(str(kwargs.get("aniversario", ""))) or None
            r = await asyncio.to_thread(
                people_store.salvar, nome, str(kwargs.get("relacao", "")).strip() or None, apel, fatos, aniv
            )
            return json.dumps({**r, "msg": f"Anotei sobre {nome}."}, ensure_ascii=False)

        if acao == "consultar":
            p = await asyncio.to_thread(people_store.buscar, str(kwargs.get("nome", "")).strip())
            if not p:
                return json.dumps({"ok": True, "encontrado": False, "msg": "Não tenho nada sobre essa pessoa ainda."}, ensure_ascii=False)
            import time as _t
            dias = int((_t.time() - p["ultimo_contato_ts"]) / 86400) if p.get("ultimo_contato_ts") else None
            return json.dumps({
                "ok": True, "encontrado": True, "nome": p["nome"], "relacao": p.get("relacao"),
                "apelidos": p.get("apelidos"), "fatos": p.get("fatos"), "aniversario": p.get("aniversario"),
                "dias_sem_contato": dias,
            }, ensure_ascii=False)

        if acao == "listar":
            pessoas = await asyncio.to_thread(people_store.listar)
            return json.dumps({"ok": True, "pessoas": [
                {"nome": p["nome"], "relacao": p.get("relacao"), "fatos": p.get("fatos")} for p in pessoas
            ]}, ensure_ascii=False)

        if acao == "esquecidos":
            esq = await asyncio.to_thread(people_store.sem_contato_ha, 14)
            import time as _t
            return json.dumps({"ok": True, "esquecidos": [
                {"nome": p["nome"], "relacao": p.get("relacao"),
                 "dias": int((_t.time() - p["ultimo_contato_ts"]) / 86400)} for p in esq
            ]}, ensure_ascii=False)

        raise ValueError(f"Ação desconhecida: {acao}")
