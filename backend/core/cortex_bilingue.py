"""
CORTEX BILÍNGUE - V1 Restaurado com Melhorias V2

Dedução de entidades Português/Inglês a partir de transcrição falada.
O reconhecimento de fala em PT-BR do Chrome distorce títulos em inglês.

Exemplo:
  User fala: "toca the perfect pear"
  Chrome transcreve: "toca the perfeit paira"  (erro fonético)
  Córtex deduz: "the perfect pair" (título correto)
  
Arquivo: backend/core/cortex_bilingue.py
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class LanguageConfidence(Enum):
    """Nível de confiança na tradução"""
    LOW = 0.3
    MEDIUM = 0.6
    HIGH = 0.85
    VERY_HIGH = 0.95


@dataclass
class BilingualEntity:
    """Entidade detectada em um texto bilíngue"""
    original: str
    corrected: str
    confidence: float
    language: str  # 'pt', 'en', or 'mixed'
    category: str  # 'music_title', 'artist', 'movie', 'command', etc.


class CortexBilingue:
    """
    Processador de comandos bilíngues com heurísticas de dedução.
    Restaura lógica V1 + melhorias V2.
    """
    
    def __init__(self):
        self.phonetic_corrections = {
            # MÚSICA (títulos em inglês)
            'perfeit paira': 'the perfect pair',
            'the perfect pear': 'the perfect pair',
            'the perfet pear': 'the perfect pair',
            'perfeito par': 'the perfect pair',
            
            # ARTISTAS/BANDAS
            'dificlo': 'difficult',
            'dificult': 'difficult',
            'theweeknd': 'the weeknd',
            'the wicend': 'the weeknd',
            'the weekend': 'the weeknd',
            
            # FILMES/SÉRIES
            'starwors': 'star wars',
            'star wors': 'star wars',
            'esbassador': 'ambassador',
            'ambaixador': 'ambassador',
            
            # COMANDOS MISTOS
            'play geral': 'play guaraná',  # Música brasileira
            'tocandosamb': 'toca samba',
            'toca bossa noba': 'toca bossa nova',
            
            # PLATAFORMAS
            'youtoob': 'youtube',
            'spotifo': 'spotify',
            'spotifai': 'spotify',
        }
        
        # Palavras-chave que indicam busca de música/artista
        self.music_context_keywords = {
            'toca', 'play', 'coloca', 'música', 'musica', 'artista',
            'canta', 'cantor', 'banda', 'canção', 'cancao', 'som'
        }
        
        # Palavras-chave que indicam busca de filme/série
        self.movie_context_keywords = {
            'assiste', 'filme', 'serie', 'série', 'episode', 'episódio',
            'netflix', 'hbo', 'show', 'season', 'temporada'
        }
        
        # Cache de correções bem-sucedidas (aprendizado V2)
        self.successful_corrections: Dict[str, Tuple[str, float]] = {}
    
    def normalize_text(self, text: str) -> str:
        """Normaliza texto removendo acentos"""
        import unicodedata
        return ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        )
    
    def detect_language(self, text: str) -> str:
        """
        Detecta idioma dominante do texto.
        Retorna: 'pt', 'en', 'mixed'
        """
        pt_pattern = r'[àáâãäèéêëìíîïòóôõöùúûüç]'
        text_lower = text.lower()
        
        pt_chars = len(re.findall(pt_pattern, text_lower))
        words = text_lower.split()
        
        # Palavras comuns em PT
        pt_words = {'o', 'a', 'de', 'que', 'para', 'é', 'do', 'em', 'está', 'toca', 'coloca', 'pausa'}
        # Palavras comuns em EN
        en_words = {'the', 'a', 'is', 'and', 'or', 'play', 'stop', 'pause', 'skip', 'artist', 'song'}
        
        pt_found = len([w for w in words if w in pt_words])
        en_found = len([w for w in words if w in en_words])
        
        if pt_chars > 3 or pt_found >= 2:
            return 'pt'
        elif en_found >= 2:
            return 'en'
        else:
            return 'mixed'
    
    def correct_phonetic_error(self, text: str) -> Tuple[str, float]:
        """
        Aplica heurísticas de correção fonética.
        Retorna: (texto_corrigido, confiança)
        """
        text_lower = text.lower().strip()
        
        # Checar cache de sucesso
        if text_lower in self.successful_corrections:
            return self.successful_corrections[text_lower]
        
        # Procurar por padrões exatos no dicionário
        for wrong, correct in self.phonetic_corrections.items():
            if text_lower == wrong:
                confidence = LanguageConfidence.VERY_HIGH.value
                self.successful_corrections[text_lower] = (correct, confidence)
                return correct, confidence
        
        # Procurar por padrões substring (fuzzy)
        for wrong, correct in self.phonetic_corrections.items():
            if wrong in text_lower:
                # Usar similarity ratio para determinar confiança
                confidence = self._similarity_ratio(text_lower, wrong)
                if confidence > 0.8:
                    corrected = text_lower.replace(wrong, correct)
                    confidence = LanguageConfidence.MEDIUM.value
                    self.successful_corrections[text_lower] = (corrected, confidence)
                    return corrected, confidence
        
        # Sem correção
        return text_lower, 0.0
    
    def _similarity_ratio(self, s1: str, s2: str) -> float:
        """Calcula similitude entre duas strings (Levenshtein simplificado)"""
        if not s1 or not s2:
            return 0.0
        
        # Contar caracteres em comum
        common = sum(1 for c1, c2 in zip(s1, s2) if c1 == c2)
        return common / max(len(s1), len(s2))
    
    def infer_entity_category(self, text: str, context: str = "") -> str:
        """
        Deduz categoria da entidade baseado em keywords.
        Retorna: 'music', 'movie', 'command', 'unknown'
        """
        text_lower = text.lower()
        context_lower = context.lower()
        full_context = f"{text_lower} {context_lower}"
        
        # Contar palavras-chave
        music_count = len([kw for kw in self.music_context_keywords if kw in full_context])
        movie_count = len([kw for kw in self.movie_context_keywords if kw in full_context])
        
        if music_count >= 1:
            return 'music'
        elif movie_count >= 1:
            return 'movie'
        else:
            return 'command'
    
    def process_bilingual_command(
        self, 
        text: str, 
        context: str = ""
    ) -> Tuple[str, BilingualEntity]:
        """
        Processa comando bilíngue completo.
        
        Args:
            text: Texto transcrito (pode ter erros)
            context: Contexto adicional (ex: histórico, preferências)
            
        Returns:
            (texto_corrigido, entidade_BilingualEntity)
        """
        language = self.detect_language(text)
        category = self.infer_entity_category(text, context)
        
        corrected, confidence = self.correct_phonetic_error(text)
        
        entity = BilingualEntity(
            original=text,
            corrected=corrected,
            confidence=confidence,
            language=language,
            category=category
        )
        
        return corrected, entity
    
    def suggest_corrections(self, text: str) -> List[Tuple[str, float]]:
        """
        Retorna múltiplas sugestões de correção ordenadas por confiança.
        """
        suggestions = []
        text_lower = text.lower()
        
        # Procurar por padrões substring
        for wrong, correct in self.phonetic_corrections.items():
            if wrong in text_lower:
                confidence = self._similarity_ratio(text_lower, wrong)
                if confidence > 0.6:
                    corrected = text_lower.replace(wrong, correct)
                    suggestions.append((corrected, confidence))
        
        # Ordenar por confiança
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return suggestions
    
    def learn_correction(self, wrong: str, correct: str, context: str = ""):
        """
        Aprende nova correção a partir de interação bem-sucedida.
        Integra com Oráculo para aprendizado persistente.
        """
        wrong_lower = wrong.lower().strip()
        correct_lower = correct.lower().strip()
        
        # Adicionar ao dicionário
        self.phonetic_corrections[wrong_lower] = correct_lower
        
        # Persistir no cache de sucesso
        self.successful_corrections[wrong_lower] = (correct_lower, LanguageConfidence.HIGH.value)
        
        print(f"[LEARN] Nova correção: '{wrong}' → '{correct}'")


# ===== FACTORY FUNCTION =====

_cortex_instance = None

def get_cortex_bilingue() -> CortexBilingue:
    """Retorna instância singleton do Córtex Bilíngue"""
    global _cortex_instance
    if _cortex_instance is None:
        _cortex_instance = CortexBilingue()
    return _cortex_instance


# ===== EXEMPLO DE USO =====
if __name__ == "__main__":
    cortex = get_cortex_bilingue()
    
    # Teste 1: Correção simples
    print("=== TESTE 1: Correction of Perfeit Paira ===")
    corrected, entity = cortex.process_bilingual_command("toca the perfeit paira")
    print(f"Original: {entity.original}")
    print(f"Corrected: {entity.corrected}")
    print(f"Confidence: {entity.confidence:.2%}")
    print(f"Category: {entity.category}")
    print()
    
    # Teste 2: Múltiplas sugestões
    print("=== TESTE 2: Multiple Suggestions ===")
    suggestions = cortex.suggest_corrections("toca the perfeit paira")
    for corrected, conf in suggestions[:3]:
        print(f"  - {corrected} (confidence: {conf:.2%})")
    print()
    
    # Teste 3: Detecção de linguagem
    print("=== TESTE 3: Language Detection ===")
    texts = [
        "toca samba",
        "play jazz",
        "toca the weeknd"
    ]
    for t in texts:
        lang = cortex.detect_language(t)
        print(f"  '{t}' → {lang}")
