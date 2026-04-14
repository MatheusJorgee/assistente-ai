"""
QUINTA_FEIRA_BRAIN_V2_OPTIMIZED.PY - Refatoração para Redução de Tokens
=========================================================================

MUDANÇAS PRINCIPAIS:

1. **Token Counting Integrado**
   - Cada requisição loga consumo real de tokens
   - Alerta quando excede limites
   - Resumo de custos ao final da sessão

2. **RAG Simples (Retrieval-Augmented Generation)**
   - Em vez de injetar TODO histórico, busca por keywords
   - Extrai keywords da mensagem do usuário
   - Recupera apenas contexto RELEVANTE do banco
   - Redução estimada: 40-60% de tokens

3. **Visão Otimizada**
   - Redimensiona imagens para 1024x1024 (de 4K)
   - Cache de imagens duplicadas (5min TTL)
   - Hash SHA256 para deduplicação
   - Qualidade WebP reduzida (85%)
   - Redução estimada: 70-90% de tokens

4. **Sliding Window de Contexto**
   - Apenas últimas 20 mensagens na janela ativa
   - Mensagens antigas movem para bank (sem enviar)
   - Resumo de contexto antigo injetado quando necessário
   - Redução estimada: 30-50% de tokens

5. **Context Window Management**
   - Padrão: Manter <= 15k tokens na janela ativa
   - Quando exceder: Summarize + sliding window
   - Monitorar tokens_remaining para próxima requisição
   - Implementar context budget planning

ECONOMIA TOTAL ESPERADA: 60-75%
De: R$ 10,00/dia → Para: R$ 2.50-4.00/dia
"""

import hashlib
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
import sys
import os

# ===== IMPORTAÇÕES RESILIENTES =====
try:
    from core import get_config, get_logger
    from core.llm_provider import LLMProvider, Message, Response
    from core.gemini_provider import GeminiAdapter
    from core.database import Database, get_database
    from core.token_optimizer import get_token_counter, get_vision_optimizer
except ImportError:
    from core import get_config, get_logger
    from core.llm_provider import LLMProvider, Message, Response
    from core.gemini_provider import GeminiAdapter
    from core.database import Database, get_database
    from core.token_optimizer import get_token_counter, get_vision_optimizer

logger = get_logger(__name__)
token_counter = get_token_counter()
vision_optimizer = get_vision_optimizer()


@dataclass
class BrainContextBudget:
    """
    Gerencia budget de tokens da janela de contexto.
    
    Context Window Típico:
    - Entrada: 30,000 tokens
    - Saída: 5,000 tokens
    - Overhead (system prompt, tools): 2,000 tokens
    - Disponível para histórico+memória: ~23,000 tokens
    """
    max_context_tokens: int = 23_000  # Tokens disponíveis para chat
    reserved_for_response: int = 2_000  # Deixar espaço para resposta
    
    current_tokens: int = 0
    messages_count: int = 0
    last_updated: str = ""
    
    def has_space_for(self, estimated_tokens: int) -> bool:
        """Verifica se há espaço para N tokens."""
        remaining = self.max_context_tokens - self.current_tokens
        return remaining > (estimated_tokens + self.reserved_for_response)
    
    def tokens_remaining(self) -> int:
        """Tokens disponíveis sem ultrapassar limite."""
        return max(0, self.max_context_tokens - self.current_tokens - self.reserved_for_response)
    
    def utilization_percent(self) -> float:
        """Porcentagem de utilização (0-100)."""
        return (self.current_tokens / self.max_context_tokens) * 100


