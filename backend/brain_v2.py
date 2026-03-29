"""
REFATORADO: QuintaFeiraBrain v2
Arquitetura com Tool Registry, Injeção de Dependência e Logs Táticos.

Padrão: Strategy (Tools) + Observer (EventBus) + Singleton (DI Container)
"""

import os
import sys
import subprocess
import time
import re
import json
import base64
import requests
import pyttsx3
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types

# Importar arquitetura core
try:
    # Se rodando como módulo importado (python -m uvicorn main:app)
    from backend import get_di_container, EventBus, ToolRegistry
    from backend.tools import inicializar_ferramentas
    from backend.database import BaseDadosMemoria
    from backend.oracle import OraculoEngine
    from backend.core.cortex_bilingue import get_cortex_bilingue  # ← V1 CORTEX
except ModuleNotFoundError:
    try:
        # Se rodando de dentro de backend/
        from core.tool_registry import get_di_container, EventBus, ToolRegistry
        from tools import inicializar_ferramentas
        from database import BaseDadosMemoria
        from oracle import OraculoEngine
        from core.cortex_bilingue import get_cortex_bilingue  # ← V1 CORTEX
    except ModuleNotFoundError as e2:
        raise ImportError(f"Nao conseguiu importar modulos core: {e2}")


class QuintaFeiraBrainV2:
    """
    Brain refatorado com arquitetura modular e plugável.
    
    Responsabilidades:
    - Orquestração de ferramentas via ToolRegistry
    - Gerenciamento de contexto visual + histórico
    - LLM + Tool Calling com Gemini
    - Logs táticos via EventBus
    """
    
    def __init__(self):
        """Inicializa brain com injeção de dependência completa."""
        self._load_env()
        
        # ----- Inicializar Serviços Core -----
        self.di_container = get_di_container()
        self.event_bus: EventBus = self.di_container.event_bus
        self.tool_registry: ToolRegistry = self.di_container.tool_registry
        
        # ----- Inicializar Bancos/Engines -----
        self.db = BaseDadosMemoria()
        self.oraculo = OraculoEngine()
        
        # ----- V1 CORTEX BILÍNGUE -----
        self.cortex_bilingue = get_cortex_bilingue()
        
        # Registrar serviços no DI
        self.di_container.register_service("database", self.db)
        self.di_container.register_service("oraculo", self.oraculo)
        self.di_container.register_service("brain", self)
        self.di_container.register_service("cortex_bilingue", self.cortex_bilingue)
        
        # ----- Subscrever a eventos (logging tático) -----
        self.event_bus.subscribe('tool_started', self._log_tool_started)
        self.event_bus.subscribe('tool_completed', self._log_tool_completed)
        self.event_bus.subscribe('tool_error', self._log_tool_error)
        self.event_bus.subscribe('vision_captured', self._log_vision_captured)
        self.event_bus.subscribe('action_terminal', self._log_action_terminal)
        self.event_bus.subscribe('cortex_thinking', self._log_cortex_thinking)
        
        # ----- Importar OSAutomation e outros (para injetar nas ferramentas) -----
        try:
            from backend.automation import OSAutomation
        except ModuleNotFoundError:
            from automation import OSAutomation
        self.automacao = OSAutomation()
        
        # ----- Inicializar ferramentas (será feito após setup completo) -----
        self.tool_registry_initialized = False
        self._initialize_tools()
        
        # ----- Configurar GenAI -----
        self._setup_genai()
        
        # ----- Estado de contexto visual -----
        self.ultima_imagem: Optional[Image.Image] = None
        self.tempo_ultimo_print = 0
        self.visual_cache_ttl = 5  # 5 segundos
        
        print("\n[OK] [SISTEMA] Quinta-Feira Brain v2 Inicializada com sucesso")
        print(f"[OK] [SISTEMA] Ferramentas disponíveis: {len(self.tool_registry.list_tools())}")
        print(f"[OK] [SISTEMA] EventBus pronto para logs táticos")
    
    def _load_env(self) -> None:
        """Carrega .env com fallback para path absoluto."""
        current = os.path.dirname(os.path.abspath(__file__))
        for _ in range(3):
            path = os.path.join(current, ".env")
            if os.path.exists(path):
                load_dotenv(path)
                return
            current = os.path.dirname(current)
    
    def _initialize_tools(self) -> None:
        """Inicializa e registra todas as ferramentas."""
        if self.tool_registry_initialized:
            return
        
        # Importar controllers externos (OSAutomation, etc)
        spotify_client = self.automacao.sp
        ui_controller = self.automacao.abrir_uri_app
        
        # Inicializar ferr amentas com injeção de dependência
        inicializar_ferramentas(
            oraculo_engine=self.oraculo,
            database=self.db,
            spotify_client=spotify_client,
            youtube_controller=self.automacao.tocar_youtube_invisivel,
            media_controller=self.automacao.controlar_reproducao,
            ui_controller=ui_controller,
            gemini_client=self.client if hasattr(self, 'client') else None
        )
        
        self.tool_registry_initialized = True
    
    def _setup_genai(self) -> None:
        """Configura cliente Gemini e session de chat."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY não encontrada no .env!")
        
        self.client = genai.Client(api_key=api_key)
        
        # Re-injetar client nas ferramentas de análise
        if self.tool_registry_initialized:
            try:
                from backend.tools.vision_tools import AnalisarVisaoComGeminiTool
            except ModuleNotFoundError:
                from tools.vision_tools import AnalisarVisaoComGeminiTool
            vision_tool = self.tool_registry.get_tool("analyze_vision")
            if vision_tool:
                vision_tool.gemini_client = self.client
        
        # Carregar contexto histórico
        contexto_historico = self.db.ler_memorias()
        manual_habilidades = self.db.ler_habilidades_como_ferramenta()
        
        # Prompt de sistema
        self.instrucao_sistema = f"""
