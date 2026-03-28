# Checklist de Integração v2.1 → Brain v2.0

## STATUS ATUAL
- ✅ **v2.0 (Base)**: Completo, em produção
- ✅ **v2.1 (Novos módulos)**: Completo, testado
- ⏳ **Integração**: TODO - deve ser feito

---

## FASES DE INTEGRAÇÃO

### FASE 1: Latency Awareness (Estimado: 2-3 horas)

**Objetivo**: Fazer brain.ask() enviar intermediate messages durante tarefas longas

**Tarefas**:
- [ ] Importar `create_latency_aware_system` em `brain_v2.py`
- [ ] Adicionar `self.latency_system` à classe QuintaFeiraBrainV2
- [ ] Atualizar método `setup_v21_features()` em brain_v2.py
  - [ ] Chamar `create_latency_aware_system(websocket_send_callback)`
  - [ ] Armazenar em `self.latency_system`
- [ ] Modificar `ask()` method:
  ```python
  # ANTES:
  async def ask(self, question, visual_context=""):
      response = await self._process_question(question, visual_context)
      audio = await self._generate_audio(response)
      return response, audio
  
  # DEPOIS:
  async def ask(self, question, visual_context=""):
      async def main_task():
          response = await self._process_question(question, visual_context)
          audio = await self._generate_audio(response)
          return response, audio
      
      response, audio = await self.latency_system.execute_with_awareness(
          user_input=question,
          main_task=main_task,
          should_suggest_music=True
      )
      return response, audio
  ```
- [ ] Testar com `python backend/teste_sistema_v21.py` (TEST 1-2)
- [ ] Verificar no frontend que intermediate messages chegam via WebSocket

---

### FASE 2: Media Queue Integration (Estimado: 3-4 horas)

**Objetivo**: Conectar fila de mídia com media_tools.py

**Tarefas**:
- [ ] Importar módulos em `brain_v2.py`:
  ```python
  from backend.core.media_queue import create_media_queue, MediaItem
  from backend.core.search_reasoning import SearchValidationTool
  ```
- [ ] Adicionar ao setup_v21_features():
  ```python
  # Event callback para media queue
  async def queue_event(event_type, data):
      await self.event_bus.emit(f"media_queue_{event_type}", data)
  
  self.media_queue = await create_media_queue(
      max_size=100,
      event_bus_callback=queue_event
  )
  ```
- [ ] Implementar método `decide_play_mode()` em brain_v2.py
  - [ ] Analisar sinais de linguagem natural
  - [ ] Consultar preferências
  - [ ] Analisar estado da fila
  - [ ] Retornar decisão com score
- [ ] Modificar `TocarMusicaSpotifyTool` em tools/media_tools.py:
  ```python
  # NOVO: usar brain.decide_play_mode()
  decision = await self.brain.decide_play_mode(
      track_name=track_name,
      artist=artist,
      user_query=query,
      genre=genre
  )
  
  if decision == "play_now":
      await self.brain.media_queue.play_now(media_item)
  else:
      await self.brain.media_queue.add_to_queue(media_item)
  ```
- [ ] Criar tools de fila:
  - [ ] AdicionarAFilaTool
  - [ ] AlternarLoopTool
  - [ ] ObterStatusFilaTool
- [ ] Testar com `python backend/teste_sistema_v21.py` (TEST 3, 7)
- [ ] Verificar persistência de fila: `backend/temp_vision/preferences.db`

---

### FASE 3: Browser Detection (Estimado: 1-2 horas)

**Objetivo**: Integrar detecção de navegadores com OSAutomation

**Tarefas**:
- [ ] Importar em `automation.py`:
  ```python
  from backend.core.browser_detection import create_browser_detector
  ```
- [ ] Adicionar `BrowserDetector` à classe OSAutomation
- [ ] Modificar `AbrirURLTool` em tools/terminal_tools.py:
  ```python
  # NOVO: extrair browser preference do query
  browser = self._extract_browser_preference(query)  # "chrome", "edge", etc
  
  success = await self.browser_detector.open_url(url, browser)
  ```
- [ ] Criar método helper `_extract_browser_preference()`:
  ```python
  def _extract_browser_preference(query: str) -> str:
      if "chrome" in query.lower():
          return "chrome"
      elif "edge" in query.lower():
          return "edge"
      # ... etc
      return "default"
  ```
