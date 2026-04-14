"""
sliding_window_context.py - Context Window Management para Chat Session
========================================================================

**PROBLEMA ARQUITETURAL:**
- Histórico cresce linearmente com tempo de sessão
- Cada nova mensagem adiciona tokens indefinidamente
- Estado da sessão: não precisa de 50+ mensagens no contexto ativo
- Solução: Manter "active window" fixo, mover histórico antigo para Obsidian

**DESIGN PATTERN: Bounded Memory with Persistence Layer**

Analogia de Arquitetura:
- Active Window (Gemini chat_session): "Short-term memory" (RAM cache)
- Obsidian Vault: "Long-term storage" (Disk persistent)
- Sliding Window pointer: Marca onde começou a janela ativa

FLUXO:

1. User message entra
   ↓
2. Adiciona to active_window (last_messages)
3. Se len(active_window) > max_messages:
   a. Extrai oldest message
   b. Cria RESUMO de contexto antigo
   c. Salva resumo no Obsidian Vault/Resumos/
   d. Remove message da active_window
   ↓
4. Gemini processa apenas messages na active_window
   → Tokens estáveis, nunca crescem além de limit

TOKEN IMPACT:
- Sem sliding window: 50 msgs × 400 chars = 20k chars ≈ 8k tokens
- Com sliding window (20 msgs):  20 msgs × 400 chars = 8k chars ≈ 3k tokens
- ECONOMIA: 62.5% tokens
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from .logger import get_logger
except ImportError:
    import logging
    get_logger = lambda x: logging.getLogger(x)

logger = get_logger(__name__)


@dataclass
class ChatMessage:
    """Representa uma mensagem no histórico."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa para dict (Gemini API format)."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class SlidingWindowContextManager:
    """
    Gerencia janela de contexto deslizante para chat session.

    **KEY INSIGHT:** Estado de uma conversa ≠ Histórico completo.

    O modelo precisa de contexto recente para manter continuidade, mas não precisa
    de TUDO. Mensagens antigas → Obsidian (para RAG posterior se necessário).

    Exemplo:
    ```
    Session: 50 mensagens totais
    Active Window: últimas 20 (em RAM)
    "Movidas para Obsidian": primeiras 30 (resumidas)

    Quando user perguntar sobre algo lá atrás:
    RAG buscará no Obsidian, injetará contexto relevante
    ```
    """

    def __init__(
        self,
        max_active_messages: int = 20,
        summary_window_size: int = 5,
    ):
        """
        Args:
            max_active_messages: Máximo de mensagens na janela ativa
            summary_window_size: Quantas mensagens agrupar em 1 resumo
        """
        self.max_active_messages = max_active_messages
        self.summary_window_size = summary_window_size
        
        self.messages: List[ChatMessage] = []  # Janela ativa (RAM)
        self.summarized_count = 0  # Contador de mensagens summarizadas
        self.total_messages_processed = 0  # Total histórico

    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[ChatMessage]]:
        """
        Adiciona mensagem ao histórico e aplica sliding window.

        Returns:
            Lista de mensagens antigas que foram removidas (se houver)
            Essas devem ser summarizadas e movidas para Obsidian
        """
        msg = ChatMessage(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        self.total_messages_processed += 1

        removed_messages: Optional[List[ChatMessage]] = None

        # Aplicar sliding window
        if len(self.messages) > self.max_active_messages:
            # Remover mensagens antigas
            batch_size = len(self.messages) - self.max_active_messages
            removed_messages = self.messages[:batch_size]
            self.messages = self.messages[batch_size:]
            self.summarized_count += batch_size

            logger.info(
                f"[CONTEXT] Sliding window ativado: removidas {batch_size} msgs antigo. "
                f"Ativa: {len(self.messages)}, Total: {self.total_messages_processed}"
            )

        return removed_messages

    def get_active_messages(self) -> List[Dict[str, Any]]:
        """
        Retorna mensagens ativas no formato esperado pelo Gemini API.

        Formato de saída:
        [
            {"role": "user", "content": "Olá"},
            {"role": "assistant", "content": "Oi!"},
            ...
        ]

        Returns:
            Lista de mensagens para passar ao LLM
        """
        return [msg.to_dict() for msg in self.messages]

    def get_context_info(self) -> Dict[str, Any]:
        """
        Retorna informações sobre o estado do contexto.

        Útil para logging e debugging.
        """
        return {
            "active_messages_count": len(self.messages),
            "max_active_messages": self.max_active_messages,
            "summarized_messages_count": self.summarized_count,
            "total_messages_processed": self.total_messages_processed,
            "window_utilization_percent": (len(self.messages) / self.max_active_messages) * 100,
            "estimated_tokens_active": self._estimate_tokens(),
        }

    def _estimate_tokens(self) -> int:
        """
        Estima tokens da janela ativa (português: ~2.5 chars/token).

        Returns:
            Número estimado de tokens
        """
        total_chars = sum(len(msg.content) for msg in self.messages)
        # Português é mais compressível: ~2.5 chars por token
        return max(1, total_chars // 3)  # Conservative estimate

    def clear(self) -> None:
        """Limpa contexto ativo."""
        self.messages.clear()
        logger.info("[CONTEXT] Histórico limpo")

    def prepare_summarization_batch(self, batch_size: Optional[int] = None) -> str:
        """
        Prepara texto para summarização (quando histórico foi movido).

        Args:
            batch_size: Quantas mensagens agrupar. Default: summary_window_size

        Returns:
            String formatada com as mensagens removidas
        """
        if batch_size is None:
            batch_size = self.summary_window_size

        # As mensagens foram removidas, então reconstroem a partir de
        # self.summarized_count. Aqui apenas montamos o texto para resumir.

        # NOTA: Esta função é mais utilitária - a real summarização
        # deve acontecer quando as mensagens são removidas (em add_message)

        return f"[Conversa de {batch_size} mensagens resumida]"

    def get_first_message(self) -> Optional[ChatMessage]:
        """Retorna primeira mensagem ativa."""
        return self.messages[0] if self.messages else None

    def get_last_message(self) -> Optional[ChatMessage]:
        """Retorna última mensagem ativa."""
        return self.messages[-1] if self.messages else None
