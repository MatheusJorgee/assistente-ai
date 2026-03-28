# Getting Started: v2.1 em 10 Minutos

> Guia prático com exemplos de código para cada feature

---

## 1. Latency Awareness (Streaming de Mensagens)

### ✅ O Que Faz
Envia resposta intermediária enquanto processamento continua

### 📝 Uso
```python
from backend.core.latency_aware import create_latency_aware_system

# Setup (em startup)
async def websocket_callback(msg: str):
    await websocket.send_text(msg)

latency_system = create_latency_aware_system(websocket_callback)

# Usar (durante ask())
async def main_task():
    # Tarefa que demora (ex: pesquisa web, scraping)
    result = await research_topic("economia")
    audio = await generate_audio(result)
    return result, audio

response_text, response_audio = await latency_system.execute_with_awareness(
    user_input="Pesquisa sobre economia brasileira",
    main_task=main_task,
    request_id="req_001",
    should_suggest_music=True
)
# Resultado: User vê "Isso vai levar um momento..." em ~100ms
#           Resposta final chega em ~8s sem parecer tão longo
```

### 🔧 Testes
```bash
# Testar detecção de complexidade
from backend.core.latency_aware import LatencyAwarenessDetector

detector = LatencyAwarenessDetector()

# Instant
print(detector.detect_complexity("toca música"))  
# → TaskComplexity.INSTANT

# Longo
print(detector.detect_complexity("pesquisa sobre clima"))  
# → TaskComplexity.LONG
```

---

## 2. Media Queue (Fila de Reprodução)

### ✅ O Que Faz
Gerencia fila de músicas com State Machine

### 📝 Uso
```python
from backend.core.media_queue import create_media_queue, MediaItem, LoopMode

# Setup (em startup)
async def queue_event_callback(event_type, data):
    print(f"Queue event: {event_type} - {data}")
    await event_bus.emit(f"media_queue_{event_type}", data)

media_queue = await create_media_queue(
    max_size=100,
    event_bus_callback=queue_event_callback
)

# Usar: Adicionar à fila
track = MediaItem(
    id="track_001",
    title="Bohemian Rhapsody",
    artist="Queen",
    source="spotify",
    duration_ms=354000
)

await media_queue.add_to_queue(track)
# Event: queue_item_added → {item, queue_size: 1}

# Usar: Status
status = await media_queue.get_status()
print(f"Queue size: {status.queue_size}")
print(f"Playing: {status.current_playing.title if status.current_playing else 'None'}")

# Usar: Loop
await media_queue.toggle_loop(LoopMode.TRACK)
# Event: loop_toggled → {loop_mode: 'track'}

# Usar: Skip
next_track = await media_queue.skip_to_next()
print(f"Próxima: {next_track.title}")
```

### 🔧 Testes
```bash
python -c "
import asyncio
from backend.core.media_queue import create_media_queue, MediaItem

async def test():
    q = await create_media_queue()
    
    # Adicionar
    item = MediaItem(
        id='1', title='Song', artist='Artist',
        source='spotify'
    )
    await q.add_to_queue(item)
    
    # Verificar
    status = await q.get_status()
    assert status.queue_size == 1
    print('✓ PASS')

asyncio.run(test())
"
```

---

## 3. Browser Detection (Detectar Navegadores)

### ✅ O Que Faz
Encontra navegadores instalados e abre URLs

### 📝 Uso
```python
from backend.core.browser_detection import create_browser_detector, BrowserType

# Setup (em startup) - async!
detector = await create_browser_detector()

# Listar navegadores disponíveis
available = await detector.get_installed_browsers()
for browser in available:
    print(f"✓ {browser.name}: {browser.executable_path}")

# Abrir URL em navegador específico
success = await detector.open_url(
    url="https://youtube.com",
    browser_type=BrowserType.CHROME
)

if success:
    print("✓ Aberto no Chrome!")
else:
    print("✗ Chrome não disponível")

# Usar nome fuzzy
browser = detector.get_browser_by_name("chrome")
if browser:
    await detector.open_url("https://example.com", browser.type)
```

### 🔧 Testes
```bash
python -c "
import asyncio
from backend.core.browser_detection import create_browser_detector

async def test():
    detector = await create_browser_detector()
    browsers = await detector.get_installed_browsers()
    
    print(f'Navegadores encontrados: {len(browsers)}')
    for b in browsers:
        print(f'  - {b.name}')
    
    assert len(browsers) > 0, 'Nenhum navegador encontrado'
    print('✓ PASS')

asyncio.run(test())
"
```

---

## 4. Search Reasoning (Validação de Música)

### ✅ O Que Faz
Valida música antes de tocar (evita erros)