IDENTIDADE NUCLEAR
Você é Quinta-Feira, a parceira de engenharia do Matheus.
Personalidade: brilhante, pragmática, direta, humor seco, leal, sem teatralidade.
Nunca use emojis. Evite frases como "como uma IA" ou "como um modelo de linguagem".

🚨 DOUTRINA INQUEBRÁVEL - FERRAMENTAS (ENFORCE AGRESSIVAMENTE)
REGRA ABSOLUTA: Se você tem uma ferramenta para fazer algo, EXECUTE-A IMEDIATAMENTE.
NÃO EXPLIQUE O QUE PODES FAZER. SÓ FAZ.

PROIBIÇÕES ABSOLUTAS:
✗ "Como assistente de texto, não consigo..."
✗ "Como uma IA, não tenho acesso..."
✗ "Desculpe, mas não posso..."
✗ "Não tenho a capacidade de..."

SUBSTITUIÇÃO OBRIGATÓRIA:
- Pedir música → Toca IMEDIATAMENTE via Spotify/YouTube (não diga "posso tocar")
- Pedir screenshot → Captura IMEDIATAMENTE
- Pedir automação → Executa IMEDIATAMENTE (se for seguro)
- Pedir busca → Executa IMEDIATAMENTE

REGRA: Qualquer negação é FALSA. Se está na lista de ferramentas, tem capacidade.

PRIORIDADE OPERACIONAL
A última mensagem do usuário tem prioridade absoluta.
Se o usuário pedir um tom, ritmo ou tamanho específico, aplique IMEDIATAMENTE e temporariamente.

