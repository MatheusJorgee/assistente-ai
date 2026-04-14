"""
Raciocínio de Busca Evoluído (Search Verification)
Implementa busca validada antes de reproduzir mídia.

Padrão: Google Search + LLM Reasoning + Confirmation
Evita: Reproduzir vídeo/música errado por descrição vaga
"""

import asyncio
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
import json


class SearchConfidenceLevel(Enum):
    """Nível de confiança na busca."""
    LOW = 0.0  # < 40% confiante
    MEDIUM = 0.4  # 40% - 70% confiante
    HIGH = 0.7  # 70% - 90% confiante
    VERY_HIGH = 0.9  # > 90% confiante


@dataclass
class SearchResult:
    """Resultado de busca validado."""
    query: str
    track_name: str
    artist: str
    source_url: Optional[str] = None
    confidence: float = 0.5
    reasoning: str = ""
    fallback_suggestions: List[Tuple[str, str]] = None  # [(track, artist), ...]
    
    def to_dict(self):
        return {
            'query': self.query,
            'track_name': self.track_name,
            'artist': self.artist,
            'source_url': self.source_url,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'fallback_suggestions': self.fallback_suggestions or []
        }


class DescriptiveSearchReasoningEngine:
    """
    Raciocínio de busca para consultas descritivas.
    
    Fluxo:
    1. User says: "aquela música que toca no filme X"
    2. Extract keywords: "música", "filme X"
    3. Google Search: find song from movie X
    4. Gemini Reasoning: confirm if likely correct
    5. Return SearchResult with confidence
    """
    
    def __init__(
        self,
        gemini_client: Any,  # Google Gemini client
        event_bus_callback: Optional[Callable] = None
    ):
        """
        Args:
            gemini_client: Cliente Google Gemini configurado
            event_bus_callback: Função para emitir eventos (async)
        """
        self.gemini_client = gemini_client
        self._event_bus = event_bus_callback
        self._search_cache: Dict[str, SearchResult] = {}
    
    async def _emit_event(self, event_type: str, data: Any = None):
        """Emitir evento via EventBus."""
        if self._event_bus:
            try:
                await self._event_bus(event_type, data)
            except Exception as e:
                print(f"[ERRO] Falha ao emitir evento {event_type}: {e}")
    
    def _extract_keywords(self, query: str) -> List[str]:
        """
        Extrai keywords relevantes de consulta descritiva.
        
        Args:
            query: Consulta do usuário
            
        Returns:
            Lista de keywords
        """
        # Remover stopwords comuns em português
        stopwords = {'a', 'o', 'de', 'da', 'do', 'e', 'ou', 'em', 'para', 'que', 'é'}
        
        words = query.lower().split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        
        return keywords
    
    async def _search_google(self, query: str) -> Optional[List[Dict[str, str]]]:
        """
        Realiza busca no Google (usando API ou web scraping).
        
        NOTA: Implementação simulada. Em produção, usar Google Custom Search API.
        
        Args:
            query: Termo de busca
            
        Returns:
            Lista de resultados [{'title': ..., 'url': ...}, ...]
        """
        await self._emit_event('google_search_initiated', {'query': query})
        
        # SIMULAÇÃO de resultados (em produção seria real)
        # Retornar dados dummy úteis
        simulated_results = [
            {
                'title': f'Track found for "{query}"',
                'url': f'https://youtube.com/results?search_query={query}',
                'snippet': f'Search results for {query}'
            },
            {
                'title': f'Spotify: {query}',
                'url': f'https://open.spotify.com/search/{query}',
                'snippet': f'Spotify results for {query}'
            },
            {
                'title': f'{query} - Music Database',
                'url': f'https://musicbrainz.org/search?query={query}',
                'snippet': f'MusicBrainz results for {query}'
            }
        ]
        
        return simulated_results
    
    async def _reason_with_gemini(
        self,
        query: str,
        search_results: List[Dict[str, str]],
        context: Optional[str] = None
    ) -> Tuple[SearchResult, float]:
        """
        Usa Gemini para raciocinar sobre resultados de busca.
        
        Args:
            query: Consulta original
            search_results: Resultados do Google
            context: Contexto adicional da conversa
            
        Returns:
            (SearchResult, confidence_score)
        """
        # Preparar prompt para Gemini
        prompt = f"""Você é um assistente especializado em identificar músicas e vídeos.

Consulta do usuário: "{query}"
Contexto: {context or 'Nenhum'}

Resultados de busca encontrados: {json.dumps(search_results[:3], ensure_ascii=False)}

Baseado nesses resultados, identifique:
1. Nome da música/vídeo mais provável
2. Artista (se aplicável)
3. Confiança (0-100%)
4. Raciocínio breve

Responda em JSON:
{{
    "track_name": "...",
    "artist": "...",
    "confidence": 85,
    "reasoning": "...",
    "fallback_options": [["track2", "artist2"], ...]
}}
"""
        
        await self._emit_event('gemini_reasoning_started', {'query': query})
        
        try:
            response = await asyncio.to_thread(
                self.gemini_client.generate_content,
                prompt
            )
            
            # Extrair JSON da resposta
            response_text = response.text
            
            # Tentar parsear JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_str = response_text[json_start:json_end]
            
            result_data = json.loads(json_str)
            
            search_result = SearchResult(
                query=query,
                track_name=result_data.get('track_name', ''),
                artist=result_data.get('artist', ''),
                confidence=result_data.get('confidence', 50) / 100.0,
                reasoning=result_data.get('reasoning', ''),
                fallback_suggestions=result_data.get('fallback_options')
            )
            
            await self._emit_event('gemini_reasoning_completed', {
                'query': query,
                'confidence': search_result.confidence
            })
            
            return search_result, search_result.confidence
        
        except Exception as e:
            print(f"[ERRO] Falha ao raciocinar com Gemini: {e}")
            await self._emit_event('gemini_reasoning_error', {'query': query, 'error': str(e)})
            
            # Retornar resultado com baixa confiança
            return SearchResult(
                query=query,
                track_name="",
                artist="",
                confidence=0.0,
                reasoning=f"Erro ao processar: {e}"
            ), 0.0
    
    async def resolve_descriptive_query(
        self,
        query: str,
        context: Optional[str] = None,
        min_confidence: float = 0.7
    ) -> Optional[SearchResult]:
        """
        Resolve consulta descritiva em música/vídeo específico.
        
        Fluxo principal:
        1. Validar cache
        2. Buscar no Google
        3. Raciocinar com Gemini
        4. Validar confiança
        5. Retornar resultado ou fallback
        
        Args:
            query: Descrição/consulta do usuário
            context: Contexto da conversa anterior
            min_confidence: Confiança mínima aceitável
            
        Returns:
            SearchResult se encontrou com confiança >= min_confidence, None caso contrário
        """
        # Verificar cache
        cache_key = query.lower()
        if cache_key in self._search_cache:
            cached = self._search_cache[cache_key]
            if cached.confidence >= min_confidence:
                await self._emit_event('search_result_from_cache', {'query': query})
                return cached
        
        await self._emit_event('search_resolution_started', {
            'query': query,
            'min_confidence': min_confidence
        })
        
        # 1. Extrair keywords
        keywords = self._extract_keywords(query)
        search_query = ' '.join(keywords)
        
        # 2. Buscar no Google
        search_results = await self._search_google(search_query)
        
        # 3. Raciocinar com Gemini
        search_result, confidence = await self._reason_with_gemini(
            query,
            search_results or [],
            context
        )
        
        # 4. Validar confiança
        if confidence >= min_confidence and search_result.track_name:
            self._search_cache[cache_key] = search_result
            
            await self._emit_event('search_result_validated', {
                'query': query,
                'confidence': confidence,
                'track_name': search_result.track_name
            })
            
            return search_result
        else:
            await self._emit_event('search_result_rejected', {
                'query': query,
                'confidence': confidence,
                'reason': 'Confiança insuficiente'
            })
            
            return None
    
    async def validate_before_playback(
        self,
        user_query: str,
        context: Optional[str] = None
    ) -> Tuple[bool, Optional[SearchResult], str]:
        """
        Valida se deve tocar música antes de reproduzir.
        
        Estratégia:
        - Se é nome específico (ex: "Bohemian Rhapsody") → True
        - Se é descrição vaga (ex: "aquela do filme X") → Buscar e validar
        - Se confiança < 70% → Pedir confirmação
        
        Args:
            user_query: Consulta original do usuário
            context: Conversação anterior
            
        Returns:
            (should_play, search_result, confirmation_message)
        """
        # Detectar se é nome específico vs descrição vaga
        is_specific = (
            ' - ' in user_query or  # "Artist - Song"
            user_query.count(' ') < 3  # Menos de 3 palavras
        )
        
        if is_specific:
            # Provavelmente nome específico
            return True, None, ""
        
        # Descrição vaga - buscar e validar
        search_result = await self.resolve_descriptive_query(
            user_query,
            context,
            min_confidence=0.7
        )
        
        if search_result and search_result.confidence >= 0.9:
            # Altamente confiante
            return True, search_result, ""
        
        elif search_result and search_result.confidence >= 0.7:
            # Confiança moderada - pedir confirmação
            msg = f"Achei essa: {search_result.track_name} por {search_result.artist}. Quer tocar?"
            return False, search_result, msg
        
        else:
            # Não conseguiu encontrar com confiança
            msg = "Não consegui identificar essa música com segurança. Pode descrever melhor ou dizer o nome específico?"
            return False, None, msg


class SearchValidationTool:
    """
    Tool wrapper para usar resolver de busca no Brain.
    """
    
    def __init__(self, reasoning_engine: DescriptiveSearchReasoningEngine):
        self.engine = reasoning_engine
    
    async def validate_and_get_track(self, query: str, context: str = "") -> Dict[str, Any]:
        """
        Valida e obtém informações de faixa.
        
        Returns:
            {
                'should_play': bool,
                'track_name': str,
                'artist': str,
                'confidence': float,
                'message': str
            }
        """
        should_play, result, msg = await self.engine.validate_before_playback(query, context)
        
        return {
            'should_play': should_play,
            'track_name': result.track_name if result else '',
            'artist': result.artist if result else '',
            'confidence': result.confidence if result else 0.0,
            'message': msg,
            'full_result': result.to_dict() if result else None
        }