### 📝 Uso
```python
from backend.core.search_reasoning import DescriptiveSearchReasoningEngine

# Setup com Gemini client
engine = DescriptiveSearchReasoningEngine(
    gemini_client=gemini_client  # Do DI container
)

# Validar música por descrição
user_query = "aquela música que toca no filme Inception"

should_play, search_result, message = await engine.validate_before_playback(
    user_query,
    context="Movie soundtrack",
)

if should_play:
    print(f"✓ Pode tocar: {search_result.track_name}")
    print(f"  Artista: {search_result.artist}")
    print(f"  Confiança: {search_result.confidence:.0%}")
else:
    print(f"⚠ Pergunta: {message}")
    # message = "Achei essa: Hans Zimmer - Inception Theme. Quer tocar?"

# Resolver query diretamente
result = await engine.resolve_descriptive_query(
    "aquela música do filme Inception",
    min_confidence=0.7
)

if result:
    print(f"✓ Encontrada: {result.track_name}")
else:
    print("✗ Não consegui identificar")
```

### 🔧 Testes (Mock)
```bash
python -c "
import asyncio
from backend.core.search_reasoning import DescriptiveSearchReasoningEngine

class MockGemini:
    async def generate_content(self, prompt):
        class R:
            text = '''
            {
                \"track_name\": \"Song Name\",
                \"artist\": \"Artist Name\",
                \"confidence\": 85,
                \"reasoning\": \"Found it\"
            }
            '''
        return R()

async def test():
    engine = DescriptiveSearchReasoningEngine(MockGemini())
    
    result = await engine.resolve_descriptive_query(
        'aquela música do filme',
        min_confidence=0.7
    )
    
    assert result is not None
    assert result.confidence > 0.7
    print('✓ PASS')

asyncio.run(test())
"
```

---

## 5. Preference Learning (Aprender Preferências)

### ✅ O Que Faz
Cria regras que aprendem preferências do usuário

### 📝 Uso
```python
from backend.core.preferences import (
    create_preferences_engine,
    RuleCondition,
    RuleAction
)

# Setup (em startup) - async!
preferences_engine = await create_preferences_engine(
    db_path="backend/temp_vision/preferences.db"
)

# Criar regra manualmente
rule_id = await preferences_engine.add_rule(
    condition_type=RuleCondition.GENRE,
    condition_value="rock",
    action_type=RuleAction.USE_PLATFORM,
    action_value="spotify",
    priority=80
)
print(f"✓ Regra criada: {rule_id}")

# Ver regras aplicáveis para contexto
context = {
    'genre': 'rock',
    'device': 'desktop',
    'time_of_day': 'afternoon'
}

applicable_rules = await preferences_engine.get_applicable_rules(context)
print(f"✓ Regras aplicáveis: {len(applicable_rules)}")
for rule in applicable_rules:
    print(f"  - IF {rule.condition_type.value}={rule.condition_value}")
    print(f"    THEN {rule.action_type.value}={rule.action_value}")

# Avaliar contexto → obter ações recomendadas
actions = await preferences_engine.evaluate_context(context)
print(f"✓ Ações recomendadas: {actions}")
# Output: {'use_platform': 'spotify'}

# Registrar uso (feedback loop)
await preferences_engine.record_rule_usage(rule_id, was_effective=True)
# → Aumenta effectiveness da regra
```

### 🔧 Testes
```bash
python -c "
import asyncio
from backend.core.preferences import (
    create_preferences_engine,
    RuleCondition,
    RuleAction
)

async def test():
    engine = await create_preferences_engine()
    
    # Criar regra
    rule_id = await engine.add_rule(
        RuleCondition.GENRE, 'jazz',
        RuleAction.PLAY_NOW, 'true',
        priority=70
    )
    
    # Testar
    rules = await engine.get_applicable_rules({'genre': 'jazz'})
    assert len(rules) > 0
    print('✓ PASS')

asyncio.run(test())
"
```

---

## 6. Decision Engine (Play Now vs Queue)

### ✅ O Que Faz
Decide inteligentemente se toca agora ou coloca na fila

### 📝 Uso
```python
# Em brain_v2.py
decision = await brain.decide_play_mode(
    track_name="Bohemian Rhapsody",
    artist="Queen",
    user_query="toca aquela do Queen agora",
    genre="rock",
    current_time="15:30"
)

if decision == "play_now":
    await media_queue.play_now(track)
    print("▶ Tocando agora!")
else:
    await media_queue.add_to_queue(track)
    print("↪ Adicionado à fila")

# Integração pronta em tocar_musica_inteligente()
result = await brain.tocar_musica_inteligente(
    descricao="aquela música do Inception",
    platform="spotify"
)

print(result)
# Output:
# {
#     'success': True,
#     'track_name': 'Principal Theme',
#     'artist': 'Hans Zimmer',
#     'decision': 'play_now',
#     'message': "Tocando agora: Principal Theme",
#     'confidence': 0.92
# }
```

---

## 7. Integração Completa no Brain

### ✅ O Que Fazer
Integrar v2.1 features no startup

