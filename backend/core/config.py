"""
Config.py: CentralizaÃ§Ã£o de VariÃ¡veis de Ambiente e ConfiguraÃ§Ãµes
============================================================

PadrÃ£o: Singleton + Factory

Responsabilidade:
- Carregar .env com fallback para path absoluto
- Fornecer interface Ãºnica e type-safe para todas as configs
- Validar secrets obrigatÃ³rios na inicializaÃ§Ã£o

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
    ConfiguraÃ§Ã£o centralizada do sistema (Singleton Pattern).
    
    Carrega .env com estratÃ©gia de fallback:
    1. Procura .env no diretÃ³rio do arquivo (backend/)
    2. Procura em ../
    3. Procura em ../../
    4. Carrega de variÃ¡veis de ambiente do sistema
    
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
        self._initialize_values()
        self._validate_required()
        self._initialized = True
    
    def _load_env(self) -> None:
        """Carrega .env com fallback para path absoluto."""
        # EstratÃ©gia: comeÃ§ar do __file__ (backend/core/config.py)
        current = Path(__file__).parent.parent  # backend/
        
        # Tentar 3 nÃ­veis acima
        for _ in range(3):
            env_path = current / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                return
            current = current.parent
    
    def _initialize_values(self) -> None:
        """Inicializa atributos de configuraÃ§Ã£o."""
        # ===== LLM =====
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.55"))
        self.LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))
        
        # ===== VOZ / TTS =====
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
        self.ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
        self.TTS_ENABLED = os.getenv("TTS_ENABLED", "true").lower() == "true"
        
        # ===== SPOTIFY =====
        self.SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        
        # ===== YOUTUBE =====
        self.YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
        
        # ===== SEGURANÃ‡A / TERMINAL =====
        self.SECURITY_PROFILE = os.getenv("SECURITY_PROFILE", "trusted-local")  # trusted-local | strict
        self.ALLOW_TERMINAL_COMMANDS = os.getenv("ALLOW_TERMINAL_COMMANDS", "true").lower() == "true"
        self.TERMINAL_TIMEOUT_SECONDS = int(os.getenv("TERMINAL_TIMEOUT_SECONDS", "30"))
        
        # ===== VISÃƒO / CAPTURA DE TELA =====
        self.VISION_ENABLED = os.getenv("VISION_ENABLED", "true").lower() == "true"
        self.VISION_COMPRESSION_QUALITY = int(os.getenv("VISION_COMPRESSION_QUALITY", "70"))
        self.VISION_MAX_DIMENSION = int(os.getenv("VISION_MAX_DIMENSION", "1280"))
        
        # ===== LOGGING =====
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        
        # ===== SERVIDOR =====
        self.BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
        self.BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
        self.FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
        
        # ===== BANCO DE DADOS =====
        self.DATABASE_PATH = os.getenv("DATABASE_PATH", "backend/memoria_quinta_feira.db")
        
        # ===== CACHE / TEMP =====
        self.CACHE_DIR = os.getenv("CACHE_DIR", "backend/.cache")
        self.TEMP_DIR = os.getenv("TEMP_DIR", "backend/temp_vision")
    
    def _validate_required(self) -> None:
        """Valida que secrets obrigatÃ³rios estÃ£o presentes."""
        required = {
            "GEMINI_API_KEY": self.GEMINI_API_KEY,
        }
        
        missing = [k for k, v in required.items() if not v]
        
        if missing:
            raise EnvironmentError(
                f"VariÃ¡veis de ambiente obrigatÃ³rias ausentes: {', '.join(missing)}\n"
                f"Confirme que .env estÃ¡ carregado corretamente."
            )
    
    def to_dict(self) -> dict:
        """Exporta configuraÃ§Ã£o como dicionÃ¡rio (Ãºtil para logging seguro)."""
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
    """Retorna instÃ¢ncia singleton de Config."""
    return Config()

