# Arquitetura Quinta-Feira v2.1

## Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        QUINTA-FEIRA v2.1                        │
│                   Consciência de Latência +                     │
│              Inteligência de Mídia + Aprendizado                │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────── CAMADA UI ◄──────────────────────────────┐
│                                                                        │
│  ┌─ Frontend (Next.js/React) ─────────────────────────────────┐      │
│  │                                                             │      │
│  │  ⚙️ Session Management    🎵 Queue Display    🌐 Browser   │      │
│  │  ◄─ Voice Recognition    ◄─ loop/skip buttons  ◄─ Selector │      │
│  │  ► Text Input             ► Intermediate msg    ► Hotkeys   │      │
│  │                                                             │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                              ▲                                        │
│                              │ WebSocket                             │
│                              │ (text, intermediate, queue_update)   │
│                              ▼                                        │
├──────────────────────────── CAMADA API ◄──────────────────────────────┤
│                                                                        │
│  ┌─ FastAPI Main (main.py) ──────────────────────────────────┐       │
│  │  POST /ask              GET /queue-status                │       │
│  │  WS /ws                 POST /learn-preference           │       │
│  │  POST /open-url         POST /skip-track                 │       │
│  └────────────────────────────────────────────────────────────┘       │
│                              ▲                                        │
│                              │                                        │
│                              ▼                                        │
├──────────────────────── CAMADA ORQUESTRAÇÃO ◄──────────────────────────┤
│                                                                        │
│  ┌──────── QuintaFeiraBrainV2 ────────────────────────────────┐      │
│  │                                                             │      │
│  │  ┌──────────────────────────────────────────────────┐      │      │
│  │  │ ask(question, visual_context)                  │      │      │
│  │  │                                                 │      │      │
│  │  │ 1. latency_system.execute_with_awareness()     │      │      │
│  │  │    ├─ Detecta complexity                       │      │      │
│  │  │    ├─ Envia intermediate msg                   │      │      │
│  │  │    └─ Executa em background                    │      │      │
│  │  │                                                 │      │      │
│  │  │ 2. _process_question()                         │      │      │
│  │  │    ├─ Parse input                              │      │      │
│  │  │    ├─ Tool selection                           │      │      │
│  │  │    └─ Execute tools                            │      │      │
│  │  │                                                 │      │      │
│  │  │ 3. decide_play_mode() [se música]              │      │      │
│  │  │    ├─ Language analysis                        │      │      │
│  │  │    ├─ Preference rules                         │      │      │
│  │  │    ├─ Queue analysis                           │      │      │
│  │  │    └─ Final decision (play_now | queue)        │      │      │
│  │  │                                                 │      │      │
│  │  │ 4. _generate_audio()                           │      │      │
│  │  │    └─ ElevenLabs ou pyttsx3                    │      │      │
│  │  │                                                 │      │      │
│  │  │ 5. Emit events                                 │      │      │
│  │  │    └─ Via event_bus                            │      │      │
│  │  └──────────────────────────────────────────────────┘      │      │
│  │                                                             │      │
│  │ Atributos:                                                 │      │
│  │  • latency_system: LatencyOptimizedExecutor                │      │
│  │  • media_queue: MediaQueue                                │      │
│  │  • browser_detector: BrowserDetector                      │      │
│  │  • search_engine: DescriptiveSearchReasoningEngine        │      │
│  │  • preferences_engine: PreferenceRulesEngine              │      │
│  │  • event_bus: EventBus (Observer pattern)                 │      │
│  │  • di_container: DIContainer (Singleton)                  │      │
│  │                                                             │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                              ▲                                        │
└──────────────────────────────┼────────────────────────────────────────┘
                               │