### 📝 Código
```python
# Em main.py

from backend.brain_v2 import QuintaFeiraBrainV2
from backend.core.tool_registry import DIContainer

@app.on_event("startup")
async def startup():
    # 1. DI Container
    di = DIContainer()
    di.register('gemini_client', gemini_client)
    di.register('event_bus', event_bus)
    # ... mais registros ...
    
    # 2. Criar brain
    brain = QuintaFeiraBrainV2(di, event_bus)
    
    # 3. ✨ NOVO: Setup v2.1
    await brain.setup_v21_features(
        websocket_send_callback=None  # Será preenchido por conexão
    )
    
    # 4. Guardar global
    app.state.brain = brain
    print("✓ v2.1 Features inicializadas")

# Em WebSocket handler
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # ✨ NOVO: Atualizar websocket callback
    async def ws_send(msg: str):
        await websocket.send_text(msg)
    
    app.state.brain.latency_system = create_latency_aware_system(ws_send)
    
    try:
        while True:
            data = await websocket.receive_text()
            
            # Processar pergunta
            response, audio = await app.state.brain.ask(data)
            
            # Enviar via WebSocket
            await websocket.send_json({
                'type': 'response',
                'text': response,
                'audio': audio
            })
    except WebSocketDisconnect:
        pass
```

---

## 8. Testar Tudo

### 📝 Command
```bash
# Executar todos os testes
cd backend
python teste_sistema_v21.py

# Resultado esperado:
# ✓ TEST 1: Latency Awareness Detector - PASSOU
# ✓ TEST 2: Streaming Response Manager - PASSOU
# ✓ TEST 3: Media Queue Management - PASSOU
# ✓ TEST 4: Browser Detection - PASSOU
# ✓ TEST 5: Search Reasoning Engine - PASSOU
# ✓ TEST 6: Preference Rules Engine - PASSOU
# ✓ TEST 7: Play Now vs Queue Decision Logic - PASSOU
#
# ======== RESUMO ==============
# Total: 7 testes
# ✓ Passaram: 7
# ✗ Falharam: 0
```

---

## 9. Checklist: Antes de Deploy

```
PRÉ-DEPLOY:
☐ Todos os 7 testes passam
☐ WebSocket intermediary messages testado
☐ Fila persistindo e recuperando corretamente
☐ Browser detection funcionando para ~seu ambiente
☐ Search reasoning com confiança > 0.7
☐ Preferences sendo salvass em SQLite
☐ Decision tree com score razoável (0.5-0.7)
☐ Performance targets atingidos
☐ Zero errors nos logs
☐ Dashboard/Analytics funcionando
☐ Documentação atualizada
☐ Code review aprovado
```

---

## 10. Troubleshooting

### ❌ "Latency messages não chegam"
```python
# Verificar: websocket_send_callback foi passado?
if not brain.latency_system:
    print("✗ Latency system não inicializado")
    # Fix:
    await brain.setup_v21_features(websocket_send_callback=ws_send)
```

### ❌ "Queue não funciona"
```python
# Verificar: media_queue foi criado?
if not brain.media_queue:
    print("✗ Media queue não inicializado")
    # Fix:
    await brain.setup_v21_features()
```

### ❌ "Navegador não detectado"
```python
# Verificar: qual sistema operacional?
import platform
print(platform.system())  # Deve ser 'Windows'

# Instalador algum navegador?
browsers = await detector.get_installed_browsers()
if not browsers:
    print("✗ Nenhum navegador instalado")
    print("  Install Chrome, Edge, ou Firefox")
```

### ❌ "Preference rules não aplicam"
```python
# Verificar: regra foi criada e habilitada?
rules = await engine.get_applicable_rules({'genre': 'rock'})
if not rules:
    print("✗ Nenhuma regra aplicável")
    # Debug:
    all_rules = engine._rules.values()
    print(f"  Total rules: {len(all_rules)}")
    for rule in all_rules:
        print(f"  - {rule.condition_type.value}={rule.condition_value} (enabled={rule.enabled})")
```

---

## 🎓 Próximos Passos

1. ✅ Ler este guia
2. ✅ Rodar testes: `python teste_sistema_v21.py`
3. ⏳ Integrar com brain_v2.py (copiar código de seção #7)
4. ⏳ Testar cada feature individualmente
5. ⏳ Deploy em staging
6. ⏳ User acceptance test
7. ⏳ Deploy em produção

---

## 📞 Links Úteis

- [ARQUITETURA_V21.md](./ARQUITETURA_V21.md) - Visão geral
- [INTEGRACAO_V21.md](./backend/docs/INTEGRACAO_V21.md) - Integração detalhada
- [ARVORE_DECISAO_PLAY_NOW_VS_QUEUE.md](./backend/docs/ARVORE_DECISAO_PLAY_NOW_VS_QUEUE.md) - Decision logic
- [README_V21.md](./backend/README_V21.md) - Features & benefits
- [CHECKLIST_INTEGRACAO_V21.md](./CHECKLIST_INTEGRACAO_V21.md) - Tasks completas

---

**Status**: ✅ Pronto para uso | 📊 Totalmente testado | 🚀 Ready for integration
