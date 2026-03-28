# Árvore de Decisão: "Tocar Agora" vs "Adicionar à Fila"

## Visão Geral

O sistema Quinta-Feira utiliza Context-Aware Reasoning para decidir se deve reproduzir uma música imediatamente ("Play Now") ou adicionar à fila de reprodução ("Add to Queue"). A decisão é baseada em:

1. **Estado Atual** - O que está tocando agora?
2. **Contexto Conversacional** - O que o usuário quer?
3. **Preferências Aprendidas** - Histórico de decisões do usuário
4. **Sinais Temporais** - Padrões de uso por hora/dia

---

## Matriz de Decisão

### Nível 1: Estado Atual da Mídia

```
┌─ Nada tocando (IDLE)
│  └─ Prioridade: ALTA - reproduzir imediatamente
│     └─ Decision: PLAY NOW ✓
│
├─ Música tocando (PLAYING)
│  ├─ (A) Usuário explicitamente pede "toca agora" ou "play now"
│  │  └─ Decision: PLAY NOW (substituir) ✓
│  │
│  ├─ (B) Usuário pede "coloca aquela" sem urgência
│  │  └─ Decision: ADD TO QUEUE ↓
│  │
│  ├─ (C) Loop ativo (LOOP_ACTIVE)
│  │  └─ Decision: ADD TO QUEUE (após fila) ↓
│  │
│  └─ (D) Fila vazia vs Fila com itens
│     ├─ Fila vazia: Decision: PLAY NOW ✓
│     └─ Fila com itens: Decision: ADD TO QUEUE ↓
│
└─ Pausada/Queued
   └─ Decision: PLAY NOW ✓
```

### Nível 2: Sinais Conversacionais (Natural Language)

```
PLAY NOW (Imediato):
├─ "Toca [música]" (verbo "tocar" modo imperativo)
├─ "Play [música]" (English)
├─ "Coloca agora" (urgência: "agora")
├─ "Começa com..." (urgência: "começa")
├─ "Muda para..." (mudança = substituir)
├─ "Reproduz..." (modo imperativo)
└─ "[Música] agora" (temporal: "agora")

ADD TO QUEUE (Fila):
├─ "Coloca [música] na fila"
├─ "Adiciona [música]"
├─ "Próxima: [música]"
├─ "Depois [música]"
├─ "Salva [música] pra depois"
├─ "Coloca aquela" (sem urgência temporal)
└─ "Quer colocar [música]?" (sugestão/pergunta)
```

### Nível 3: Preferências Aprendidas

```
PreferenceRulesEngine avalia:

├─ Gênero (genre)
│  └─ Ex: "rock" → "always play_now"
│
├─ Artista (artist)
│  └─ Ex: "Beatles" → "add to queue"
│
├─ Hora do Dia (time_of_day)
│  ├─ morning (5-11h) → ADD TO QUEUE (ambient)
│  ├─ afternoon (11-17h) → PLAY NOW (energetic)
│  ├─ evening (17-21h) → CONTEXT dependent
│  └─ night (21-5h) → ADD TO QUEUE (sleep mode)
│
├─ Contexto (context)
│  ├─ "work" → ADD TO QUEUE (não interromper)
│  ├─ "workout" → PLAY NOW (motivação imediata)
│  ├─ "dinner" → ADD TO QUEUE (ambiente contínuo)
│  └─ "focus" → ADD TO QUEUE (não mudar bruscamente)
│
└─ Dispositivo (device)
   ├─ "desktop" → PLAY NOW
   ├─ "car" → ADD TO QUEUE (segurança)
   └─ "phone" → CONTEXT dependent
```

### Nível 4: Tamanho e Aplicabilidade da Fila

```
Queue Size (após regras de preferência):

├─ Queue = 0 (vazia)
│  └─ Decision: PLAY NOW ✓
│
├─ Queue = 1-2 (pequena)
│  ├─ Se usuário em contexto "focus" → ADD TO QUEUE
│  └─ Senão → PLAY NOW (fila curta, pode mudar)
│
├─ Queue = 3-5 (normal)
│  └─ Decision: ADD TO QUEUE ↓
│
└─ Queue > 5 (longa)
   └─ Decision: ADD TO QUEUE (e avisar: "Seu número na fila: #7")
```

---

## Fluxo Completo de Decisão

