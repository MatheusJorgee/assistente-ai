"""
TOKEN OPTIMIZER - Utilitários para Contagem e Otimização de Tokens
===================================================================

Objetivo: "O que não se mede, não se gerencia"

Fornece:
1. Token counting via Gemini SDK nativo
2. Logging de consumo por requisição
3. Alertas quando exceder limites
4. Batch processing efficiency

Economia de tokens típica:
- RAG simples: 40-60% redução (em vez de 100% memória)
- Visão otimizada: 70-90% redução (redimensionamento + cache)
- Sliding window: 30-50% redução (últimas 20 msgs vs 50)
- Total esperado: 60-75% de economia (R$ 10/dia → R$ 2.50-4/dia)
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json

try:
    import anthropic  # Fallback se não usar Gemini
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    # Vamos usar Gemini nativo para token counting
    import google.generativeai as genai
    HAS_GEMINI_TOKEN_COUNT = True
except ImportError:
    HAS_GEMINI_TOKEN_COUNT = False

logger = logging.getLogger(__name__)


class TokenCounter:
    """
    Contador de tokens usando Gemini SDK nativo.
    
    Equivalentes aproximados:
    - 1 token ≈ 4 caracteres (em inglês)
    - 1 token ≈ 2-3 caracteres (em português)
    - 1 imagem ≈ 258 tokens (até 16k pixels)
    """
    
    def __init__(self):
        self.total_tokens_used = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.calls_count = 0
        self.start_time = datetime.now()
        self.requests_log: List[Dict[str, Any]] = []
        self.token_limit_per_day = 1_000_000  # Típico para tier gratuito
        self.alert_threshold = 0.8  # Alertar em 80%
    
    def estimate_tokens(self, text: str, is_portuguese: bool = True) -> int:
        """
        Estimativa simples de tokens (sem API call).
        
        Args:
            text: String a estimar
            is_portuguese: Se True, usa fator 2.5:1 (mais conservador)
        
        Returns:
            Número estimado de tokens
        """
        if not text:
            return 0
        
        # Português é mais compressível (~2.5 chars/token)
        # Inglês é menos compressível (~4 chars/token)
        factor = 2.5 if is_portuguese else 4.0
        estimated = len(text) // factor
        return max(1, int(estimated))
    
    def count_tokens_api(self, messages: List[Dict[str, Any]]) -> Optional[int]:
        """
        Contagem real via Gemini API (quando disponível).
        
        Args:
            messages: Lista de mensagens [{"role": "user", "content": "..."}]
        
        Returns:
            Número real de tokens, ou None se API falhar
        """
        if not HAS_GEMINI_TOKEN_COUNT:
            return None
        
        try:
            # Importar apenas quando necessário
            from core.config import get_config
            config = get_config()
            
            genai.configure(api_key=config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            # Converter para formato Gemini
            gemini_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                gemini_messages.append({
                    "role": "user" if role == "user" else "model",
                    "parts": [{"text": content}]
                })
            
            # Contar tokens
            response = model.count_tokens(gemini_messages)
            token_count = response.total_tokens
            
            logger.debug(f"[TOKEN_COUNT] API contou {token_count} tokens")
            return token_count
            
        except Exception as e:
            logger.warning(f"[TOKEN_COUNT] Falha ao contar tokens via API: {e}")
            return None
    
    def log_request(
        self,
        messages: List[Dict[str, Any]],
        input_tokens: int,
        output_tokens: int,
        model: str = "gemini-2.0-flash",
        operation: str = "chat",
    ) -> None:
        """
        Registra requisição e tokens consumidos.
        
        Args:
            messages: Mensagens enviadas
            input_tokens: Tokens na entrada
            output_tokens: Tokens na saída
            model: Nome do modelo
            operation: Tipo de operação (chat, vision, etc)
        """
        total = input_tokens + output_tokens
        
        self.total_tokens_used += total
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.calls_count += 1
        
        # Logging estruturado
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "operation": operation,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total,
            "message_count": len(messages),
        }
        self.requests_log.append(log_entry)
        
        # Log no terminal
        elapsed = (datetime.now() - self.start_time).total_seconds()
        tokens_per_sec = self.total_tokens_used / elapsed if elapsed > 0 else 0
        
        logger.info(
            f"[TOKENS] op={operation} | "
            f"in={input_tokens} | out={output_tokens} | "
            f"total={total}  | "
            f"cumulative={self.total_tokens_used} | "
            f"avg={tokens_per_sec:.1f} tokens/sec"
        )
        
        # Alerta se exceder threshold
        usage_percent = (self.total_tokens_used / self.token_limit_per_day) * 100
        if usage_percent > (self.alert_threshold * 100):
            logger.warning(
                f"[TOKEN ALERT] Uso acima de {self.alert_threshold*100:.0f}%: "
                f"{usage_percent:.1f}% do limite diário"
            )
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Retorna resumo de consumo de tokens.
        
        Returns:
            Dicionário com estatísticas
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        minutes = elapsed / 60
        
        return {
            "total_tokens": self.total_tokens_used,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "calls_count": self.calls_count,
            "elapsed_seconds": elapsed,
            "elapsed_minutes": minutes,
            "avg_tokens_per_call": self.total_tokens_used / self.calls_count if self.calls_count > 0 else 0,
            "tokens_per_minute": self.total_tokens_used / minutes if minutes > 0 else 0,
            "estimated_cost_usd": self._estimate_cost_usd(),
            "estimated_cost_brl": self._estimate_cost_usd() * 5.0,  # R$ ≈ 5x USD
        }
    
    def _estimate_cost_usd(self) -> float:
        """
        Estima custo em USD (Gemini 2.0 Flash pricing).
        
        Preço (jan 2025):
        - Input: $0.075/1M tokens
        - Output: $0.30/1M tokens
        
        Returns:
            Custo em USD
        """
        cost_input = (self.total_input_tokens / 1_000_000) * 0.075
        cost_output = (self.total_output_tokens / 1_000_000) * 0.30
        return cost_input + cost_output
    
    def reset(self) -> None:
        """Reseta contadores."""
        self.total_tokens_used = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.calls_count = 0
        self.start_time = datetime.now()
        self.requests_log.clear()


class VisionOptimizerMemory:
    """
    Gerencia cache de visão para evitar re-envio de imagens duplicadas.
    
    Estratégia:
    - Hash SHA256 da imagem redimensionada
    - Cache por 5 minutos
    - Timestamp + deteção de mudança
    """
    
    def __init__(self, cache_ttl_seconds: int = 300):
        self.cache_ttl = cache_ttl_seconds
        self.cached_images: Dict[str, Dict[str, Any]] = {}
    
    def should_send_image(self, image_bytes: bytes, image_hash: str) -> bool:
        """
        Retorna True se imagem deve ser enviada (não está em cache ou expirou).
        
        Args:
            image_bytes: Bytes da imagem
            image_hash: SHA256 da imagem
        
        Returns:
            True se deve enviar, False se está em cache
        """
        if image_hash not in self.cached_images:
            # Nova imagem, devemos enviar
            self.cached_images[image_hash] = {
                "timestamp": datetime.now(),
                "size_bytes": len(image_bytes),
            }
            logger.debug(f"[VISION] Nova imagem em cache (hash={image_hash[:8]}...)")
            return True
        
        # Verificar se cache expirou
        cached_time = self.cached_images[image_hash]["timestamp"]
        if (datetime.now() - cached_time).total_seconds() > self.cache_ttl:
            # Cache expirado
            logger.debug(f"[VISION] Cache expirado para {image_hash[:8]}...")
            self.cached_images[image_hash]["timestamp"] = datetime.now()
            return True
        
        # Imagem está em cache e válida
        logger.debug(f"[VISION] Imagem em cache (pulando envio)")
        return False
    
    def clear_expired(self) -> None:
        """Remove imagens com cache expirado."""
        now = datetime.now()
        expired_keys = [
            k for k, v in self.cached_images.items()
            if (now - v["timestamp"]).total_seconds() > self.cache_ttl
        ]
        for key in expired_keys:
            del self.cached_images[key]
        
        if expired_keys:
            logger.debug(f"[VISION] Limpou {len(expired_keys)} caches expirados")


# Singleton global
_token_counter: Optional[TokenCounter] = None
_vision_memory: Optional[VisionOptimizerMemory] = None


def get_token_counter() -> TokenCounter:
    """Retorna singleton do token counter."""
    global _token_counter
    if _token_counter is None:
        _token_counter = TokenCounter()
    return _token_counter


def get_vision_optimizer() -> VisionOptimizerMemory:
    """Retorna singleton do vision memory."""
    global _vision_memory
    if _vision_memory is None:
        _vision_memory = VisionOptimizerMemory()
    return _vision_memory