- [ ] Testar com `python backend/teste_sistema_v21.py` (TEST 4)
- [ ] Validar com: "Abre no Chrome", "Usa o Edge"

---

### FASE 4: Search Reasoning (Estimado: 2-3 horas)

**Objetivo**: Validar música antes de tocar

**Tarefas**:
- [ ] Importar em `brain_v2.py`:
  ```python
  from backend.core.search_reasoning import DescriptiveSearchReasoningEngine
  ```
- [ ] Setup em `setup_v21_features()`:
  ```python
  self.search_engine = DescriptiveSearchReasoningEngine(
      gemini_client=self.di_container.get('gemini_client'),
      event_bus_callback=async_event_callback
  )
  ```
- [ ] Criar novo método `tocar_musica_inteligente()`:
  ```python
  async def tocar_musica_inteligente(self, descricao: str, platform: str = "spotify"):
      # 1. Validar com search reasoning
      should_play, result, msg = await self.search_engine.validate_before_playback(...)
      
      # 2. Decidir play_now vs queue
      decision = await self.decide_play_mode(...)
      
      # 3. Reproduzir com contexto
      if decision == "play_now":
          await self.media_queue.play_now(media_item)
      else:
          await self.media_queue.add_to_queue(media_item)
      
      return result
  ```
- [ ] Modificar `TocarMusicaSpotifyTool`:
  ```python
  # NOVO: chamar tocar_musica_inteligente em vez de tocar direto
  result = await self.brain.tocar_musica_inteligente(track_name, "spotify")
  ```
- [ ] Testar com `python backend/teste_sistema_v21.py` (TEST 5)
- [ ] Validar com: "aquela musica do Inception"

---

### FASE 5: Preference Learning (Estimado: 2-3 horas)

**Objetivo**: Aprender preferências e aplicar automaticamente

**Tarefas**:
- [ ] Importar em `brain_v2.py`:
  ```python
  from backend.core.preferences import (
      create_preferences_engine, 
      RuleCondition, 
      RuleAction
  )
  ```
- [ ] Setup em `setup_v21_features()`:
  ```python
  self.preferences_engine = await create_preferences_engine(
      db_path="backend/temp_vision/preferences.db",
      event_bus_callback=async_event_callback
  )
  ```
- [ ] Implementar `learn_user_preference()`:
  ```python
  async def learn_user_preference(self, query, action_taken, user_satisfied=True):
      # Extrair padrão (ex: genre=rock)
      # Criar regra automaticamente
      rule_id = await self.preferences_engine.add_rule(...)
      return rule_id
  ```
- [ ] Modificar `decide_play_mode()` para usar preferências:
  ```python
  # Em decide_play_mode()
  context = {
      'genre': genre.lower(),
      'device': 'desktop',
      'time_of_day': self._get_time_period(),
      'context': self._detect_context(question)  # work, relax, etc
  }
  
  applicable_rules = await self.preferences_engine.get_applicable_rules(context)
  pref_score = self._calculate_rule_score(applicable_rules)
  ```
- [ ] Adicionar feedback loop após decision:
  ```python
  # Registrar se regra foi efetiva
  await self.preferences_engine.record_rule_usage(rule_id, was_effective=True)
  ```
- [ ] Testar com `python backend/teste_sistema_v21.py` (TEST 6, 7)
- [ ] Validar persistência: `SQLite preferences.db`

---

### FASE 6: Frontend Updates (Estimado: 3-4 horas)

**Objetivo**: Mostrar queue, intermediate messages, browser selection

**Tarefas**:
- [ ] Atualizar `frontend/app/page-v2.tsx`:
  - [ ] Queue visualization section (próximas 5 faixas)
  - [ ] Intermediate message indicator ("⏳ Pesquisando...")
  - [ ] Loop toggle button
  - [ ] Browser selector dropdown
- [ ] Adicionar WebSocket handlers para:
  ```
  msg.type = "intermediate" 
    ├─ step: "thinking", "searching", "fetching"
    ├─ text: "Isso vai levar um momento..."
    └─ suggestion: "play_background_music"
  
  msg.type = "queue_updated"
    ├─ queue: [...MediaItems]
    ├─ current_playing: MediaItem
    └─ queue_size: int
  ```
