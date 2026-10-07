"""
Config.py: Centralização de Variáveis de Ambiente e Configurações
============================================================

Padrão: Singleton + Factory

Responsabilidade:
- Carregar .env com fallback para path absoluto
- Fornecer interface única e type-safe para todas as configs
- Validar secrets obrigatórios na inicialização

Uso:
    from .config import Config
    cfg = Config()
    print(cfg.GEMINI_API_KEY)  # Carregado automaticamente
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """
    Configuração centralizada do sistema (Singleton Pattern).
    
    Carrega .env com estratégia de fallback:
    1. Procura .env no diretório do arquivo (backend/)
    2. Procura em ../
    3. Procura em ../../
    4. Carrega de variáveis de ambiente do sistema
    
    Isso garante que funcione:
    - python backend/main.py (cwd = root)
    - cd backend && python main.py (cwd = backend)
    - uvicorn main:app (cwd = qualquer lugar)
    """
    
    _instance: Optional['Config'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._load_env()
        # Chaves guardadas no Gerenciador de Credenciais do Windows completam as que faltam no .env
        try:
            from .host.segredos import carregar_no_ambiente
            carregar_no_ambiente()
        except Exception:
            pass
        self._initialize_values()
        self._validate_required()
        self._initialized = True
    
    def _load_env(self) -> None:
        """Carrega .env com fallback para path absoluto."""
        # Estratégia: começar do __file__ (backend/core/config.py)
        current = Path(__file__).parent.parent  # backend/
        
        # Tentar 3 níveis acima
        for _ in range(3):
            env_path = current / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                return
            current = current.parent
    
    def _initialize_values(self) -> None:
        """Inicializa atributos de configuração."""
        # ===== LLM =====
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))
        # Raciocínio (thinking) do Gemini 2.5: -1 = dinâmico (pensa mais em perguntas
        # difíceis, menos em comandos simples), 0 = desligado (rápido/reativo), N = teto fixo.
        self.THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "-1"))

        # ===== CUSTO x INTELIGENCIA =====
        # Politica por funcao (core/llm_policy.py): tarefas de fundo raciocinam pouco ou nada
        # e classificadores usam o modelo lite. LLM_POLICY_ENABLED=false volta ao comportamento antigo.
        self.LLM_POLICY_ENABLED = os.getenv("LLM_POLICY_ENABLED", "true").lower() == "true"
        self.GEMINI_MODEL_LITE = os.getenv("GEMINI_MODEL_LITE", "gemini-2.5-flash-lite")
        # Modelo forte: so no MODO AGENTE (objetivo multi-passo). STRONG_MODEL_ENABLED=false desliga.
        self.GEMINI_MODEL_STRONG = os.getenv("GEMINI_MODEL_STRONG", "gemini-2.5-pro")
        self.STRONG_MODEL_ENABLED = os.getenv("STRONG_MODEL_ENABLED", "true").lower() == "true"
        # Tetos de raciocinio (o dinamico -1 nao tem teto e chegava a milhares de tokens).
        self.COMPLEX_THINKING_BUDGET = int(os.getenv("COMPLEX_THINKING_BUDGET", "4096"))
        self.STRONG_THINKING_BUDGET = int(os.getenv("STRONG_THINKING_BUDGET", "8192"))
        # Contexto variavel (memoria, hora, humor...) vai no fim da mensagem do usuario em vez
        # do system prompt: o prefixo (system+tools ~9.4k tokens) fica identico e o cache
        # automatico do Google pode reaproveita-lo. false = comportamento antigo.
        self.CONTEXT_IN_USER_TURN = os.getenv("CONTEXT_IN_USER_TURN", "true").lower() == "true"
        # Teto de caracteres da saida de uma tool que volta pro LLM (ela e reenviada a cada volta do loop).
        self.TOOL_OUTPUT_MAX_CHARS = int(os.getenv("TOOL_OUTPUT_MAX_CHARS", "7000"))
        self.LLM_LEDGER_ENABLED = os.getenv("LLM_LEDGER_ENABLED", "true").lower() == "true"
        # Streaming da resposta do chat: o texto chega na tela (e vira voz, frase a frase) enquanto
        # o modelo ainda escreve. Só vale para quem escuta o progresso (chat pelo WebSocket).
        # false = espera a resposta inteira, como antes.
        self.STREAM_RESPONSES = os.getenv("STREAM_RESPONSES", "true").lower() == "true"
        # Tempo máximo (s) de UMA volta em streaming; o modelo forte ganha o dobro.
        self.STREAM_TIMEOUT_SECONDS = float(os.getenv("STREAM_TIMEOUT_SECONDS", "30"))

        # ===== VOZ / TTS =====
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
        self.ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
        self.TTS_ENABLED = os.getenv("TTS_ENABLED", "true").lower() == "true"
        # Voz neural padrão (gratuita, sem chave): Edge TTS. Feminina brasileira.
        # Outras opções: pt-BR-ThalitaMultilingualNeural, pt-BR-YaraNeural...
        self.EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "pt-BR-FranciscaNeural")
        self.EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+8%")
        
        # ===== SPOTIFY =====
        self.SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        
        # ===== YOUTUBE =====
        self.YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

        # ===== PROATIVIDADE =====
        # Monitor proativo (avisos de bateria/CPU/RAM/clima/pausa). true/false.
        self.PROACTIVE_ENABLED = os.getenv("PROACTIVE_ENABLED", "true").lower() == "true"

        # ===== ORGANISMO VIVO =====
        # Pulso de presença: de tempos em tempos ela decide sozinha se vale
        # comentar algo (quase sempre escolhe silêncio). Intervalo em minutos.
        self.PRESENCE_ENABLED = os.getenv("PRESENCE_ENABLED", "true").lower() == "true"
        self.PRESENCE_INTERVAL_MINUTES = int(os.getenv("PRESENCE_INTERVAL_MINUTES", "50"))
        # Horário de silêncio (só avisos críticos falam). Padrão: 1h às 7h.
        self.QUIET_HOURS_START = int(os.getenv("QUIET_HOURS_START", "1"))
        self.QUIET_HOURS_END = int(os.getenv("QUIET_HOURS_END", "7"))
        # Reflexão (auto-aprendizado): relê conversas/hábitos e destila fatos.
        self.REFLECTION_ENABLED = os.getenv("REFLECTION_ENABLED", "true").lower() == "true"
        self.REFLECTION_INTERVAL_HOURS = float(os.getenv("REFLECTION_INTERVAL_HOURS", "6"))
        # Curiosidade (aprendizado via internet): ela pesquisa sozinha sobre os
        # interesses/projetos do Matheus, com guarda de segurança (SearchGuard:
        # temas vetados, PII removida, cota diária de pesquisas).
        self.CURIOSITY_ENABLED = os.getenv("CURIOSITY_ENABLED", "true").lower() == "true"
        self.CURIOSITY_INTERVAL_HOURS = float(os.getenv("CURIOSITY_INTERVAL_HOURS", "3"))
        self.CURIOSITY_MAX_PER_RUN = int(os.getenv("CURIOSITY_MAX_PER_RUN", "3"))
        self.CURIOSITY_MAX_PER_DAY = int(os.getenv("CURIOSITY_MAX_PER_DAY", "12"))
        # Memória vetorial (embeddings Gemini): recall por significado.
        self.EMBEDDINGS_ENABLED = os.getenv("EMBEDDINGS_ENABLED", "true").lower() == "true"
        # Triagem proativa do WhatsApp: avisa quando chega mensagem relevante.
        # Só roda se o Edge do WhatsApp já estiver aberto (não lança sozinho).
        self.WA_TRIAGE_ENABLED = os.getenv("WA_TRIAGE_ENABLED", "true").lower() == "true"
        self.WA_TRIAGE_INTERVAL_MINUTES = int(os.getenv("WA_TRIAGE_INTERVAL_MINUTES", "30"))
        # Co-piloto financeiro: cota a watchlist e avisa movimento relevante.
        self.FINANCE_ENABLED = os.getenv("FINANCE_ENABLED", "true").lower() == "true"
        self.FINANCE_INTERVAL_MINUTES = int(os.getenv("FINANCE_INTERVAL_MINUTES", "20"))
        # Modo foco: segura avisos não-críticos durante jogo em tela cheia ou chamada.
        self.FOCUS_MODE_ENABLED = os.getenv("FOCUS_MODE_ENABLED", "true").lower() == "true"
        # Google Agenda via endereço iCal privado (sem OAuth). Vazio = desligado.
        self.CALENDAR_ICS_URL = os.getenv("CALENDAR_ICS_URL", "")
        # Escuta ambiente: confiança mínima pra ela assumir que a fala foi com ela
        # (sem wake word). Mais alto = mais conservadora (responde menos à toa).
        self.AMBIENT_CONFIDENCE_THRESHOLD = float(os.getenv("AMBIENT_CONFIDENCE_THRESHOLD", "0.6"))
        # Briefing ritual: bom dia completo (clima+notícias+agenda+mercado+lembretes)
        # e fechamento à noite, em vez da saudação curta.
        self.BRIEFING_RITUAL_ENABLED = os.getenv("BRIEFING_RITUAL_ENABLED", "true").lower() == "true"
        # Alertas de disco/armazenamento (disco cheio, Downloads). Pode desligar de vez.
        self.DISK_ALERTS_ENABLED = os.getenv("DISK_ALERTS_ENABLED", "true").lower() == "true"
        # Notificações nativas do Windows (toast) — alcança mesmo com navegador fechado.
        self.NATIVE_NOTIFICATIONS_ENABLED = os.getenv("NATIVE_NOTIFICATIONS_ENABLED", "true").lower() == "true"
        # Ela puxar assunto sozinha (como um amigo que manda mensagem do nada).
        self.CONVERSATION_STARTER_ENABLED = os.getenv("CONVERSATION_STARTER_ENABLED", "true").lower() == "true"
        # Discord: bot pra ver quem está online num servidor compartilhado (opcional).
        self.DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
        self.DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")

        # ===== REDES SOCIAIS / TELEGRAM =====
        # Bot criado no @BotFather. Com o token no .env, a Quinta-Feira passa a
        # conversar pelo celular e a mandar avisos quando o Matheus está longe.
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

        # ===== BUSCA WEB =====
        # Tavily (busca para IA, free tier em tavily.com). Opcional: sem ela,
        # o tool cai no scraping DuckDuckGo (best-effort, sujeito a rate-limit).
        self.TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

        # Pré-gate do pulso de presença: só chama o LLM se o contexto mudou (A4)
        self.PREGATE_ENABLED = os.getenv("PREGATE_ENABLED", "true").lower() not in ("0", "false", "no")

        # ===== HOLOGRAMAS =====
        # Sai para a internet: nome do lugar, coordenadas e datas da viagem (Nominatim, Overpass,
        # Wikivoyage/Wikipedia, Open-Meteo). Nenhuma chave necessaria.
        self.HOLO_ENABLED = os.getenv("HOLO_ENABLED", "true").lower() not in ("0", "false", "no")
        self.HOLO_CONTACT = os.getenv("HOLO_CONTACT", "")
        self.HOLO_DEADLINE_S = float(os.getenv("HOLO_DEADLINE_S", "14"))

        # ===== BRIEFING MATINAL =====
        self.OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
        self.BRIEFING_CITY = os.getenv("BRIEFING_CITY", "Sao Paulo,BR")
        self.BRIEFING_ON_STARTUP = os.getenv("BRIEFING_ON_STARTUP", "false").lower() == "true"
        self.BRIEFING_NEWS_COUNT = int(os.getenv("BRIEFING_NEWS_COUNT", "5"))

        # ===== SEGURANÇA / TERMINAL =====
        self.SECURITY_PROFILE = os.getenv("SECURITY_PROFILE", "trusted-local")  # trusted-local | strict
        self.ALLOW_TERMINAL_COMMANDS = os.getenv("ALLOW_TERMINAL_COMMANDS", "true").lower() == "true"
        self.TERMINAL_TIMEOUT_SECONDS = int(os.getenv("TERMINAL_TIMEOUT_SECONDS", "30"))
        
        # ===== VISÃO / CAPTURA DE TELA =====
        self.VISION_ENABLED = os.getenv("VISION_ENABLED", "true").lower() == "true"
        self.VISION_COMPRESSION_QUALITY = int(os.getenv("VISION_COMPRESSION_QUALITY", "70"))
        self.VISION_MAX_DIMENSION = int(os.getenv("VISION_MAX_DIMENSION", "1280"))
        
        # ===== LOGGING =====
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        
        # ===== SERVIDOR =====
        # SEGURANÇA: a Quinta tem terminal, WhatsApp e arquivos — só a própria máquina
        # deve alcançá-la. 0.0.0.0 expunha o WebSocket, sem senha, a toda a rede local.
        self.BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
        # Guarda de origem/host (core/api/local_guard.py): bloqueia páginas web de terceiros
        # falando com o backend pelo navegador (CSRF/WebSocket hijacking) e DNS rebinding.
        # Extras separados por vírgula, ex.: EXTRA_ALLOWED_ORIGINS=https://meu-tunel.ngrok.io
        self.LOCAL_GUARD_ENABLED = os.getenv("LOCAL_GUARD_ENABLED", "true").lower() == "true"
        # Teto de espera por resposta do brain no WebSocket do chat (segundos).
        # Inclui o tempo que ele leva para APROVAR ações críticas (até 60s cada), então 300.
        self.WS_BRAIN_TIMEOUT_SECONDS = float(os.getenv("WS_BRAIN_TIMEOUT_SECONDS", "300"))
        self.EXTRA_ALLOWED_ORIGINS = [
            o.strip() for o in os.getenv("EXTRA_ALLOWED_ORIGINS", "").split(",") if o.strip()
        ]
        self.EXTRA_ALLOWED_HOSTS = [
            h.strip() for h in os.getenv("EXTRA_ALLOWED_HOSTS", "").split(",") if h.strip()
        ]
        self.BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
        self.FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
        
        # ===== BANCO DE DADOS =====
        self.DATABASE_PATH = os.getenv("DATABASE_PATH", "backend/memoria_quinta_feira.db")
        
        # ===== CACHE / TEMP =====
        self.CACHE_DIR = os.getenv("CACHE_DIR", "backend/.cache")
        self.TEMP_DIR = os.getenv("TEMP_DIR", "backend/temp_vision")
    
    def _validate_required(self) -> None:
        """Valida que secrets obrigatórios estão presentes."""
        required = {
            "GEMINI_API_KEY": self.GEMINI_API_KEY,
        }
        
        missing = [k for k, v in required.items() if not v]
        
        if missing:
            raise EnvironmentError(
                f"Variáveis de ambiente obrigatórias ausentes: {', '.join(missing)}\n"
                f"Confirme que .env está carregado corretamente."
            )
    
    def to_dict(self) -> dict:
        """Exporta configuração como dicionário (útil para logging seguro)."""
        return {
            "GEMINI_MODEL": self.GEMINI_MODEL,
            "SECURITY_PROFILE": self.SECURITY_PROFILE,
            "LOG_LEVEL": self.LOG_LEVEL,
            "TTS_ENABLED": self.TTS_ENABLED,
            "VISION_ENABLED": self.VISION_ENABLED,
        }
    
    def __repr__(self) -> str:
        return f"<Config instance at {id(self)}>"


# Factory function (preferido para imports simples)
def get_config() -> Config:
    """Retorna instância singleton de Config."""
    return Config()

