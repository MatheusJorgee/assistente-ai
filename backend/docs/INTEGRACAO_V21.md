"""
Guia de Integração: Módulos v2.1 com Brain v2.0

Este arquivo documenta como integrar todos os 5 novos módulos (latency_aware, 
media_queue, browser_detection, search_reasoning, preferences) com brain_v2.py
e o sistema existente.
"""

# ============================================================================
# 1. IMPORTS & INICIALIZAÇÃO (em brain_v2.py ou main.py)
# ============================================================================

from backend.core.latency_aware import create_latency_aware_system, LatencyAwarenessDetector
from backend.core.media_queue import create_media_queue, MediaQueue
from backend.core.browser_detection import create_browser_detector, BrowserDetector
from backend.core.search_reasoning import DescriptiveSearchReasoningEngine, SearchValidationTool
from backend.core.preferences import create_preferences_engine, PreferenceRulesEngine


# ============================================================================
# 2. INSTANTIAÇÃO NA CLASSE QuintaFeiraBrainV2
# ============================================================================

class QuintaFeiraBrainV2:
    """Brain refatorado com suporte a v2.1 features."""
    
    def __init__(self, di_container, event_bus):
        # ... código existente ...
        self.di_container = di_container
        self.event_bus = event_bus
        
        # === NOVOS COMPONENTES v2.1 ===
        
        # 1. Latency Awareness (será inicializado com websocket_send_callback)
        self.latency_system = None  # Será inicializado em setup()
        
        # 2. Media Queue
        self.media_queue = None  # Será inicializado em setup()
        
        # 3. Browser Detection
        self.browser_detector = None  # Será inicializado em setup() [async]
        
        # 4. Search Reasoning
        self.search_engine = None  # Será inicializado em setup()
        
        # 5. Preferences Engine
        self.preferences_engine = None  # Será inicializado em setup() [async]
    
    async def setup_v21_features(self, websocket_send_callback=None):
        """
        Inicializa todos os componentes v2.1.
        DEVE SER CHAMADO no startup da aplicação.
        
        Args:
            websocket_send_callback: função async (msg: str) -> None
        """
        
        # 1. Latency Awareness System
        if websocket_send_callback:
            self.latency_system = create_latency_aware_system(websocket_send_callback)
        else:
            # Fallback: criar sem streaming
            self.latency_system = LatencyAwarenessDetector()
        
        # 2. Media Queue (com callback de eventos)
        async def queue_event_callback(event_type, data):
            """Propagar eventos de queue para EventBus."""
            await self.event_bus.emit(f"media_queue_{event_type}", data)
        
        self.media_queue = await create_media_queue(
            max_size=100,
            event_bus_callback=queue_event_callback
        )
        
        # 3. Browser Detection (async operation!)
        self.browser_detector = await create_browser_detector(
            event_bus_callback=lambda event, data: asyncio.create_task(
                self.event_bus.emit(f"browser_{event}", data)
            )
        )
        
        # 4. Search Reasoning Engine
        self.search_engine = DescriptiveSearchReasoningEngine(
            gemini_client=self.di_container.get('gemini_client'),
            event_bus_callback=lambda event, data: asyncio.create_task(
                self.event_bus.emit(f"search_{event}", data)
            )
        )
        
        # 5. Preferences Rules Engine
        self.preferences_engine = await create_preferences_engine(
            db_path="backend/temp_vision/preferences.db",
            event_bus_callback=lambda event, data: asyncio.create_task(
                self.event_bus.emit(f"preference_{event}", data)
            )
        )
        
        print("[SETUP] v2.1 Features inicializados com sucesso")


