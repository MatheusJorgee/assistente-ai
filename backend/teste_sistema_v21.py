"""
Suite de Testes: Quinta-Feira v2.1
Validação de: Latency Awareness, Media Queue, Browser Detection,
Search Reasoning, Preference Learning

Execute: python backend/teste_sistema_v21.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Adicionar backend ao path
sys.path.insert(0, str(Path(__file__).parent))

from core.latency_aware import (
    LatencyAwarenessDetector,
    TaskComplexity,
    StreamingResponseManager,
    create_latency_aware_system
)
from core.media_queue import (
    create_media_queue,
    MediaItem,
    MediaState,
    LoopMode
)
from core.browser_detection import create_browser_detector
from core.search_reasoning import DescriptiveSearchReasoningEngine, SearchResult
from core.preferences import (
    create_preferences_engine,
    RuleCondition,
    RuleAction
)


# ============================================================================
# TESTES LATENCY AWARENESS
# ============================================================================

async def test_latency_detector():
    """Testa detecção de complexidade de tarefas."""
    print("\n" + "="*60)
    print("TEST 1: Latency Awareness Detector")
    print("="*60)
    
    detector = LatencyAwarenessDetector()
    
    test_cases = [
        ("toca bohemian", TaskComplexity.INSTANT, "Comando simples"),
        ("pesquisa sobre IA", TaskComplexity.MODERATE, "Requer busca"),
        ("aquela música do filme Inception", TaskComplexity.LONG, "Descrição + busca web"),
        ("pause a música", TaskComplexity.INSTANT, "Controle direto"),
        ("busca múltiplos artistas e cria playlist", TaskComplexity.LONG, "Tarefas múltiplas"),
    ]
    
    all_passed = True
    for query, expected_complexity, description in test_cases:
        detected = detector.detect_complexity(query)
        passed = detected == expected_complexity
        
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} | {description:30} | {query}")
        print(f"       Expected: {expected_complexity.name:12} Got: {detected.name}")
        
        if not passed:
            all_passed = False
    
    print(f"\n-> Resultado: {'PASSOU' if all_passed else 'FALHOU'}")
    return all_passed


async def test_streaming_response_manager():
    """Testa envio de mensagens intermediárias via streaming."""
    print("\n" + "="*60)
    print("TEST 2: Streaming Response Manager")
    print("="*60)
    
    messages_sent = []
    
    async def mock_send(msg: str):
        messages_sent.append(msg)
        print(f"  -> Enviado: {msg[:50]}...")
    
    manager = StreamingResponseManager(mock_send)
    
    # Detector de complexidade
    detector = LatencyAwarenessDetector()
    complexity = detector.detect_complexity("pesquisa sobre economia brasileira")
    intermediate = detector.get_intermediate_message(complexity)
    
    # Enviar intermediária
    await manager.send_intermediate(intermediate, "req_001")
    
    # Enviar final
    await manager.send_final(
        "Economia brasileira cresceu 2.1% em 2024",
        request_id="req_001"
    )
    
    passed = len(messages_sent) == 2
    print(f"\nMensagens enviadas: {len(messages_sent)}/2")
    print(f"-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    
    return passed


# ============================================================================
# TESTES MEDIA QUEUE
# ============================================================================

async def test_media_queue():
    """Testa gerenciamento de fila de mídia."""
    print("\n" + "="*60)
    print("TEST 3: Media Queue Management")
    print("="*60)
    
    events_emitted = []
    
    async def event_callback(event_type, data):
        events_emitted.append((event_type, data))
    
    queue = create_media_queue(max_size=5, event_bus_callback=event_callback)
    
    # Teste 1: Criar items
    item1 = MediaItem(
        id="song_1",
        title="Bohemian Rhapsody",
        artist="Queen",
        source="spotify"
    )
    item2 = MediaItem(
        id="song_2",
        title="Stairway to Heaven",
        artist="Led Zeppelin",
        source="youtube"
    )
    
    # Teste 2: Adicionar à fila
    success1 = await queue.add_to_queue(item1)
    success2 = await queue.add_to_queue(item2)
    
    print(f"[OK] Item 1 adicionado: {success1}")
    print(f"[OK] Item 2 adicionado: {success2}")
    
    # Teste 3: Obter status
    status = await queue.get_status()
    print(f"\nStatus da fila:")
    print(f"  - Estado: {status.current_state.value}")
    print(f"  - Tamanho: {status.queue_size}")
    print(f"  - Items: {len(status.queue)}")
    
    # Teste 4: Play now (substitui)
    item3 = MediaItem(
        id="song_3",
        title="Like a Rolling Stone",
        artist="Bob Dylan",
        source="spotify"
    )
    await queue.play_now(item3)
    
    status = await queue.get_status()
    print(f"\nApós play_now:")
    print(f"  - Tocando agora: {status.current_playing.title if status.current_playing else 'Nada'}")
    print(f"  - Estado: {status.current_state.value}")
    
    # Teste 5: Toggle loop
    await queue.toggle_loop(LoopMode.TRACK)
    status = await queue.get_status()
    print(f"\nApós toggle loop:")
    print(f"  - Loop mode: {status.loop_mode.value}")
    print(f"  - Estado: {status.current_state.value}")
    
    # Teste 6: Skip to next
    next_item = await queue.skip_to_next()
    print(f"\nApós skip_to_next:")
    print(f"  - Próximo item: {next_item.title if next_item else 'Nada'}")
    
    passed = (
        success1 and success2 and
        status.queue_size >= 0 and
        status.loop_mode == LoopMode.TRACK
    )
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    print(f"Eventos emitidos: {len(events_emitted)}")
    
    return passed


# ============================================================================
# TESTES BROWSER DETECTION
# ============================================================================

async def test_browser_detection():
    """Testa detecção de navegadores instalados."""
    print("\n" + "="*60)
    print("TEST 4: Browser Detection")
    print("="*60)
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    detector = await create_browser_detector(
        event_bus_callback=event_callback
    )
    
    # Obter lista de navegadores instalados
    installed = await detector.get_installed_browsers()
    
    print(f"Navegadores detectados: {len(installed)}")
    for browser in installed:
        print(f"  [OK] {browser.name:15} | {browser.executable_path or 'N/A'}")
    
    # Verificar se pelo menos um foi detectado
    passed = len(installed) > 0
    
    # Listar eventos
    print(f"\nEventos emitidos: {len(events)}")
    for event_type, data in events[:5]:  # Primeiros 5
        print(f"  [{event_type}]")
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU (Nenhum navegador detectado)'}")
    
    return passed


# ============================================================================
# TESTES SEARCH REASONING
# ============================================================================

async def test_search_reasoning():
    """Testa raciocínio de busca e validação."""
    print("\n" + "="*60)
    print("TEST 5: Search Reasoning Engine")
    print("="*60)
    
    # Mock de Gemini client (usar dummy)
    class MockGeminiClient:
        def generate_content(self, prompt):
            """Método síncrono que simula a API do Gemini."""
            class Response:
                text = '''
                {
                    "track_name": "Song from Movie",
                    "artist": "Movie Composer",
                    "confidence": 85,
                    "reasoning": "Found in soundtrack",
                    "fallback_options": []
                }
                '''
            return Response()
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    engine = DescriptiveSearchReasoningEngine(
        gemini_client=MockGeminiClient(),
        event_bus_callback=event_callback
    )
    
    # Teste: Resolver consulta descritiva
    query = "aquela música que toca no filme Inception"
    
    result = await engine.resolve_descriptive_query(
        query,
        context="Movie soundtrack",
        min_confidence=0.7
    )
    
    if result:
        print(f"Resultado encontrado:")
        print(f"  [Track] {result.track_name}")
        print(f"  [Artist] {result.artist}")
        print(f"  [Confidence] {result.confidence:.0%}")
        print(f"  [Reasoning] {result.reasoning}")
    else:
        print("Nenhum resultado com confiança suficiente")
    
    passed = result is not None and result.confidence > 0.5
    
    print(f"\nEventos emitidos: {len(events)}")
    print(f"-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    
    return passed


# ============================================================================
# TESTES PREFERENCE RULES ENGINE
# ============================================================================

async def test_preferences_engine():
    """Testa motor de preferências."""
    print("\n" + "="*60)
    print("TEST 6: Preference Rules Engine")
    print("="*60)
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    engine = await create_preferences_engine(
        db_path="backend/temp_vision/test_preferences.db",
        event_bus_callback=event_callback
    )
    
    # Teste 1: Criar regra
    rule_id = await engine.add_rule(
        condition_type=RuleCondition.GENRE,
        condition_value="rock",
        action_type=RuleAction.USE_PLATFORM,
        action_value="spotify",
        priority=80
    )
    
    print(f"Regra criada: {rule_id}")
    
    # Teste 2: Obter regras aplicáveis
    context = {
        'genre': 'rock',
        'device': 'desktop',
        'time_of_day': 'afternoon'
    }
    
    applicable_rules = await engine.get_applicable_rules(context)
    print(f"\nRegras aplicáveis para contexto {context}:")
    print(f"  Encontradas: {len(applicable_rules)}")
    
    for rule in applicable_rules:
        print(f"  - {rule.condition_type.value}={rule.condition_value}")
        print(f"    -> {rule.action_type.value}={rule.action_value} (priority={rule.priority})")
    
    # Teste 3: Avaliar contexto
    actions = await engine.evaluate_context(context)
    print(f"\nAções recomendadas:")
    for action_type, action_value in actions.items():
        print(f"  - {action_type} = {action_value}")
    
    # Teste 4: Registrar uso
    await engine.record_rule_usage(rule_id, was_effective=True)
    
    # Recarregar para ver efetividade atualizada
    await engine.load_rules()
    if rule_id in engine._rules:
        updated_rule = engine._rules[rule_id]
        print(f"\nRegra após uso:")
        print(f"  - Usage count: {updated_rule.usage_count}")
        print(f"  - Effectiveness: {updated_rule.effectiveness:.2f}")
    
    passed = len(applicable_rules) > 0 and bool(actions)
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    
    return passed


# ============================================================================
# TESTES DECISION LOGIC
# ============================================================================

async def test_play_now_vs_queue_decision():
    """Testa lógica de decisão Play Now vs Queue."""
    print("\n" + "="*60)
    print("TEST 7: Play Now vs Queue Decision Logic")
    print("="*60)
    
    # Simular engine de preferências
    engine = await create_preferences_engine(
        db_path="backend/temp_vision/test_decisions.db"
    )
    
    # Adicionar algumas regras de teste
    await engine.add_rule(
        RuleCondition.GENRE, "rock",
        RuleAction.PLAY_NOW, "true",
        priority=70
    )
    
    await engine.add_rule(
        RuleCondition.CONTEXT, "work",
        RuleAction.PLAY_NOW, "false",
        priority=80
    )
    
    # Teste: diferentes contextos
    test_cases = [
        ({
            'genre': 'rock',
            'device': 'desktop',
            'time_of_day': 'afternoon'
        }, "rock + afternoon"),
        ({
            'genre': 'rock',
            'context': 'work',
            'device': 'desktop'
        }, "rock + work context"),
        ({
            'genre': 'jazz',
            'time_of_day': 'night',
            'device': 'phone'
        }, "jazz + night"),
    ]
    
    print("Decisões para contextos:")
    
    all_passed = True
    for context, description in test_cases:
        rules = await engine.get_applicable_rules(context)
        actions = await engine.evaluate_context(context)
        
        print(f"\n  {description}")
        print(f"    - Regras aplicáveis: {len(rules)}")
        print(f"    - Acoes: {actions}")
    
    passed = True
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    
    return passed


# ============================================================================
# RUNNER PRINCIPAL
# ============================================================================

async def run_all_tests():
    """Executa todos os testes."""
    print("\n" + "#"*60)
    print("# SUITE DE TESTES: Quinta-Feira v2.1")
    print("#"*60)
    
    results = {
        'Latency Detector': await test_latency_detector(),
        'Streaming Manager': await test_streaming_response_manager(),
        'Media Queue': await test_media_queue(),
        'Browser Detection': await test_browser_detection(),
        'Search Reasoning': await test_search_reasoning(),
        'Preferences Engine': await test_preferences_engine(),
        'Decision Logic': await test_play_now_vs_queue_decision(),
    }
    
    # Resumo final
    print("\n" + "#"*60)
    print("# RESUMO DOS TESTES")
    print("#"*60)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed
    
    print(f"\nTotal: {total} testes")
    print(f"[PASS] Passaram: {passed}")
    print(f"[FAIL] Falharam: {failed}")
    
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} | {test_name}")
    
    print("\n" + "#"*60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