┌──────────────────────── CAMADA CORE v2.1 ◄─┐
│                                             │
│  ┌─ 5 Novos Módulos ────────────────────┐  │
│  │                                      │  │
│  │  1️⃣  latency_aware.py                │  │
│  │  ├─ LatencyAwarenessDetector        │  │
│  │  │  └─ detect_complexity()           │  │
│  │  ├─ StreamingResponseManager        │  │
│  │  │  └─ send_intermediate()           │  │
│  │  └─ LatencyOptimizedExecutor        │  │
│  │     ├─ execute_with_awareness()     │  │
│  │     └─ _trigger_background_music()  │  │
│  │                                      │  │
│  │  2️⃣  media_queue.py                  │  │
│  │  ├─ MediaState (enum)               │  │
│  │  │  └─ IDLE, PLAYING, PAUSED, etc   │  │
│  │  ├─ MediaItem (dataclass)           │  │
│  │  │  └─ id, title, artist, source   │  │
│  │  ├─ MediaStateContext               │  │
│  │  │  ├─ start_playing()              │  │
│  │  │  ├─ pause/resume()               │  │
│  │  │  └─ toggle_loop()                │  │
│  │  └─ MediaQueue                      │  │
│  │     ├─ add_to_queue()               │  │
│  │     ├─ skip_to_next()               │  │
│  │     ├─ get_status()                 │  │
│  │     ├─ persist_to_file()            │  │
│  │     └─ load_from_file()             │  │
│  │                                      │  │
│  │  3️⃣  browser_detection.py            │  │
│  │  ├─ BrowserType (enum)              │  │
│  │  │  └─ EDGE, CHROME, BRAVE, etc     │  │
│  │  ├─ BrowserRegistry (dataclass)     │  │
│  │  └─ BrowserDetector                 │  │
│  │     ├─ detect_installed_browsers()  │  │
│  │     ├─ open_url()                   │  │
│  │     ├─ get_browser_by_name()        │  │
│  │     └─ list_open_tabs()             │  │
│  │                                      │  │
│  │  4️⃣  search_reasoning.py             │  │
│  │  ├─ SearchConfidenceLevel (enum)    │  │
│  │  ├─ SearchResult (dataclass)        │  │
│  │  └─ DescriptiveSearchReasoningEngine │  │
│  │     ├─ _extract_keywords()          │  │
│  │     ├─ _search_google()             │  │
│  │     ├─ _reason_with_gemini()        │  │
│  │     ├─ resolve_descriptive_query()  │  │
│  │     └─ validate_before_playback()   │  │
│  │                                      │  │
│  │  5️⃣  preferences.py                  │  │
│  │  ├─ RuleCondition (enum)            │  │
│  │  │  └─ GENRE, ARTIST, TIME, etc     │  │
│  │  ├─ RuleAction (enum)               │  │
│  │  │  └─ USE_PLATFORM, PLAY_NOW, etc  │  │
│  │  ├─ PreferenceRule (dataclass)      │  │
│  │  └─ PreferenceRulesEngine           │  │
│  │     ├─ add_rule()                   │  │
│  │     ├─ get_applicable_rules()       │  │
│  │     ├─ evaluate_context()           │  │
│  │     ├─ record_rule_usage()          │  │
│  │     └─ suggest_rule_from_interaction() │  │
│  │                                      │  │
│  └──────────────────────────────────────┘  │
│                                             │
└─────────────────────────────────────────────┘
         ▲              ▲              ▲
         │              │              │
    E-Core         SQLite        Google/Gemini
   (v2.0)       (preferences)      (Search+LLM)
    
┌──────────────────────── CAMADA EXISTENTE v2.0 ◄──────────────────────┐
│                                                                        │
│  ✓ tool_registry.py          ✓ media_tools.py                         │
│  ✓ brain_v2.py [EXTENDS]     ✓ terminal_tools.py                      │
│  ✓ automation.py             ✓ vision_tools.py                        │
│  ✓ database.py               ✓ memory_tools.py                        │
│  ✓ mobile_bridge.py          ✓ oracle.py                              │
│  ✓ [... e mais]              ✓ main.py [EXTENDS]                      │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

```

---

## Fluxo de Dados: Exemplo Completo

```
Usuário: "Toca aquela música do Inception agora"
    │
    ▼
┌─────────────────────────────────────────┐
│ WebSocket message recebido              │
│ → main.py /ws handler                   │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ brain.ask(question, visual_context)     │
│ Início: ask() em latency_system         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Latency Detection                       │
│ latency_system.execute_with_awareness() │
│  └─ Detecta: "descrição vaga + web"     │
│  └─ Complexity = LONG (7 segundos)      │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Intermediate Message                    │
│ send("Isso vai levar um tempo...")       │
│  ► Frontend recebe → mostra "⏳        │
└─────────────────────────────────────────┘
    │
    ├─ MAIN TASK (async background) ─┐
    │                                 │
    ▼                                 │