- [ ] Display real-time queue updates
  - [ ] Add fade-in for new items
  - [ ] Remove old items with animation
- [ ] Browser selector:
  ```html
  <select onChange={handleBrowserChange}>
    <option>System Default</option>
    <option>Chrome</option>
    <option>Edge</option>
    <option>Brave</option>
  </select>
  ```
- [ ] Tornar page-v2.tsx production-ready:
  - [ ] Renomear para `page.tsx`
  - [ ] Backup do página.tsx antigo
- [ ] Testar conexão WebSocket end-to-end

---

### FASE 7: Documentation & Cleanup (Estimado: 1-2 horas)

**Tarefas**:
- [ ] Atualizar `README.md` principal com v2.1 highlights
- [ ] Adicionar exemplos de uso em docstrings
- [ ] Criar `MIGRATION_V20_TO_V21.md` (como atualizar)
- [ ] Adicionar logging detalhado:
  - [ ] `logger.info(f"Decision: {final_score} → {decision}")`
  - [ ] `await event_bus.emit('decision_tree_log', {...})`
- [ ] Cleanup de teste files:
  - [ ] Removido arquivos de teste temporários
  - [ ] Validar suite completo passa
- [ ] Performance profiling:
  - [ ] Latency de intermediate messages
  - [ ] Overhead de queue operations
  - [ ] Memory usage com 100 items na fila

---

## ORDEM RECOMENDADA

```
1. ✅ Modules criados (latency_aware.py, media_queue.py, etc)
2. ⏳ FASE 1: Latency Awareness
3. ⏳ FASE 2: Media Queue
4. ⏳ FASE 3: Browser Detection
5. ⏳ FASE 4: Search Reasoning
6. ⏳ FASE 5: Preference Learning
7. ⏳ FASE 6: Frontend
8. ⏳ FASE 7: Documentation
```

Tempo total estimado: **15-20 horas de desenvolvimento**

---

## TESTES APÓS CADA FASE

Após cada fase, executar:

```bash
# Testar módulos
python backend/teste_sistema_v21.py

# Testar integração com brain
python backend/teste_brain_v21_integration.py  # TODO: criar

# Testar via API
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Toca rock agora", "visual_context": ""}'

# Verificar WebSocket messages
# No frontend, abrir Console e monitorar ws messages
```

---

## ROLLBACK PLAN

Se algo quebrar, rollback é fácil:

```bash
# Desabilitar v2.1 features (manter v2.0 funcionando)
# Em main.py:
try:
    await brain.setup_v21_features()
except Exception as e:
    print(f"v2.1 init failed: {e}. Continuando com v2.0")
    # Sistema continua funcionando apenas com v2.0
```

---

## VALIDAÇÃO FINAL

Checklist de produção:

- [ ] Todos os 7 testes em `teste_sistema_v21.py` passam
- [ ] Sem errors em logs
- [ ] WebSocket messages sendo entregues
- [ ] Queue persistindo corretamente
- [ ] Preferências sendo salvas em SQLite
- [ ] Decision tree com >90% confidence rate
- [ ] Performance:
  - [ ] Intermediate message latency < 200ms
  - [ ] Queue operations < 50ms
  - [ ] Browser detection < 500ms (first time)
- [ ] UX test com usuário real
- [ ] Code review de todos os módulos

---

## ESTIMATIVA DE TEMPO

| Fase | Tempo | Status |
|------|-------|--------|
| 1. Latency | 2-3h | ⏳ TODO |
| 2. Queue | 3-4h | ⏳ TODO |
| 3. Browser | 1-2h | ⏳ TODO |
| 4. Search | 2-3h | ⏳ TODO |
| 5. Preferences | 2-3h | ⏳ TODO |
| 6. Frontend | 3-4h | ⏳ TODO |
| 7. Docs | 1-2h | ⏳ TODO |
| **TOTAL** | **15-20h** | ⏳ TODO |

---

## PRÓXIMO PASSO

**Ação imediata**: Começar FASE 1 (Latency Awareness em brain_v2.py)

**Responsável**: [Person/Team]

**Prazo sugerido**: [Data]

---

Documentado em: 2024
v2.1 Planning & Integration Checklist
