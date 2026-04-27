"""
Gerenciamento de contexto com compressão assíncrona.

Arquitetura de duas camadas:
- Short-term : deque dos últimos N turnos — enviado intacto ao LLM
- Long-term  : resumo injetado no system prompt, produzido em background

A compressão nunca bloqueia o path de resposta: ela é agendada via
asyncio.create_task() quando o buffer short-term atinge o trigger.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import deque
from typing import Optional

try:
    from .. import get_logger
    from ..llm_provider import LLMProvider, Message
except ImportError:
    from .. import get_logger
    from ..llm_provider import LLMProvider, Message

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Strategy de compressão — swappable sem mudar ConversationMemory
# ---------------------------------------------------------------------------

class CompressionStrategy(ABC):
    @abstractmethod
    async def compress(self, messages: list[Message]) -> str: ...


class LLMCompressionStrategy(CompressionStrategy):
    """
    Usa o LLMProvider existente para comprimir mensagens.
    Custo: 1 chamada extra ao LLM por batch, mas nunca na thread do request.
    """

    _SYSTEM = (
        "Você é um compressor de contexto. "
        "Resuma em até 5 frases densas os FATOS, DECISÕES e PREFERÊNCIAS da conversa abaixo. "
        "Preserve nomes, valores numéricos e contexto técnico. "
        "Produza apenas o resumo, sem explicações ou cabeçalhos."
    )

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def compress(self, messages: list[Message]) -> str:
        body = "\n".join(
            f"{m.role}: {m.content or ''}"
            for m in messages
            if m.content
        )
        if not body.strip():
            return ""

        try:
            response = await self._llm.generate(
                messages=[
                    Message(role="system", content=self._SYSTEM),
                    Message(role="user", content=body),
                ],
                tools=None,
                temperature=0.1,
                max_tokens=512,
            )
            return (response.text or "").strip()
        except Exception as exc:
            logger.warning("[MEMORY] Compressão falhou: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# ConversationMemory — drop-in replacement para MessageHistory
# ---------------------------------------------------------------------------

class ConversationMemory:
    """
    Substitui MessageHistory com compressão assíncrona de contexto antigo.

    Interface idêntica à MessageHistory original:
      add(role, content, **kwargs)
      get_messages() -> list[Message]
      clear()
      __len__()

    Extensões:
      inject_strategy(strategy)       — define o compressor
      build_system_prompt(base) -> str — injeta long-term no prompt
    """

    def __init__(
        self,
        max_messages: int = 20,
        compress_trigger: int = 16,
        keep_after_compress: int = 4,
    ) -> None:
        self._short_term: deque[Message] = deque(maxlen=max_messages)
        self._long_term_summary: str = ""
        self._strategy: Optional[CompressionStrategy] = None
        self._pending_task: Optional[asyncio.Task] = None
        self._compress_trigger = compress_trigger
        self._keep_after_compress = keep_after_compress

    # ------------------------------------------------------------------
    # Configuração
    # ------------------------------------------------------------------

    def inject_strategy(self, strategy: CompressionStrategy) -> None:
        self._strategy = strategy

    # ------------------------------------------------------------------
    # Interface compatível com MessageHistory
    # ------------------------------------------------------------------

    def add(self, role: str, content: Optional[str] = None, **kwargs) -> None:
        msg = Message(role=role, content=content, **kwargs)
        self._short_term.append(msg)
        if self._strategy and len(self._short_term) >= self._compress_trigger:
            self._schedule_compression()

    def get_messages(self) -> list[Message]:
        return list(self._short_term)

    def clear(self) -> None:
        self._short_term.clear()
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()

    def __len__(self) -> int:
        return len(self._short_term)

    # ------------------------------------------------------------------
    # Extensão: injeção no system prompt
    # ------------------------------------------------------------------

    def build_system_prompt(self, base: str) -> str:
        if not self._long_term_summary:
            return base
        return (
            f"{base}\n\n"
            "## Contexto de Sessões Anteriores (Comprimido)\n"
            f"{self._long_term_summary}"
        )

    @property
    def long_term_summary(self) -> str:
        return self._long_term_summary

    # ------------------------------------------------------------------
    # Compressão assíncrona (nunca bloqueia o path de request)
    # ------------------------------------------------------------------

    def _schedule_compression(self) -> None:
        if self._pending_task and not self._pending_task.done():
            return

        all_msgs = list(self._short_term)
        to_compress = all_msgs[: -self._keep_after_compress]
        keep = all_msgs[-self._keep_after_compress :]

        if not to_compress:
            return

        # Esvazia e recoloca apenas os recentes antes de lançar a task
        self._short_term.clear()
        self._short_term.extend(keep)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Sem event loop ativo — descarta silenciosamente
            return

        self._pending_task = loop.create_task(
            self._run_compression(to_compress),
            name="memory_compression",
        )
        logger.debug("[MEMORY] Compressão agendada (%d mensagens)", len(to_compress))

    async def _run_compression(self, messages: list[Message]) -> None:
        new_fragment = await self._strategy.compress(messages)
        if not new_fragment:
            return

        if self._long_term_summary:
            # Mescla o resumo acumulado com o novo fragmento
            merged = await self._strategy.compress([
                Message(role="system", content="Resumo anterior: " + self._long_term_summary),
                Message(role="user", content="Novo fragmento a incorporar: " + new_fragment),
            ])
            self._long_term_summary = merged or self._long_term_summary
        else:
            self._long_term_summary = new_fragment

        logger.info("[MEMORY] Long-term summary atualizado (%d chars)", len(self._long_term_summary))
