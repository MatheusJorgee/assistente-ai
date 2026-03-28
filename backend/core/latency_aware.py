"""
Sistema de Consciência de Latência (Latency-Aware System)
Implementa sinalização de 'pensamento longo' via mensagens intermediárias.

Padrão: Streaming de resposta parcial + Background Tasks
"""

import asyncio
import time
import re
import unicodedata
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class TaskComplexity(Enum):
    """Complexidade estimada de uma tarefa."""
    INSTANT = 0  # < 500ms (resposta direta)
    QUICK = 1  # 500ms - 2s (buscas simples)
    MODERATE = 2  # 2s - 5s (múltiplas buscas)
    LONG = 3  # > 5s (web scraping, múltiplas chamadas API)


@dataclass
class IntermediateMessage:
    """Mensagem intermediária de progresso."""
    step: str  # 'thinking', 'searching', 'fetching', etc
    message: str  # Texto legível: "Isso vai levar um momento..."
    suggestion: Optional[str] = None  # Sugestão: "Quer músicas de fundo?"
    estimated_wait_ms: int = 0  # Tempo estimado em ms


class LatencyAwarenessDetector:
    """
    Detector de tarefas que requerem processamento longo.
    Estima complexidade baseado em keywords e padrões.
    """
    
    # Keywords que indicam tarefas longas
    LONG_TASK_KEYWORDS = {
        'pesquis': TaskComplexity.MODERATE,  # pesquisa, pesquisar
        'busca': TaskComplexity.MODERATE,
        'procur': TaskComplexity.MODERATE,  # procura, procurar
        'google': TaskComplexity.MODERATE,
        'internet': TaskComplexity.MODERATE,
        'site': TaskComplexity.MODERATE,
        'github': TaskComplexity.MODERATE,
        'scrape': TaskComplexity.LONG,
        'multiplo': TaskComplexity.MODERATE,  # múltiplos
        'vário': TaskComplexity.MODERATE,  # vários
        'varios': TaskComplexity.MODERATE,
        'youtube search': TaskComplexity.QUICK,
        'filme': TaskComplexity.LONG,  # Buscar música de filme
        'tema': TaskComplexity.LONG,  # Tema de algo
        'aquela musica': TaskComplexity.LONG,
        'describe': TaskComplexity.MODERATE,  # Descrição vaga
        'descrev': TaskComplexity.MODERATE,
    }
    
    # Keywords que indicam tarefas instânteas
    INSTANT_TASK_KEYWORDS = {
        'toca': TaskComplexity.INSTANT,
        'play': TaskComplexity.INSTANT,
        'pause': TaskComplexity.INSTANT,
        'parar': TaskComplexity.INSTANT,
        'próxim': TaskComplexity.INSTANT,
        'skip': TaskComplexity.INSTANT,
        'volum': TaskComplexity.INSTANT,
        'abrir': TaskComplexity.INSTANT,
        'clica': TaskComplexity.INSTANT,
    }
    
    def __init__(self):
        self.history: Dict[str, TaskComplexity] = {}
    
    def detect_complexity(self, user_input: str) -> TaskComplexity:
        """
        Detecta complexidade de uma tarefa baseado no input do usuário.
        
        Args:
            user_input: Mensagem do usuário
            
        Returns:
            TaskComplexity estimada
        """
        input_lower = user_input.lower()
        
        # Normalizar acentos para melhor matching
        normalized = unicodedata.normalize('NFKD', input_lower).encode('ascii', 'ignore').decode('ascii')
        
        # Checklist de keywords simples primeiro
        for keyword, complexity in self.INSTANT_TASK_KEYWORDS.items():
            # Check with word boundaries to avoid matching substrings
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, normalized, re.IGNORECASE) or re.search(pattern, input_lower, re.IGNORECASE):
                return complexity
        
        # Depois keywords de tarefas longas
        max_complexity = TaskComplexity.INSTANT
        for keyword, complexity in self.LONG_TASK_KEYWORDS.items():
            # Check with word boundaries but also allow prefixes at word boundary
            # This allows "pesquis" to match "pesquisa", "busca" to match exactly
            pattern = r'\b' + re.escape(keyword)
            if re.search(pattern, normalized, re.IGNORECASE) or re.search(pattern, input_lower, re.IGNORECASE):
                if complexity.value > max_complexity.value:
                    max_complexity = complexity
        
        # Heurística adicional: múltiplos items (playlist, artistas, etc)
        # Procurar por fragmentos de "múltiplos" devido às várias formas
        mult_found = any(word in normalized for word in ['mult', 'varios', 'vario'])
        item_found = any(word in normalized for word in ['artista', 'musica', 'playlist', 'cancao', 'canção', 'item', 'cria'])
        
        if mult_found and item_found:
            if max_complexity.value < TaskComplexity.LONG.value:
                max_complexity = TaskComplexity.LONG
        
        # Se não teve match, usar heurística de tamanho + pontuação
        if max_complexity == TaskComplexity.INSTANT and len(input_lower) > 50:
            max_complexity = TaskComplexity.MODERATE
        
        return max_complexity
    
    def get_intermediate_message(self, complexity: TaskComplexity) -> IntermediateMessage:
        """
        Gera mensagem intermediária baseada na complexidade.
        
        Args:
            complexity: Nível de complexidade detectado
            
        Returns:
            IntermediateMessage com sugestão contextual
        """
        messages_by_complexity = {
            TaskComplexity.INSTANT: IntermediateMessage(
                step='instant',
                message='Deixa eu fazer isso agora.',
                estimated_wait_ms=0
            ),
            TaskComplexity.QUICK: IntermediateMessage(
                step='quick_search',
                message='Um segundo enquanto busco isso pra ti.',
                estimated_wait_ms=1500
            ),
            TaskComplexity.MODERATE: IntermediateMessage(
                step='moderate_search',
                message='Isso vai levar um momento, Matheus. Quer que eu coloque uma música de fundo enquanto pesquiso?',
                suggestion='play_background_music',
                estimated_wait_ms=4000
            ),
            TaskComplexity.LONG: IntermediateMessage(
                step='long_task',
                message='Essa questão é mais complexa. Deixa eu fazer um web scraping detalhado. Enquanto isso, gostaria de uma música relaxante?',
                suggestion='play_relaxing_music',
                estimated_wait_ms=7000
            ),
        }
        
        return messages_by_complexity.get(
            complexity,
            IntermediateMessage(
                step='unknown',
                message='Processando sua solicitação...',
                estimated_wait_ms=3000
            )
        )