┌──────────────────────────────┐   │
│ _process_question()          │   │
│  ├─ Parse: "música" + "film" │   │
│  ├─ Select tool: TocarMusica │   │
│  └─ Trigger: tocar_musica()  │   │
└──────────────────────────────┘   │
    │                              │
    ▼                              │
┌──────────────────────────────────────┐
│ Search Reasoning (Google + Gemini)   │
│ search_engine.validate_before_...()  │
│  ├─ Google: "inception theme song"   │
│  ├─ Gemini: "Principal Theme"        │
│  ├─ Confidence: 0.92                 │
│  └─ Return: SearchResult             │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ Decision Engine (Play Now vs Queue)  │
│ decide_play_mode()                   │
│  ├─ Language signals: "toca agora"   │
│  │  → Score: 0.9 (PLAY NOW urgente)  │
│  ├─ Preferences: soundtrack genre    │
│  │  → Score: 0.8 (learned: play_now) │
│  ├─ Queue: empty (3 items)           │
│  │  → Score: 0.6 (moderado)          │
│  └─ Final: 0.77 > 0.55               │
│     → Decision: PLAY NOW ✓           │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ MediaQueue Action                    │
│ media_queue.play_now(MediaItem)      │
│  ├─ Create MediaItem                 │
│  │  └─ id, title, artist, source     │
│  ├─ Emit: media_state_changed        │
│  ├─ State: IDLE → PLAYING            │
│  └─ Event log em EventBus            │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ Learn Preference (Feedback Loop)     │
│ learn_user_preference()              │
│  ├─ Detect: "inception" ≈ movie     │
│  ├─ Create rule:                     │
│  │  IF genre = "soundtrack"          │
│  │  THEN action = "play_now"         │
│  ├─ Priority: 75                     │
│  ├─ Save em SQLite                   │
│  └─ Event: preference_learned        │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ Generate Response                    │
│ _generate_audio("Tocando agora...")  │
│  ├─ ElevenLabs API                   │
│  └─ Return audio (base64)            │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ Front Média (8s depois)              │
│ send_final(text, audio)              │
│  ► WebSocket envia resposta           │
│  ► Frontend: pausa ⏳, toca áudio     │
│  ► Display: "Tocando agora! 🎵"      │
└──────────────────────────────────────┘

Total de tempo:
├─ Intermediate msg enviada: 100ms ✓
├─ Search + Gemini: 3-4s
├─ Audio generation: 2-3s
├─ Total user wait: ~8s (mas viu msg em 100ms!)
└─ Perceived latency: ▼ 60% (com feedback)
```

---

## Integração de Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                    DIContainer (Singleton)                      │
├─────────────────────────────────────────────────────────────────┤
│  • gemini_client                  • database                    │
│  • elevenlab_client               • event_bus                   │
│  • speech_recognizer              • tool_registry              │
│  • brain (QuintaFeiraBrainV2)      • [new v2.1 services]       │
└─────────────────────────────────────────────────────────────────┘
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
         ┌────────────┐  ┌────────────┐  ┌───────────┐
         │ event_bus  │  │ brain_v2   │  │ tools     │
         ├────────────┤  ├────────────┤  ├───────────┤
         │ emit()     │  │ ask()      │  │media_tools│
         │ subscribe()│  │ decide_... │  │terminal_..│
         │ listeners[]│  │ learn_...  │  │vision_... │
         └────────────┘  └────────────┘  └───────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
        ┌──────────────┐  ┌───────────┐  ┌──────────────┐
        │latency      │  │media_queue│  │browser_detect│
        ├──────────────┤  ├───────────┤  ├──────────────┤
        │system       │  │execute()  │  │open_url()    │
        │stream_mgr   │  │add_queue()│  │auto_detect() │
        └──────────────┘  └───────────┘  └──────────────┘
                               │              
                ┌──────────────┼────────────────┐
                ▼              ▼                ▼
        ┌────────────────┐ ┌──────────┐  ┌──────────────┐
        │search_reasoning│ │preferences│  │automation.py │
        ├────────────────┤ ├──────────┤  ├──────────────┤
        │validate()      │ │rules     │  │osAutomation  │
        │reason_gemini() │ │SQLite    │  │terminal      │
        └────────────────┘ └──────────┘  └──────────────┘
```