# ============================================================================
# 3. FLUXO PRINCIPAL: ask() COM LATENCY AWARENESS
# ============================================================================

    async def ask(self, question: str, visual_context: str = "") -> Tuple[str, str]:
        """
        Pergunta principal do Brain com suporte a latency awareness.
        
        Fluxo:
        1. Detectar complexidade (latency aware)
        2. Se longo, enviar mensagem intermediária
        3. Executar task em background
        4. Enviar resposta final
        
        Args:
            question: Pergunta/comando do usuário
            visual_context: Contexto visual (screenshot)
        
        Returns:
            (resposta_texto, resposta_audio_base64)
        """
        
        # === PARTE 1: PROCESSAMENTO COM LATENCY AWARENESS ===
        
        async def main_task():
            """Task principal que pode demorar."""
            
            # Processar questão normalmente
            response_text = await self._process_question(question, visual_context)
            
            # Gerar áudio
            response_audio = await asyncio.to_thread(
                self._generate_audio,
                response_text
            )
            
            return response_text, response_audio
        
        # Se latency_system está disponível de verdade
        if self.latency_system:
            response_text, response_audio = await self.latency_system.execute_with_awareness(
                user_input=question,
                main_task=main_task,
                request_id=f"req_{id(question)}",
                should_suggest_music=True
            )
        else:
            # Fallback: executar sem intermediate messages
            response_text, response_audio = await main_task()
        
        return response_text, response_audio


# ============================================================================
# 4. INTEGRAÇÃO COM MEDIA TOOLS
# ============================================================================

    async def decide_play_mode(
        self,
        track_name: str,
        artist: str,
        user_query: str,
        genre: str = "",
        current_time: str = ""
    ) -> str:
        """
        Decide entre PLAY_NOW e ADD_TO_QUEUE usando preferences + context.
        
        Args:
            track_name: Nome da faixa
            artist: Artista
            user_query: Query original do usuário
            genre: Gênero detectado
            current_time: Horário atual
        
        Returns:
            "play_now" ou "add_to_queue"
        """
        
        # 1. Analisar sinais de linguagem natural
        language_score = self._analyze_language_signals(user_query)
        
        # 2. Obter preferências aplicáveis
        context = {
            'genre': genre.lower() if genre else '',
            'device': 'desktop',  # De DI container
            'artist': artist.lower(),
            'time_of_day': self._get_time_period(current_time),
        }
        
        applicable_rules = await self.preferences_engine.get_applicable_rules(context)
        pref_score = self._calculate_rule_score(applicable_rules)
        
        # 3. Analisar estado da fila
        queue_status = await self.media_queue.get_status()
        queue_score = self._calculate_queue_score(queue_status)
        
        # 4. Score final
        final_score = (
            language_score * 0.30 +
            pref_score * 0.35 +
            queue_score * 0.35
        )
        
        # 5. Registrar raciocínio
        await self.event_bus.emit('cortex_thinking', {
            'decision': 'play_mode',
            'track': f"{artist} - {track_name}",
            'language_score': round(language_score, 2),
            'pref_score': round(pref_score, 2),
            'queue_score': round(queue_score, 2),
            'final_score': round(final_score, 2),
            'rules_applied': len(applicable_rules)
        })
        
        # 6. Retornar decisão
        return "play_now" if final_score >= 0.55 else "add_to_queue"
    
    
    async def tocar_musica_inteligente(
        self,
        descricao: str,
        platform: str = "spotify"
    ) -> Dict[str, Any]:
        """
        Reproduz música com raciocínio de busca evoluído.
        
        Fluxo:
        1. Validar consulta (search verification)
        2. Decidir play now vs queue
        3. Reproduzir com contexto
        
        Args:
            descricao: Descrição ou nome da música
            platform: Plataforma ("spotify", "youtube", "local")
        
        Returns:
            {
                'success': bool,
                'track_name': str,
                'artist': str,
                'decision': 'play_now' | 'add_to_queue',
                'message': str,
                'confidence': float
            }
        """
        
        # 1. Validar música com search reasoning
        should_play, search_result, message = await self.search_engine.validate_before_playback(
            descricao,
            context=f"Platform: {platform}"
        )
        
        if not should_play and not search_result:
            # Não conseguiu encontrar
            await self.event_bus.emit('music_resolution_failed', {
                'query': descricao,
                'message': message
            })
            return {
                'success': False,
                'message': message,
                'confidence': 0.0
            }
        
        # 2. Usar resultado da busca
        track_info = search_result or SearchResult(
            query=descricao,
            track_name=descricao,
            artist="",
            confidence=0.5
        )
        
        # 3. Decidir play now vs queue
        play_decision = await self.decide_play_mode(
            track_name=track_info.track_name,
            artist=track_info.artist,
            user_query=descricao,
            genre=track_info.metadata.get('genre', '')
        )
        
        # 4. Executar ação
        if play_decision == "play_now":
            # Criar MediaItem e reproduzir
            media_item = MediaItem(
                id=hash(track_info.track_name) % 10**8,
                title=track_info.track_name,
                artist=track_info.artist,
                source=platform,
                url=track_info.source_url
            )
            await self.media_queue.play_now(media_item)
            decision_msg = f"Tocando agora: {track_info.track_name}"
        else:
            # Adicionar à fila
            media_item = MediaItem(
                id=hash(track_info.track_name) % 10**8,
                title=track_info.track_name,
                artist=track_info.artist,
                source=platform,
                url=track_info.source_url
            )
            await self.media_queue.add_to_queue(media_item)
            
            # Contar posição
            status = await self.media_queue.get_status()
            position = status.queue_size
            decision_msg = f"Adicionada à fila (posição #{position}): {track_info.track_name}"
        
        # 5. Registrar uso de regra (feedback loop)
        if search_result and play_decision == "play_now":
            await self.preferences_engine.record_rule_usage(
                rule_id=play_decision,
                was_effective=True
            )
        
        await self.event_bus.emit('music_played', {
            'track': track_info.track_name,
            'artist': track_info.artist,
            'decision': play_decision,
            'confidence': track_info.confidence
        })
        
        return {
            'success': True,
            'track_name': track_info.track_name,
            'artist': track_info.artist,
            'decision': play_decision,
            'message': decision_msg,
            'confidence': track_info.confidence
        }