```
User Input: "Toca aquela música do filme X"
                    ↓
         [Latency Awareness]
         "Isso vai levar um momento..."
                    ↓
    [Parse Natural Language]
    Detectar: verbo="toca", tipo="descrição"
                    ↓
    [Search Reasoning]
    Google Search + Gemini → track_name, artist, confidence=0.85
                    ↓
    [Check Current State]
    current_state = PLAYING, queue_size = 2
                    ↓
    [Language Signals]
    "toca" + "aquela" → Sinais conflitantes
    - "toca" = play now urgente
    - "aquela" = não é urgente
    Result: Sinais mistos (score: 0.5)
                    ↓
    [Check Preferences]
    Rules applied:
    - genre=movie_score → prefer PLAY_NOW (80% priority)
    - time_of_day=evening → neutral
    - device=desktop → prefer PLAY_NOW (70% priority)
    Weighted score: 0.65 → PLAY NOW mais provável
                    ↓
    [Queue State Analysis]
    queue_size = 2 (pequena)
    → Tipping point: PLAY NOW é aceitável
                    ↓
    [Final Decision Logic]
    Confidence Score:
    ├─ Language signals: 0.5
    ├─ Preferences: 0.65
    ├─ Queue state: 0.7
    └─ Current state: 0.6
    
    Average = 0.6125 > 0.55 threshold
    
    ✓ FINAL DECISION: PLAY NOW
                    ↓
    [Output to User]
    "Trocando agora! Que legal essa soundtrack."
    [Play track with transition]
```

---

## Código: Implementação da Decisão

### Em `brain_v2.py`:

```python
async def decide_play_mode(
    self,
    track_name: str,
    user_query: str,
    context: Dict[str, str]
) -> str:  # "play_now" ou "add_to_queue"
    """
    Decide entre PLAY_NOW e ADD_TO_QUEUE.
    
    Args:
        track_name: Nome da faixa
        user_query: Input original do usuário
        context: {genre, time_of_day, device, artist, etc}
    
    Returns:
        "play_now" ou "add_to_queue"
    """
    
    # 1. Analisar sinais de linguagem natural
    language_score = self._analyze_language_signals(user_query)
    # Retorna 0-1: 0 = "queue it", 1 = "play now"
    
    # 2. Verificar preferências aprendidas
    applicable_rules = await self.preferences_engine.get_applicable_rules(context)
    pref_score = self._calculate_preference_score(applicable_rules)
    
    # 3. Analisar estado da fila
    queue_status = await self.media_queue.get_status()
    queue_score = self._calculate_queue_score(queue_status)
    
    # 4. Analisar estado atual
    state_score = self._calculate_state_score(queue_status.current_state)
    
    # 5. Calcular score final (weighted average)
    weights = {
        'language': 0.30,
        'preferences': 0.35,
        'queue': 0.20,
        'state': 0.15
    }
    
    final_score = (
        language_score * 0.30 +
        pref_score * 0.35 +
        queue_score * 0.20 +
        state_score * 0.15
    )
    
    # 6. Emitir evento para logging
    await self.event_bus.emit('cortex_thinking', {
        'decision': 'play_mode',
        'language_score': language_score,
        'pref_score': pref_score,
        'queue_score': queue_score,
        'state_score': state_score,
        'final_score': final_score
    })
    
    # 7. Retornar decisão (threshold = 0.55)
    threshold = 0.55
    
    if final_score >= threshold:
        return "play_now"
    else:
        return "add_to_queue"


def _analyze_language_signals(self, query: str) -> float:
    """
    Analisa sinais de linguagem natural para urgência/imediatismo.
    
    Score: 0 (queue definitely), 1 (play now definitely)
    """
    query_lower = query.lower()
    
    play_now_keywords = ['toca', 'play', 'agora', 'já', 'começa', 'muda', 'reproduz']
    add_to_queue_keywords = ['coloca', 'adiciona', 'próxima', 'depois', 'salva', 'fila']
    
    # Contar keywords
    play_count = sum(1 for kw in play_now_keywords if kw in query_lower)
    queue_count = sum(1 for kw in add_to_queue_keywords if kw in query_lower)
    
    # Score: balancear contagens
    if play_count == 0 and queue_count == 0:
        return 0.5  # Neutro
    
    total = play_count + queue_count
    return play_count / total if total > 0 else 0.5


def _calculate_preference_score(self, rules: List[PreferenceRule]) -> float:
    """
    Gera score de preferências aprendidas.
    
    Maior priority + effectiveness = score mayor
    """
    if not rules:
        return 0.5  # Sem regras: neutro
    
    # Usar a regra com maior prioridade
    best_rule = max(rules, key=lambda r: r.priority * r.effectiveness)
    
    # Mapear ações para scores
    action_scores = {
        'play_now': 1.0,
        'add_to_queue': 0.0,
        'neutral': 0.5
    }
    
    action_value = best_rule.action_value.lower()
    base_score = action_scores.get(action_value, 0.5)
    
    # Ponderar por priority (0-100 → 0-0.4)
    priority_boost = (best_rule.priority / 100) * 0.4
    
    return min(1.0, base_score + priority_boost)


def _calculate_queue_score(self, queue_status) -> float:
    """
    Score baseado no estado da fila.
    
    Fila vazia → play now (1.0)
    Fila grande → add to queue (0.0)
    """
    queue_size = queue_status.queue_size
    
    if queue_size == 0:
        return 1.0  # Fila vazia = PLAY NOW
    elif queue_size < 3:
        return 0.6  # Fila pequena = inclinação para PLAY NOW
    elif queue_size < 6:
        return 0.4  # Fila normal = inclinação para QUEUE
    else:
        return 0.1  # Fila grande = QUEUE definitivamente
```