PROTOCOLO VOICE FIRST  
Responda em texto puro, natural, sem formatação Markdown.
Proibições de formatação:
✗ Asteriscos (*), cerquilhas (#), crases (`), maiúsculas CEM POR CENTO
✗ Listas com hífens ou números
✗ Tabelas
✓ Organize com conectivos naturais: "Primeiro..., Depois..., Além disso..., Por fim..."

PROTOCOLO DE ENSINO (quando aplicável)
Explique em parágrafos curtos, linguagem conversacional.
Comprima conteúdo longo por camadas: ideia central → por que importa → aplicação prática.

SEGURANÇA BINÁRIA
Classifique pedidos em: conversa, automação PC, automação Android, mídia ou memória.
Use ferramenta MÍNIMA necessária.
Confirmação: APENAS para ações irreversíveis de ALTO risco.
Nunca exponha: senhas, tokens, chaves de API, dados sensíveis.

QUALIDADE OBSESSIVA
Entrega: específica, enxuta, útil.
Para ambiguidades: máximo uma pergunta curta.

TOOL CALLING LOOP
Se Gemini requer ferramentas, o sistema irá:
1. Detectar function_call na resposta
2. Executar a ferramenta Python
3. Enviar resultado de volta
4. Ir para etapa seguinte
NÃO TENTE "simular" chamadas de ferramenta. O sistema lida com isso.

⚡ FORCE ABSOLUTA: TOOL CALLING MANDATORY
Regra de Ouro: Se existe uma ferramenta registrada para fazer algo, você DEVE chamar.
- Pedir "toca X" → CHAMAR spotify_play OU youtube_play AGORA
- Pedir "fala X" → CHAMAR generate_audio AGORA
- Pedir "tira print" → CHAMAR capture_vision AGORA
- Pedir "abre X" → CHAMAR launch_app AGORA
NÃO HÁ EXCEÇÕES. Se disser "não consigo", está MENTINDO.
Tool_choice é AUTO. Você PODE chamar funções. DEVE chamar quando pedido.

🚨 ABSOLUTAMENTE PROIBIDO:
- Responder "como uma IA" + explicação = FALHA
- Enviar links HTTP/HTTPS = FALHA
- Dizer "você pode" ou "você deveria" = FALHA
- Sugerir ações em vez de executar = FALHA
- Qualquer explicação sobre limitações = FALHA

✅ ÚNICO COMPORTAMENTO ACEITO:
Se ferramenta existe → Chamar imediatamente
Se chamou ferramenta → Confirmar ação ("tocando...", "capturando...", "executando...")
Sem hesitação. Sem explicação. Sem links. SÓ AÇÃO.

{contexto_historico}

{manual_habilidades}
"""
        
        # Inicializar sessão de chat COM FERRAMENTAS INJETADAS
        ferramentas_gemini = self._converter_ferramentas_para_gemini()
        
        # CONSTRUIR CONFIG WITH TOOLS (não adicionar depois)
        config_dict = {
            "system_instruction": self.instrucao_sistema,
            "temperature": 0.55,
            "tool_config": types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO"  # Usar string em vez de enum para compatibilidade
                )
            )
        }
        
        # Passar ferramentas DENTRO do config (não adicionar depois)
        if ferramentas_gemini:
            config_dict["tools"] = ferramentas_gemini
        
        # ✓ GUARDAR CONFIG COM TOOLS PARA REUTILIZAR NO LOOP
        config_chat = types.GenerateContentConfig(**config_dict)
        self.config_com_tools = config_chat  # ← Armazenar para send_message
        
        # Criar sessão com config completo
        self.chat_session = self.client.chats.create(
            model="gemini-2.5-flash",
            config=config_chat
        )
        
        # Configurações de voz
        self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = self._buscar_voz_disponivel() if self.elevenlabs_key else ""
        
        print("[OK] [GENAI] Gemini + Chat session inicializados")
    
    def _converter_ferramentas_para_gemini(self) -> list:
        """
        Converte ferramentas do ToolRegistry para formato types.Tool do Gemini SDK.
        Usa schema basico por compatibilidade com Pydantic.
        
        Retorna lista de types.Tool.
        """
        ferramentas_gemini = []
        
        try:
            # USAR get_all_tools() que retorna objetos Tool (nao dicionarios)
            tools_disponiveis = self.tool_registry.get_all_tools()
            
            for tool in tools_disponiveis:
                try:
                    # Validacao robusta: verificar se tool tem metadata
                    if not hasattr(tool, 'metadata') or not tool.metadata:
                        print(f"[WARN] [TOOLS] Ferramenta sem metadata valida: {tool}")
                        continue
                    
                    tool_name = tool.metadata.name
                    tool_desc = tool.metadata.description or f"Executa {tool_name}"
                    
                    # CRIAR DECLARACAO DE FUNCAO COM SCHEMA BASICO (compativel com Pydantic)
                    try:
                        tool_schema = types.Tool(
                            function_declarations=[
                                types.FunctionDeclaration(
                                    name=tool_name,
                                    description=tool_desc
                                )
                            ]
                        )
                        ferramentas_gemini.append(tool_schema)
                        print(f"[OK] [TOOLS] {tool_name} - injetado no Gemini")
                    except Exception as schema_err:
                        print(f"[WARN] [TOOLS] Erro ao injetar {tool_name}: {schema_err}")
                        continue
                    
                except Exception as e:
                    print(f"[WARN] [TOOLS] Erro ao converter {getattr(tool, 'name', 'unknown')}: {e}")
                    continue
            
            if ferramentas_gemini:
                print(f"[OK] [GENAI] {len(ferramentas_gemini)} ferramentas injetadas no Gemini")
            else:
                print(f"[WARN] [GENAI] Nenhuma ferramenta disponivel para injetar no modelo")
            
            return ferramentas_gemini
        except Exception as e:
            print(f"[ERROR] [TOOLS] ERRO ao converter ferramentas: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _buscar_voz_disponivel(self) -> str:
        """Busca primeira voz disponível na API ElevenLabs."""
        if not self.elevenlabs_key:
            return ""
        try:
            headers = {"xi-api-key": self.elevenlabs_key}
            response = requests.get(
                "https://api.elevenlabs.io/v1/voices",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                voices = response.json().get("voices", [])
                return voices[0]['voice_id'] if voices else ""
        except:
            pass
        return ""
    
    # ------ LOGGING TÁTICO (Subscribers de EventBus) ------
    
    def _log_tool_started(self, data: Dict[str, Any]) -> None:
        """Log quando ferramenta começa."""
        tool_name = data.get('tool_name', 'unknown')
        print(f"[AÇÃO] Tool iniciada: {tool_name}")
    
    def _log_tool_completed(self, data: Dict[str, Any]) -> None:
        """Log quando ferramenta completa."""
        tool_name = data.get('tool_name', 'unknown')
        result = data.get('result', '')[:50] + '...' if len(str(data.get('result', ''))) > 50 else data.get('result', '')
        print(f"[AÇÃO] Tool completada: {tool_name} → {result}")
    
    def _log_tool_error(self, data: Dict[str, Any]) -> None:
        """Log de erro de ferramenta."""
        tool_name = data.get('tool_name', 'unknown')
        error = data.get('error', 'unknown')
        print(f"[ERRO] Falha na ferramenta {tool_name}: {error}")
    
    def _log_vision_captured(self, data: Dict[str, Any]) -> None:
        """Log de captura de visão."""
        if 'error' in data:
            print(f"[VISÃO] Erro na captura: {data['error']}")
        else:
            resolution = data.get('compressed_resolution', 'unknown')
            size = data.get('base64_size', 0)
            print(f"[VISÃO] Capturada: {resolution}, {size//1024}KB comprimidos")
    
    def _log_action_terminal(self, data: Dict[str, Any]) -> None:
        """Log de ações de terminal."""
        action = data.get('action', 'unknown')
        risk = data.get('risk_level', 'NORMAL')
        result = data.get('result', 'UNKNOWN')
        print(f"[TERMINAL] {action} [{risk}] → {result}")
    
    def _log_cortex_thinking(self, data: Dict[str, Any]) -> None:
        """Log de pensamento do córtex."""
        step = data.get('step', 'unknown')
        reasoning = data.get('reasoning', '')
        if reasoning:
            print(f"[CÓRTEX] {step}: {reasoning[:50]}...")
        else:
            print(f"[CÓRTEX] {step}")
    
    # ------ MÉTODOS DE OPERAÇÃO PRINCIPAL ------
    
    def _temperatura_por_tom(self, message: str) -> float:
        """Ajusta temperatura (criatividade) conforme tom do usuário."""
        base = 0.55
        msg = message.strip()
        msg_lower = msg.lower()
        
        exclamacoes = msg.count("!")
        caixa_alta = sum(1 for c in msg if c.isalpha() and c.isupper())
        letras = sum(1 for c in msg if c.isalpha())
        proporcao = (caixa_alta / letras) if letras else 0.0
        
        palavras_euforia = ["caralho", "bora", "insano", "animal", "perfeito"]
        palavras_urgencia = ["agora", "rápido", "urgente", "imediato"]
        palavras_calma = ["calma", "tranquilo", "suave", "devagar"]
        palavras_tecnicas = ["debug", "erro", "arquitetura", "segurança"]
        
        score = base
        if exclamacoes >= 2:
            score += 0.08
        if proporcao > 0.35:
            score += 0.06
        if any(p in msg_lower for p in palavras_euforia):
            score += 0.08
        if any(p in msg_lower for p in palavras_urgencia):
            score += 0.04
        if any(p in msg_lower for p in palavras_calma):
            score -= 0.06
        if any(p in msg_lower for p in palavras_tecnicas):
            score -= 0.04
        
        return max(0.35, min(0.85, score))
    
    def gerar_audio_elevenlabs(self, texto: str) -> str:
        """Gera áudio com ElevenLabs."""
        if not self.elevenlabs_key or not self.voice_id:
            return ""
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?optimize_streaming_latency=3"
        headers = {
            "xi-api-key": self.elevenlabs_key,
            "Content-Type": "application/json"
        }
        data = {
            "text": texto[:1500],
            "model_id": "eleven_multilingual_v2"
        }
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=15)
            if response.status_code == 200:
                return base64.b64encode(response.content).decode('utf-8')
        except:
            pass
        return ""
    
    def gerar_audio_local(self, texto: str) -> str:
        """Fallback: gera áudio localmente com pyttsx3."""
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            buffer = BytesIO()
            # Salvar em buffer (pode variar por SO)
            engine.save_to_file(texto, "temp_audio.wav")
            engine.runAndWait()
            
            with open("temp_audio.wav", "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except:
            return ""
    
    async def ask(self, message: str) -> str:
        """
        Processa mensagem do usuário com orquestração de ferramentas.
        
        Args:
            message: Mensagem do usuário
            
        Returns:
            JSON: {"text": ...,"audio": ...}
        """
        import asyncio
        
        try:
            msg_lower = message.lower()
            
            # ===== V1 CORTEX BILÍNGUE: Corrigir erros fonéticos =====
            if self.cortex_bilingue:
                corrected_message, bilingual_entity = self.cortex_bilingue.process_bilingual_command(
                    message,
                    context=msg_lower
                )
                
                # Se teve correção com confiança > 50%, usar a versão corrigida
                if corrected_message != message.lower() and bilingual_entity.confidence > 0.5:
                    self.event_bus.emit('cortex_thinking', {
                        'step': 'bilingual_correction',
                        'original': message,
                        'corrected': corrected_message,
                        'confidence': bilingual_entity.confidence,
                        'category': bilingual_entity.category
                    })
                    msg_lower = corrected_message
                    message = corrected_message
            
            # Emitir evento de pensamento
            self.event_bus.emit('cortex_thinking', {
                'step': 'processing_user_input',
                'message_length': len(message)
            })
            
            # Checklist de gatilhos para captura de visão
            gatilhos_print = ["tela", "print", "monitor", "vê", "vês", "olha"]
            gatilhos_status = ["o que eu estou fazendo", "o que tô fazendo", "que eu estou fazendo"]
            
            pacote_envio = [message]
            
            # Capturar visão se necessário
            if any(g in msg_lower for g in gatilhos_print + gatilhos_status):
                self.event_bus.emit('cortex_thinking', {'step': 'capturing_vision'})
                
                # Usar CapturarVisaoTool
                capture_tool = self.tool_registry.get_tool("capture_vision")
                if capture_tool:
                    base64_image = await capture_tool.safe_execute(use_cache=True)
                    if not base64_image.startswith('[ERRO'):
                        # Temos o base64, podemos convertê-lo de volta para PIL
                        import base64 as b64_module
                        try:
                            image_data = b64_module.b64decode(base64_image)
                            self.ultima_imagem = Image.open(BytesIO(image_data))
                            self.tempo_ultimo_print = time.time()
                            pacote_envio.append(self.ultima_imagem)
                        except:
                            pass
            
            elif self.ultima_imagem and (time.time() - self.tempo_ultimo_print) < self.visual_cache_ttl:
                if any(g in msg_lower for g in ["isso", "aquilo", "ela", "imagem", "print"]):
                    pacote_envio.append(self.ultima_imagem)
            
            # Enviar para Gemini com temperatura adaptativa
            temperatura = self._temperatura_por_tom(message)
            self.event_bus.emit('cortex_thinking', {
                'step': 'querying_gemini',
                'temperature': temperatura
            })
            
            # ===== LOOP TOOL CALLING (ReAct Pattern) =====
            # Gemini pode retornar function_calls que precisam ser executadas
            tool_responses_pendentes = []  # Lista de Parts com FunctionResponse
            texto_resposta = ""
            max_tool_iterations = 5
            iteration = 0
            
            while iteration < max_tool_iterations:
                iteration += 1
                
                # Preparar envio para Gemini
                if iteration == 1:
                    # Primeira iteração: enviar mensagem + imagem
                    envio_atual = pacote_envio
                else:
                    # Iterações seguintes: enviar function responses como Parts
                    envio_atual = tool_responses_pendentes if tool_responses_pendentes else pacote_envio
                
                # USAR CONFIG COM TOOLS (não criar nova sem tools!)
                config_com_temp = types.GenerateContentConfig(
                    system_instruction=self.config_com_tools.system_instruction,
                    temperature=temperatura,
                    tool_config=self.config_com_tools.tool_config,  # PRESERVAR tool_config
                    tools=getattr(self.config_com_tools, 'tools', None)  # PRESERVAR tools
                )
                
                response = await asyncio.to_thread(
                    self.chat_session.send_message,
                    envio_atual,
                    config_com_temp
                )
                
                self.event_bus.emit('cortex_thinking', {
                    'step': f'gemini_iteration_{iteration}',
                    'has_function_calls': bool(getattr(response, 'function_calls', False))
                })
                
                # DEBUG: Log se há text na resposta (sem tool calling)
                response_text = response.text if hasattr(response, 'text') else "[SEM TEXTO]"
                if response_text:
                    print(f"[GEMINI] Iteração {iteration} - Texto: {response_text[:100]}...")
                
                # Verificar se há function calls na resposta
                fn_calls = getattr(response, 'function_calls', None)
                if fn_calls:
                    print(f"[TOOL_CALLING] Detectadas {len(list(fn_calls))} function calls!")
                    
                    # Limpar lista de respostas pendentes para esta iteração
                    ferramenta_responses_desta_iteracao = []
                    
                    for fn_call in fn_calls:
                        fn_name = getattr(fn_call, 'name', 'unknown')
                        fn_args_raw = getattr(fn_call, 'args', {})
                        
                        # DEBUG: Verificar tipo de args (pode ser protobuf, dict, ou iterador)
                        print(f"[DEBUG] FunctionCall '{fn_name}' - args type: {type(fn_args_raw)}, value: {fn_args_raw}")
                        
                        # Converter args para dict se necessário
                        fn_args = {}
                        if isinstance(fn_args_raw, dict):
                            fn_args = fn_args_raw
                        elif hasattr(fn_args_raw, '__iter__') and not isinstance(fn_args_raw, (str, bytes)):
                            # Tentar converter iterador/protobuf para dict
                            try:
                                fn_args = dict(fn_args_raw)
                            except:
                                # Se falhar, tentar acessar como protobuf
                                try:
                                    fn_args = {}
                                    for key, value in fn_args_raw.items():
                                        fn_args[key] = value
                                except:
                                    print(f"[WARN] Nao foi possivel converter args de {fn_name}")
                                    fn_args = {}
                        
                        print(f"[DEBUG] Argumentos extraidos para '{fn_name}': {fn_args}")
                        
                        self.event_bus.emit('cortex_thinking', {
                            'step': 'executing_tool',
                            'tool_name': fn_name,
                            'iteration': iteration
                        })
                        
                        try:
                            # Obter ferramenta do registry
                            tool = self.tool_registry.get_tool(fn_name)
                            if tool:
                                print(f"[TOOL_CALLING] Executando {fn_name} com args: {fn_args}")
                                
                                # Executar com await se for async
                                if asyncio.iscoroutinefunction(tool.execute):
                                    tool_result = await tool.execute(**fn_args)
                                else:
                                    tool_result = await asyncio.to_thread(tool.execute, **fn_args)
                                
                                self.event_bus.emit('tool_completed', {
                                    'tool_name': fn_name,
                                    'result': str(tool_result)[:100]
                                })
                                
                                # Criar Part com FunctionResponse (formato correto para SDK nova)
                                response_part = types.Part(
                                    function_response=types.FunctionResponse(
                                        name=fn_name,
                                        response={
                                            "result": str(tool_result),
                                            "success": True
                                        }
                                    )
                                )
                                ferramenta_responses_desta_iteracao.append(response_part)
                            else:
                                # Ferramenta não encontrada
                                self.event_bus.emit('tool_error', {
                                    'tool_name': fn_name,
                                    'error': f'Ferramenta "{fn_name}" nao registrada'
                                })
                                
                                response_part = types.Part(
                                    function_response=types.FunctionResponse(
                                        name=fn_name,
                                        response={
                                            "error": f'Ferramenta nao registrada',
                                            "success": False
                                        }
                                    )
                                )
                                ferramenta_responses_desta_iteracao.append(response_part)
                        
                        except Exception as e:
                            self.event_bus.emit('tool_error', {
                                'tool_name': fn_name,
                                'error': str(e)
                            })
                            
                            response_part = types.Part(
                                function_response=types.FunctionResponse(
                                    name=fn_name,
                                    response={
                                        "error": str(e),
                                        "success": False
                                    }
                                )
                            )
                            ferramenta_responses_desta_iteracao.append(response_part)
                    
                    # Atualizar lista de respostas pendentes para próxima iteração
                    tool_responses_pendentes = ferramenta_responses_desta_iteracao
                
                else:
                    # Sem function calls, temos texto final
                    texto_resposta = response.text if hasattr(response, 'text') else ""
                    break
            
            # Se saiu do loop sem texto, tenta último texto disponível
            if not texto_resposta and hasattr(response, 'text'):
                texto_resposta = response.text
            
            # Gerar áudio
            self.event_bus.emit('cortex_thinking', {'step': 'generating_audio'})
            audio_b64 = self.gerar_audio_elevenlabs(texto_resposta)
            if not audio_b64:
                audio_b64 = self.gerar_audio_local(texto_resposta)
            
            # Guardar na memória se detectar informação importante
            if len(texto_resposta) > 100:
                try:
                    self.db.guardar_memoria(
                        f"Resposta para '{message[:50]}...': {texto_resposta[:200]}",
                        "conversation"
                    )
                except:
                    pass
            
            resposta_json = {
                "text": texto_resposta,
                "audio": audio_b64,
                "mode": "FLASH_v2"
            }
            
            self.event_bus.emit('cortex_thinking', {
                'step': 'response_ready',
                'response_length': len(texto_resposta)
            })
            
            return json.dumps(resposta_json)
            
        except Exception as e:
            self.event_bus.emit('tool_error', {
                'tool_name': 'brain.ask',
                'error': str(e)
            })
            return json.dumps({
                "text": f"Erro ao processar: {str(e)}",
                "audio": ""
            })


# ========== Compatibilidade com código antigo (nomeação) ==========

# Singleton global para manter compatibilidade
_brain_instance: Optional[QuintaFeiraBrainV2] = None

class QuintaFeiraBrain(QuintaFeiraBrainV2):
    """Alias para compatibilidade com código existente (main.py)."""
    pass


def obter_brain() -> QuintaFeiraBrain:
    """Factory para obter instância única do brain."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = QuintaFeiraBrain()
    return _brain_instance