class StreamingResponseManager:
    """
    Gerenciar envio de respostas em streaming via WebSocket.
    Permite múltiplas mensagens antes do resultado final.
    """
    
    def __init__(self, websocket_send_callback: Callable):
        """
        Args:
            websocket_send_callback: Função para enviar via ws (async)
        """
        self.send_callback = websocket_send_callback
        self.active_request_id = None
    
    async def send_intermediate(
        self,
        intermediate_msg: IntermediateMessage,
        request_id: str = 'default'
    ) -> None:
        """
        Envia mensagem intermediária via WebSocket.
        
        Args:
            intermediate_msg: Mensagem a enviar
            request_id: ID para rastrear request
        """
        import json
        
        payload = {
            'type': 'intermediate',
            'request_id': request_id,
            'step': intermediate_msg.step,
            'text': intermediate_msg.message,
            'suggestion': intermediate_msg.suggestion,
            'estimated_wait_ms': intermediate_msg.estimated_wait_ms,
            'timestamp': time.time()
        }
        
        try:
            await self.send_callback(json.dumps(payload))
        except Exception as e:
            print(f"[ERRO StreamingResponse] Falha ao enviar intermediária: {e}")
    
    async def send_final(
        self,
        text: str,
        audio_base64: str = '',
        request_id: str = 'default'
    ) -> None:
        """
        Envia resposta final via WebSocket.
        
        Args:
            text: Texto da resposta
            audio_base64: Áudio codificado em base64
            request_id: ID para rastrear request
        """
        import json
        
        payload = {
            'type': 'final',
            'request_id': request_id,
            'text': text,
            'audio': audio_base64,
            'timestamp': time.time()
        }
        
        try:
            await self.send_callback(json.dumps(payload))
        except Exception as e:
            print(f"[ERRO StreamingResponse] Falha ao enviar final: {e}")


class LatencyOptimizedExecutor:
    """
    Executor que roda tarefas longas em background com feedback intermediário.
    """
    
    def __init__(self, streaming_manager: StreamingResponseManager):
        self.streaming_manager = streaming_manager
        self.complexity_detector = LatencyAwarenessDetector()
    
    async def execute_with_awareness(
        self,
        user_input: str,
        main_task,  # Callable[[], Coroutine] - async function
        request_id: str = 'default',
        should_suggest_music: bool = True
    ):
        """
        Executa tarefa com consciência de latência.
        Se for longa, envia mensagem intermediária antes.
        
        Args:
            user_input: Mensagem do usuário
            main_task: Tarefa assíncrona principal
            request_id: ID para rastrear
            should_suggest_music: Se deve sugerir música de fundo
            
        Returns:
            (text, audio) da resposta final
        """
        # 1. Detectar complexidade
        complexity = self.complexity_detector.detect_complexity(user_input)
        
        # 2. Se for tarefa longa, enviar intermediária
        if complexity.value >= TaskComplexity.MODERATE.value:
            intermediate = self.complexity_detector.get_intermediate_message(complexity)
            await self.streaming_manager.send_intermediate(intermediate, request_id)
            
            # Se houver sugestão, disparar música em background
            if should_suggest_music and intermediate.suggestion:
                asyncio.create_task(self._trigger_background_music(intermediate.suggestion))
        
        # 3. Executar tarefa principal
        try:
            text, audio = await asyncio.wait_for(
                main_task(),
                timeout=30  # Timeout de 30s
            )
        except asyncio.TimeoutError:
            text = "A tarefa demorou demais. Pode tentar novamente?"
            audio = ""
        
        return text, audio
    
    async def _trigger_background_music(self, suggestion_type: str):
        """
        Dispara música de fundo em paralelo.
        Não bloqueia o processamento principal.
        """
        # Será implementado via Tool Registry
        print(f"[BACKGROUND] Sugestão de música: {suggestion_type}")


def create_latency_aware_system(websocket_send_callback):
    """
    Factory para criar sistema de latência.
    
    Args:
        websocket_send_callback: função async para enviar ws
        
    Returns:
        LatencyOptimizedExecutor pronto
    """
    streaming_mgr = StreamingResponseManager(websocket_send_callback)
    return LatencyOptimizedExecutor(streaming_mgr)
