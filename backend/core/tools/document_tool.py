"""
DocumentTool — "lê esse documento pra mim".

Extrai texto de PDF (pypdf), Word (python-docx) e texto puro (txt/md), e resume
no tom dela via LLM. Combina com `buscar_arquivo`: ele acha o arquivo, ela lê.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger

logger = get_logger(__name__)

_MAX_CHARS = 16000  # corta documentos gigantes antes do LLM


def _extrair_sync(caminho: str) -> str:
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(caminho)
        partes = []
        for pag in reader.pages[:60]:
            try:
                partes.append(pag.extract_text() or "")
            except Exception:
                continue
        return "\n".join(partes)
    if ext in (".docx",):
        import docx
        doc = docx.Document(caminho)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if ext in (".txt", ".md", ".csv", ".log", ".json"):
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise ValueError(f"Formato não suportado: {ext} (use PDF, docx, txt ou md)")


class DocumentTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="ler_documento",
                description=(
                    "Lê e resume um documento (PDF, Word/.docx, .txt, .md) a partir do "
                    "CAMINHO completo do arquivo. Use quando ele pedir pra ler/resumir/"
                    "entender um documento, contrato, roteiro, PDF. Se não souber o caminho, "
                    "ache antes com `buscar_arquivo`. Pode responder uma pergunta específica "
                    "sobre o conteúdo se ele fornecer."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(name="caminho", type="string", description="Caminho completo do arquivo.", required=True),
                    ToolParameter(
                        name="pergunta",
                        type="string",
                        description="Opcional: pergunta específica sobre o documento (senão, resume).",
                        required=False,
                    ),
                ],
                examples=[
                    "caminho=C:\\Users\\mathe\\Downloads\\contrato.pdf",
                    "caminho=C:\\Users\\mathe\\Documents\\roteiro.docx, pergunta=qual o gancho de abertura?",
                ],
                security_level=SecurityLevel.LOW,
                tags=["documento", "pdf", "resumo", "leitura"],
            )
        )
        self._brain = None

    def set_brain(self, brain: Any) -> None:
        self._brain = brain

    def validate_input(self, **kwargs: Any) -> bool:
        return bool(str(kwargs.get("caminho", "")).strip())

    async def execute(self, **kwargs: Any) -> str:
        caminho = str(kwargs.get("caminho", "")).strip().strip('"')
        pergunta = str(kwargs.get("pergunta", "")).strip()
        if not os.path.exists(caminho):
            return f"[ERRO] Não achei o arquivo: {caminho}. Use buscar_arquivo pra localizar."

        try:
            texto = await asyncio.to_thread(_extrair_sync, caminho)
        except Exception as exc:
            return f"[ERRO] Não consegui ler: {exc}"

        texto = (texto or "").strip()
        if not texto:
            return "O documento parece vazio ou é só imagem (sem texto extraível)."
        texto = texto[:_MAX_CHARS]
        nome = os.path.basename(caminho)

        if not self._brain:
            # Sem brain: devolve o texto cru pro LLM principal resumir
            return f"CONTEÚDO DE '{nome}':\n{texto}"

        try:
            from core.llm_provider import Message
        except ImportError:
            from ..llm_provider import Message
        if pergunta:
            instr = f"Responda esta pergunta sobre o documento, citando o que importa: \"{pergunta}\""
        else:
            instr = ("Resuma no seu tom, em 3-6 frases: do que se trata, os pontos principais e "
                     "qualquer coisa que peça atenção do Matheus (prazo, valor, cláusula, ação).")
        try:
            resp = await self._brain.llm_provider.generate(
                messages=[
                    Message(role="system", content=(
                        "Você é a Quinta-Feira lendo um documento pro Matheus. " + instr +
                        " Sem markdown pesado, sem enrolação.")),
                    Message(role="user", content=f"DOCUMENTO '{nome}':\n{texto}"),
                ],
                tools=None,
                temperature=0.4,
                max_tokens=2048,
            )
            return (resp.text or "").strip() or f"CONTEÚDO DE '{nome}':\n{texto[:2000]}"
        except Exception as exc:
            logger.warning(f"[DOC] resumo falhou: {exc}")
            return f"CONTEÚDO DE '{nome}':\n{texto[:2000]}"
