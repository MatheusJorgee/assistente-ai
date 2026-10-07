"""
DraftTool — escreve no ESTILO do Matheus.

Rascunha WhatsApp/e-mail/legenda/descrição imitando o jeito dele de escrever.
Para captar o estilo, amostra as mensagens recentes DELE no banco de chat como
exemplos (few-shot). NÃO envia nada — só entrega o rascunho pra ele aprovar/ajustar.
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, List

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

logger = get_logger(__name__)


class DraftTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="rascunhar",
                description=(
                    "Escreve um rascunho IMITANDO o jeito do Matheus de escrever (WhatsApp, "
                    "e-mail, legenda de vídeo, descrição, post). Use quando ele pedir pra você "
                    "escrever/redigir algo que ELE vai mandar ('escreve um zap pra X dizendo Y', "
                    "'faz a legenda do vídeo', 'redige um email pro cliente'). NÃO envia — só "
                    "entrega o texto pra ele aprovar. Para mandar no WhatsApp, use depois `whatsapp`."
                ),
                category="content",
                parameters=[
                    ToolParameter(name="canal", type="string",
                                  description="whatsapp, email, legenda, descricao, post.", required=True,
                                  choices=["whatsapp", "email", "legenda", "descricao", "post"]),
                    ToolParameter(name="sobre", type="string",
                                  description="O que a mensagem precisa dizer (pontos/intenção).", required=True),
                    ToolParameter(name="destinatario", type="string", description="Para quem (opcional).", required=False),
                    ToolParameter(name="tom", type="string", description="Tom desejado (ex: informal, profissional, animado).", required=False),
                ],
                examples=[
                    "canal=whatsapp, sobre=avisar que vou chegar 20min atrasado, destinatario=Yngrid",
                    "canal=legenda, sobre=vídeo novo de gameplay de Valorant clutch",
                ],
                security_level=SecurityLevel.LOW,
                tags=["rascunho", "escrita", "estilo", "redacao"],
            )
        )
        self._brain = None
        self._chat_db_path = None

    def set_brain(self, brain: Any) -> None:
        self._brain = brain

    def set_chat_db(self, path: str) -> None:
        self._chat_db_path = path

    def validate_input(self, **kwargs: Any) -> bool:
        return bool(str(kwargs.get("canal", "")).strip()) and bool(str(kwargs.get("sobre", "")).strip())

    def _amostrar_estilo(self) -> List[str]:
        """Pega mensagens recentes do Matheus pra servir de exemplo de estilo."""
        if not self._chat_db_path:
            return []
        try:
            conn = sqlite3.connect(self._chat_db_path)
            rows = conn.execute(
                "SELECT content FROM messages WHERE role='user' AND length(content) BETWEEN 8 AND 200 "
                "ORDER BY id DESC LIMIT 25"
            ).fetchall()
            conn.close()
            msgs = []
            for (c,) in rows:
                c = (c or "").strip()
                if c and not c.startswith("[") and "?" != c:
                    msgs.append(c)
            return msgs[:12]
        except Exception as exc:
            logger.debug(f"[DRAFT] amostra de estilo falhou: {exc}")
            return []

    async def execute(self, **kwargs: Any) -> str:
        if not self._brain:
            return "[ERRO] Rascunho indisponível (brain não conectado)."
        canal = str(kwargs.get("canal", "")).strip().lower()
        sobre = str(kwargs.get("sobre", "")).strip()
        dest = str(kwargs.get("destinatario", "")).strip()
        tom = str(kwargs.get("tom", "")).strip()

        exemplos = await asyncio.to_thread(self._amostrar_estilo)
        amostra = ("\n".join(f"- {m}" for m in exemplos)) if exemplos else "(sem amostra; use um tom casual brasileiro natural)"

        try:
            from core.llm_provider import Message
        except ImportError:
            from ..llm_provider import Message

        formato = {
            "whatsapp": "uma mensagem de WhatsApp curta e natural",
            "email": "um e-mail com saudação e fechamento, claro e objetivo",
            "legenda": "uma legenda/caption chamativa pra vídeo (1-3 frases)",
            "descricao": "uma descrição de vídeo (2-4 frases, pode ter chamada pra ação)",
            "post": "um post curto pra rede social",
        }.get(canal, "uma mensagem")

        system = (
            "Você é a Quinta-Feira escrevendo um RASCUNHO que o MATHEUS vai mandar — então escreva "
            f"COMO ELE escreveria, não como você. Abaixo, exemplos reais do jeito dele (gírias, "
            "pontuação, informalidade): IMITE esse estilo.\n\nEXEMPLOS DO ESTILO DELE:\n" + amostra +
            f"\n\nProduza {formato}" + (f" para {dest}" if dest else "") +
            (f", em tom {tom}" if tom else "") +
            ". Entregue SÓ o texto do rascunho, sem aspas, sem explicação, sem 'aqui está'."
        )
        try:
            resp = await self._brain.llm_provider.generate(
                messages=[Message(role="system", content=system),
                          Message(role="user", content=f"A mensagem precisa: {sobre}")],
                tools=None, temperature=0.8, max_tokens=1024,
            )
            texto = (resp.text or "").strip().strip('"')
            if not texto:
                return "Não consegui rascunhar agora — tenta de novo?"
            return f"Rascunho ({canal}) — é só aprovar ou pedir ajuste:\n\n{texto}"
        except Exception as exc:
            logger.warning(f"[DRAFT] falha: {exc}")
            return "Tropecei ao rascunhar. Tenta de novo daqui a pouco?"