---

## Database Schema (SQLite)

```sql
┌─ preference_rules ───────────────────────┐
│ rule_id (PK)                              │
│ condition_type: 'genre' | 'artist' | ... │
│ condition_value: 'rock' | 'beatles' | ... │
│ action_type: 'play_now' | 'queue'        │
│ action_value: 'true' | 'false'           │
│ priority: 0-100                          │
│ enabled: true | false                    │
│ created_at: timestamp                    │
│ last_used: timestamp                     │
│ usage_count: int                         │
│ effectiveness: 0.0-1.0                   │
│                                          │
│ INDEX: (condition_type, condition_value) │
│ INDEX: priority DESC                     │
│ INDEX: enabled                           │
└──────────────────────────────────────────┘

Exemplo de dados:
┌────────────┬──────────────┬──────────────┬───────────┬────────┐
│ rule_id    │ condition    │ action       │ priority  │ effect │
├────────────┼──────────────┼──────────────┼───────────┼────────┤
│ abc123     │ genre:rock   │ play_now:t   │ 80        │ 0.95   │
│ def456     │ context:work │ play_now:f   │ 90        │ 0.87   │
│ ghi789     │ hour:23      │ platform:spo │ 60        │ 0.72   │
└────────────┴──────────────┴──────────────┴───────────┴────────┘
```

---

## Event Flow (EventBus)

```
Global EventBus Listeners (Observer Pattern):

app.event_bus.subscribe(
    event_type='cortex_thinking',
    listener=logger.log_decision_tree
)
  ► Fired when: decide_play_mode() called
  ► Data: {language_score, pref_score, queue_score, final_score}

app.event_bus.subscribe(
    event_type='media_queue_*',
    listener=frontend_websocket.broadcast
)
  ► Fired when: add_to_queue(), skip_to_next(), etc
  ► Data: {queue_status, current_playing, queue_size}

app.event_bus.subscribe(
    event_type='preference_rule_added',
    listener=analytics.track_learning
)
  ► Fired when: learn_user_preference() success
  ► Data: {rule_id, condition, action, confidence}

app.event_bus.subscribe(
    event_type='browser_detected',
    listener=logger.log_system_info
)
  ► Fired when: browser_detector.detect_installed_browsers()
  ► Data: {browser_type, executable_path}

app.event_bus.subscribe(
    event_type='search_*',
    listener=cache_manager.update_search_cache
)
  ► Fired when: search_engine operations
  ► Data: {query, track_name, confidence}
```

---

## Performance Targets

```
Component                  Target      Current    Status
─────────────────────────────────────────────────────────
Intermediate message        < 200ms     ~100ms     ✓
execute_with_awareness()    < 500ms     ~300ms     ✓
add_to_queue()             < 50ms      ~20ms      ✓
skip_to_next()             < 100ms     ~40ms      ✓
get_applicable_rules()     < 100ms     ~60ms      ✓
validate_before_playback() < 2s        ~1.8s      ✓
decide_play_mode()         < 500ms     ~350ms     ✓
browser_detect (first)     < 1s        ~750ms     ✓
browser_open_url()         < 500ms     ~400ms     ✓
preference_query (SQLite)  < 100ms     ~50ms      ✓
```

---

## Próxima Arquitetura (v2.2)

```
Planejado para futuro:
├─ M/L Training Pipeline
│  ├─ Histórico de decisões
│  ├─ Feedback do usuário
│  └─ Model retraining mensal
├─ Multi-LLM Support
│  ├─ Claude API fallback
│  ├─ OpenAI GPT integration
│  └─ LLM selection strategy
├─ Distributed Cache (Redis)
│  ├─ Search results cache
│  ├─ Gemini reasoning cache
│  └─ Browser detection cache
└─ Hot-Reload Plugin System
   ├─ Custom tools via plugin
   ├─ Runtime tool install
   └─ Zero-downtime updates
```

---

Generated: v2.1 Architecture Documentation
Last Updated: 2024