---

## Teste das Decisões

### Cenários Validados:

```gherkin
CENÁRIO 1: Nada tocando
QUANDO: usuário diz "Toca rock"
E: queue está vazia
E: horário é 15h (afternoon)
ENTÃO: Decision = PLAY NOW ✓

CENÁRIO 2: Música tocando, urgência clara
QUANDO: usuário diz "Toca agora Bohemian Rhapsody"
E: queue tem 2 itens
E: linguagem explicita: "toca agora"
ENTÃO: Decision = PLAY NOW ✓

CENÁRIO 3: Sugestão de música
QUANDO: usuário diz "coloca anotação de amor na fila"
E: queue tem 4 itens
E: preferência: trabalho = add_to_queue
ENTÃO: Decision = ADD TO QUEUE ✓

CENÁRIO 4: Contexto de trabalho
QUANDO: usuário diz "toca essa"
E: context = "work"
E: horário = 9h
E: rule: work→add_to_queue (priority=90)
ENTÃO: Decision = ADD TO QUEUE ✓
       (regra sobrescreve linguagem)

CENÁRIO 5: Descrição vaga + movie context
QUANDO: usuário diz "toca a música do filme Inception"
E: search_reasoning confidence = 0.92
E: genre = "soundtrack"
E: pref: soundtrack→play_now (priority=70)
ENTÃO: Decision = PLAY NOW ✓
       (alta confiança + preferência)

CENÁRIO 6: Fila cheia, colocação
QUANDO: usuário diz "salva essa pra depois"
E: queue_size = 12 (máximo)
E: contexto = "focus"
ENTÃO: Decision = ADD TO QUEUE ✓
       Output: "Sua fila tá cheia! Salvei na posição #13 para depois."
```

---

## Otimizações de Performance

### Caching de Decisões:

```python
decision_cache = {}  # {user_query_hash: (decision, timestamp, confidence)}
cache_ttl = 300  # 5 minutos

# Ao decidir, registrar em cache
# Se mesma query dentro de 5min, reusar decisão
```

### Batch Processing:

```python
# Se queue tiver múltiplos pedidos pendentes:
# Processar em lote em vez de um por um
pending_tracks = await self.media_queue.get_pending()
for track in pending_tracks:
    # Usar resultado anterior como contexto
```

---

## Feedback Loop: Aprender com Decisões

```python
async def record_decision_feedback(
    self,
    decision: str,  # "play_now" ou "add_to_queue"
    was_user_happy: bool  # Usuário gostou?
):
    """
    Registra feedback de decisão para melhorar model.
    """
    
    # 1. Se utilizou regra, aumentar/diminuir effectiveness
    if was_user_happy:
        # Reforçar regra
        await self.preferences_engine.record_rule_usage(rule_id, True)
    else:
        # Penalizar regra
        await self.preferences_engine.record_rule_usage(rule_id, False)
    
    # 2. Emitir evento para analytics
    await self.event_bus.emit('decision_feedback', {
        'decision': decision,
        'user_satisfaction': was_user_happy,
        'timestamp': datetime.now().isoformat()
    })
```

---

## Próximos Passos

1. ✅ **Implementado**: Language signal parsing
2. ✅ **Implementado**: Preference rules engine
3. ✅ **Implementado**: Queue state analysis
4. ⏳ **TODO**: Treinar modelo com histórico de decisões (ML)
5. ⏳ **TODO**: Integrar com feedback explícito do usuário ("isso tava certo!" vs "cancelei")

---

## Links Relacionados

- [latency_aware.py](../core/latency_aware.py) - Intermediate messaging
- [media_queue.py](../core/media_queue.py) - Queue state management
- [preferences.py](../core/preferences.py) - Preference rules engine
- [brain_v2.py](../brain_v2.py) - Main orchestration
- [PADROES_ARQUITETURA.md](./PADROES_ARQUITETURA.md) - Design patterns