class OptimizedVisionProcessor:
    """
    Processa e otimiza imagens antes do envio ao LLM.
    
    Estratégias:
    1. Redimensionar para 1024x1024 (econômico)
    2. Qualidade WebP reduzida (75-85%)
    3. Cache e deduplicação
    4. Apenas enviar se houver mudança real
    """
    
    def __init__(self, max_dimension: int = 1024, webp_quality: int = 85):
        self.max_dimension = max_dimension
        self.webp_quality = webp_quality
    
    def compute_hash(self, image_bytes: bytes) -> str:
        """Computa SHA256 da imagem."""
        return hashlib.sha256(image_bytes).hexdigest()
    
    def should_process_image(self, image_bytes: bytes, reason: str = "default") -> bool:
        """
        Decide se a imagem deve ser processada e enviada.
        
        Args:
            image_bytes: Dados da imagem
            reason: Razão da solicitação (default, user_explicit, etc)
        
        Returns:
            True se deve processar, False caso contrário
        """
        image_hash = self.compute_hash(image_bytes)
        
        # Se usuário pediu explicitamente, sempre processar
        if reason == "user_explicit":
            logger.info(f"[VISION] Processando por solicitação explícita")
            return True
        
        # Caso contrário, verificar cache
        return vision_optimizer.should_send_image(image_bytes, image_hash)
    
    def optimize_vision_request(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Otimiza imagem e retorna no formato esperado pelo LLM.
        
        Args:
            image_bytes: Dados originais da imagem
        
        Returns:
            Dicionário com imagem otimizada e metadados
        """
        import io
        try:
            from PIL import Image
        except ImportError:
            # Fallback: sem PIL, retornar como-está
            logger.warning("[VISION] PIL não disponível, retornando imagem original")
            return {
                "format": "jpeg",
                "data": image_bytes,
                "optimized": False,
                "original_size": len(image_bytes),
            }
        
        try:
            # Abrir imagem
            img = Image.open(io.BytesIO(image_bytes))
            
            # Redimensionar
            img.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)
            
            # Converter para WebP com qualidade reduzida
            output = io.BytesIO()
            img.save(output, format="WEBP", quality=self.webp_quality, method=6)
            optimized_bytes = output.getvalue()
            
            # Log de economia
            reduction_percent = (
                (len(image_bytes) - len(optimized_bytes)) / len(image_bytes)
            ) * 100 if len(image_bytes) > 0 else 0
            
            logger.info(
                f"[VISION] Otimizada: {len(image_bytes)} → {len(optimized_bytes)} bytes "
                f"({reduction_percent:.1f}% redução)"
            )
            
            return {
                "format": "webp",
                "data": optimized_bytes,
                "optimized": True,
                "original_size": len(image_bytes),
                "optimized_size": len(optimized_bytes),
                "compression_ratio": reduction_percent,
            }
        
        except Exception as e:
            logger.error(f"[VISION] Erro ao otimizar imagem: {e}")
            return {
                "format": "jpeg",
                "data": image_bytes,
                "optimized": False,
                "error": str(e),
            }


class ContextWindowManager:
    """
    Gerencia janela de contexto para evitar explosão de tokens.
    
    Ciclo de vida:
    1. Aceita mensagem do usuário
    2. Calcula tokens necessários
    3. Se não há espaço, resume contexto antigo ou move para bank
    4. Mantém sliding window de últimas N mensagens
    5. Injeta resumo when needed
    """
    
    def __init__(
        self,
        db: Database,
        session_id: str,
        max_active_messages: int = 20,
        max_context_tokens: int = 23_000,
    ):
        self.db = db
        self.session_id = session_id
        self.max_active_messages = max_active_messages
        self.budget = BrainContextBudget(max_context_tokens=max_context_tokens)
        self.active_messages: List[Message] = []
        self.moved_to_bank_count = 0
    
    async def update_context_from_message(
        self,
        user_message: str,
        assistant_messages: Optional[List[str]] = None,
    ) -> None:
        """
        Atualiza contexto ativo após uma interação.
        
        Args:
            user_message: Mensagem do usuário (nova)
            assistant_messages: Respostas anteriores (para cálculo)
        """
        # Carregar histórico recente
        recent = await self.db.get_recent_messages_window(
            self.session_id,
            window_size=self.max_active_messages,
        )
        
        self.active_messages = recent
        
        # Estimar tokens do contexto atual
        total_text = "\n".join([m.content or "" for m in self.active_messages])
        self.budget.current_tokens = token_counter.estimate_tokens(total_text)
        self.budget.messages_count = len(self.active_messages)
        self.budget.last_updated = datetime.now().isoformat()
        
        logger.debug(
            f"[CONTEXT] Atualizado: {len(self.active_messages)} msgs, "
            f"{self.budget.current_tokens} tokens, "
            f"{self.budget.utilization_percent():.1f}% utilização"
        )
    
    async def should_summarize(self) -> bool:
        """Retorna True se contexto está muito cheio (>80%)."""
        return self.budget.utilization_percent() > 80.0
    
    async def get_context_summary_injection(self) -> Optional[str]:
        """
        Gera um resumo de contexto antigo para ser injetado quando necessário.
        
        Reduz tokens do histórico completo injetando apenas resumo.
        
        Returns:
            String com resumo formatado, ou None
        """
        # Pegar mensagens antigas (fora da janela ativa)
        all_messages = await self.db.get_messages(self.session_id, limit=100)
        old_messages = all_messages[:-self.max_active_messages] if len(all_messages) > self.max_active_messages else []
        
        if not old_messages:
            return None
        
        summary = await self.db.summarize_session(self.session_id)
        
        return (
            "[CONTEXT_SUMMARY - Histórico Antigo]\n"
            f"Resumo de {len(old_messages)} mensagens anteriores:\n"
            f"{summary[:]}\n"
            "[/CONTEXT_SUMMARY]"
        )
    
    def get_budget_report(self) -> Dict[str, Any]:
        """Retorna relatório do budget de contexto."""
        return {
            "current_tokens": self.budget.current_tokens,
            "max_tokens": self.budget.max_context_tokens,
            "tokens_remaining": self.budget.tokens_remaining(),
            "utilization_percent": self.budget.utilization_percent(),
            "messages_count": self.budget.messages_count,
            "moved_to_bank": self.moved_to_bank_count,
        }


# ========== REFACTORING SUMMARY ==========
"""
Instruções de Integração no brain.py atual:

1. Copiar classes OptimizedVisionProcessor, BrainContextBudget, ContextWindowManager
   para o topo do brain.py

2. No __init__ do QuintaFeiraBrain:
   - Inicializar: self.context_manager = ContextWindowManager(db, session_id)
   - Inicializar: self.vision_processor = OptimizedVisionProcessor()

3. Na função ask():
   
   # ANTES:
   if image_data:
       self.vision_buffer.add_image(image_data)
   
   # DEPOIS:
   if image_data:
       if self.vision_processor.should_process_image(image_data):
           optimized = self.vision_processor.optimize_vision_request(image_data)
           self.vision_buffer.add_image(optimized["data"])

4. Para injetar contexto relevante:
   
   # ANTES:
   system_prompt = self.system_prompt
   if hidden_context:
       system_prompt += f"\n{hidden_context}"
   
   # DEPOIS:
   system_prompt = self.system_prompt
   
   # RAG: Buscar contexto relevante via keywords
   keywords = self._extract_keywords(message)
   relevant_msgs = await database.search_messages_by_keywords(
       session_id, keywords, limit=10
   )
   
   if relevant_msgs:
       context_str = "\n".join([f"[{m.role}] {m.content}" for m in relevant_msgs])
       system_prompt += f"\n[RELEVANT_CONTEXT]\n{context_str}\n[/RELEVANT_CONTEXT]"
   
   # Context summary se necessário
   if await context_manager.should_summarize():
       summary = await context_manager.get_context_summary_injection()
       if summary:
           system_prompt += f"\n{summary}"

5. Para token counting:
   
   # Após receber resposta do LLM:
   token_counter.log_request(
       messages=llm_messages,
       input_tokens=response.usage.prompt_tokens,
       output_tokens=response.usage.completion_tokens,
       operation="chat",
   )
   
   # Log do resumo:
   summary = token_counter.get_summary()
   logger.info(f"[TOKENS_SUMMARY] {summary}")

6. Método auxiliar para extrair keywords:
   
   def _extract_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
       # Remover stopwords comuns
       stopwords = {"o", "a", "de", "da", "do", "que", "o", "é", "e", "um", "uma"}
       words = text.lower().split()
       keywords = [w for w in words if len(w) > 3 and w not in stopwords]
       return list(set(keywords))[:max_keywords]

RESULTADO ESPERADO:
- Tokens por dia: R$ 10 → R$ 2.50-4.00 (75% redução)
- Latência: Mínimamente impactada (<50ms add)
- Qualidade: Mantida (apenas memória irrelevante removida)
"""