# ============================================================================
# 5. INTEGRAÇÃO COM TERMINAL TOOLS (Browser Detection)
# ============================================================================

    async def abrir_url_inteligente(
        self,
        url: str,
        browser_name: str = "default"
    ) -> Dict[str, Any]:
        """
        Abre URL em navegador específico ou padrão.
        
        Args:
            url: URL a abrir
            browser_name: "chrome", "edge", "brave", "firefox", ou "default"
        
        Returns:
            {'success': bool, 'browser': str, 'message': str}
        """
        
        success = await self.browser_detector.open_url(url, browser_name)
        
        if success:
            installed = await self.browser_detector.get_installed_browsers()
            await self.event_bus.emit('url_opened_successfully', {
                'url': url,
                'browser': browser_name
            })
            return {
                'success': True,
                'browser': browser_name,
                'message': f"Abrindo em {browser_name}..."
            }
        else:
            return {
                'success': False,
                'browser': browser_name,
                'message': f"Não consegui abrir em {browser_name}"
            }


# ============================================================================
# 6. PREFERENCE LEARNING: Criar Regras Automaticamente
# ============================================================================

    async def learn_user_preference(
        self,
        query: str,
        action_taken: str,
        user_satisfied: bool = True
    ) -> Optional[str]:
        """
        Cria regra de preferência baseada em padrão de comportamento.
        
        Exemplo:
            - User diz "rock" frequentemente
            - User escolhe "spotify"
            - Sistema sugere: genre=rock → platform=spotify
        
        Args:
            query: Consulta original
            action_taken: Ação que foi realizada ("play_spotify", "add_queue", etc)
            user_satisfied: Se o usuário gostou
        
        Returns:
            ID da regra criada ou None
        """
        
        # 1. Sugerir regra
        await self.preferences_engine.suggest_rule_from_interaction(query, action_taken)
        
        # 2. Se user satisfeito, criar regra automaticamente
        if user_satisfied:
            # Extrair condição e ação
            keywords = query.lower().split()
            
            # Heurística simples
            possible_condition = next(
                (kw for kw in keywords if len(kw) > 3),
                None
            )
            
            if possible_condition:
                rule_id = await self.preferences_engine.add_rule(
                    condition_type=RuleCondition.GENRE,
                    condition_value=possible_condition,
                    action_type=RuleAction.USE_PLATFORM,
                    action_value=action_taken.split('_')[-1],  # "play_spotify" → "spotify"
                    priority=75
                )
                
                await self.event_bus.emit('preference_learned', {
                    'condition': possible_condition,
                    'action': action_taken,
                    'rule_id': rule_id
                })
                
                return rule_id
        
        return None


# ============================================================================
# HELPER METHODS
# ============================================================================

    def _analyze_language_signals(self, query: str) -> float:
        """Score de 0 (queue) a 1 (play now) baseado em linguagem."""
        query_lower = query.lower()
        
        play_keywords = ['toca', 'play', 'agora', 'já', 'começa']
        queue_keywords = ['coloca', 'adiciona', 'depois', 'fila']
        
        play_count = sum(1 for kw in play_keywords if kw in query_lower)
        queue_count = sum(1 for kw in queue_keywords if kw in query_lower)
        
        if play_count == 0 and queue_count == 0:
            return 0.5
        
        total = play_count + queue_count
        return play_count / total


    def _get_time_period(self, current_time: str) -> str:
        """Converte hora para período do dia."""
        try:
            from datetime import datetime
            if not current_time:
                hour = datetime.now().hour
            else:
                hour = int(current_time.split(':')[0])
            
            if 5 <= hour < 11:
                return 'morning'
            elif 11 <= hour < 17:
                return 'afternoon'
            elif 17 <= hour < 21:
                return 'evening'
            else:
                return 'night'
        except:
            return 'afternoon'


    def _calculate_rule_score(self, rules: List) -> float:
        """Calcula score de preferências."""
        if not rules:
            return 0.5
        
        best_rule = max(rules, key=lambda r: r.priority * r.effectiveness)
        
        action_scores = {
            'play_now': 1.0,
            'add_to_queue': 0.0,
            'use_platform': 0.5
        }
        
        base_score = action_scores.get(best_rule.action_type.value, 0.5)
        priority_boost = (best_rule.priority / 100) * 0.4
        
        return min(1.0, base_score + priority_boost)


    def _calculate_queue_score(self, queue_status) -> float:
        """Calcula score baseado no tamanho da fila."""
        queue_size = queue_status.queue_size
        
        if queue_size == 0:
            return 1.0
        elif queue_size < 3:
            return 0.6
        elif queue_size < 6:
            return 0.4
        else:
            return 0.1


# ============================================================================
# 7. STARTUP NO main.py
# ============================================================================

# Em main.py:

@app.on_event("startup")
async def startup_v21():
    """Inicializar v2.1 features."""
    
    # 1. Instanciar brain com DI
    brain = QuintaFeiraBrainV2(di_container, event_bus)
    
    # 2. Setup v2.1 components
    await brain.setup_v21_features(
        websocket_send_callback=None  # Será passado por conexão WebSocket
    )
    
    # Guardar global
    app.state.brain = brain
    print("✓ v2.1 Features inicializadas")


# Em WebSocket handler:

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Re-inicializar latency system com este websocket
    async def ws_send(msg: str):
        await websocket.send_text(msg)
    
    app.state.brain.latency_system = create_latency_aware_system(ws_send)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Processar...
    except:
        pass


# ============================================================================
"""
RESUMO DE INTEGRAÇÃO:

✓ Latency Awareness
  - Detecta tarefas longas
  - Envia intermediate messages
  - Não bloqueia asyncio da pesquisa

✓ Media Queue
  - Gerencia fila de reprodução
  - State machine (Playing, Paused, Queued)
  - Persistência em JSON

✓ Browser Detection
  - Localiza navegadores instalados
  - Abre URLs em browser específico
  - Event logging

✓ Search Reasoning
  - Google Search + Gemini validation
  - Confiança de resultados
  - Cache de buscas

✓ Preferences Engine
  - Aprende preferências do usuário
  - Decision tree com regras
  - Feedback loop para efetividade

PRÓXIMOS PASSOS:
1. Testar integração com teste_sistema_v21.py
2. Atualizar frontend para mostrar queue
3. Adicionar analytics para rastreamento
"""
