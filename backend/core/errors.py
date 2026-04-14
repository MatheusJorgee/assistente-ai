"""
Errors.py: ExceÃ§Ãµes Customizadas do Backend
=============================================

PadrÃ£o: Hierarchy de ExceÃ§Ãµes + String representation clara

Responsabilidade:
- Definir exceÃ§Ãµes especÃ­ficas do domÃ­nio (IA, Motor, PersistÃªncia)
- Permitir tratamento diferenciado de erros
- Facilitar debug com mensagens clara e contexto

Uso:
    from .errors import ToolExecutionError, TerminalSecurityError
    
    try:
        result = registry.execute("meu_tool")
    except ToolExecutionError as e:
        logger.error(f"Tool error: {e}")
        # Avisar frontend de forma amigÃ¡vel
"""

from typing import Optional, Any, Dict


class QuintaFeirError(Exception):
    """
    ExceÃ§Ã£o base de toda a Quinta-Feira.
    
    Todos os erros do sistema herdam desta classe.
    Permite catch genÃ©rico vs tratamento especÃ­fico.
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Exporta erro para JSON (Ãºtil para respostas HTTP/WebSocket)."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"


# ===== ERROS DE CONFIGURAÃ‡ÃƒO =====

class ConfigurationError(QuintaFeirError):
    """Falha ao carregar ou validar configuraÃ§Ã£o."""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="CONFIG_ERROR",
            details=details
        )


# ===== ERROS DE FERRAMENTAS (Tool Registry) =====

class ToolError(QuintaFeirError):
    """Erro genÃ©rico ao executar ferramenta."""
    
    def __init__(self, tool_name: str, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=f"Tool '{tool_name}' falhou: {message}",
            error_code="TOOL_ERROR",
            details={"tool_name": tool_name, **(details or {})}
        )


class ToolNotFoundError(ToolError):
    """Ferramenta solicitada nÃ£o existe no registry."""
    
    def __init__(self, tool_name: str):
        super().__init__(
            tool_name=tool_name,
            message=f"Tool nÃ£o registrada",
            details={"error_type": "not_found"}
        )
        self.error_code = "TOOL_NOT_FOUND"


class ToolExecutionError(ToolError):
    """Falha na execuÃ§Ã£o de uma ferramenta."""
    
    def __init__(self, tool_name: str, original_error: Exception):
        super().__init__(
            tool_name=tool_name,
            message=str(original_error),
            details={"error_type": "execution", "original_error_type": type(original_error).__name__}
        )
        self.error_code = "TOOL_EXECUTION_ERROR"
        self.original_error = original_error


class ToolValidationError(ToolError):
    """ParÃ¢metros de ferramenta invÃ¡lidos."""
    
    def __init__(self, tool_name: str, reason: str):
        super().__init__(
            tool_name=tool_name,
            message=f"ValidaÃ§Ã£o falhou: {reason}",
            details={"error_type": "validation"}
        )
        self.error_code = "TOOL_VALIDATION_ERROR"


# ===== ERROS DE TERMINAL / AUTOMAÃ‡ÃƒO =====

class TerminalError(QuintaFeirError):
    """Erro ao executar comando no terminal."""
    
    def __init__(self, message: str, command: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="TERMINAL_ERROR",
            details={"command": command, **(details or {})}
        )


class TerminalSecurityError(TerminalError):
    """Comando bloqueado por razÃµes de seguranÃ§a."""
    
    def __init__(self, command: str, reason: str):
        super().__init__(
            message=f"Comando bloqueado: {reason}",
            command=command,
            details={"error_type": "security", "blocked_command": command}
        )
        self.error_code = "TERMINAL_SECURITY_ERROR"


class TerminalTimeoutError(TerminalError):
    """Comando excedeu timeout."""
    
    def __init__(self, command: str, timeout_seconds: int):
        super().__init__(
            message=f"Timeout apÃ³s {timeout_seconds}s",
            command=command,
            details={"error_type": "timeout", "timeout_seconds": timeout_seconds}
        )
        self.error_code = "TERMINAL_TIMEOUT_ERROR"


# ===== ERROS DE IA / LLM =====

class LLMError(QuintaFeirError):
    """Erro ao comunicar com LLM (Gemini, etc)."""
    
    def __init__(self, message: str, model: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="LLM_ERROR",
            details={"model": model, **(details or {})}
        )


class LLMAuthenticationError(LLMError):
    """Erro de autenticaÃ§Ã£o com LLM (ex: API key invÃ¡lida)."""
    
    def __init__(self, model: str, reason: str = "API key invÃ¡lida ou expirada"):
        super().__init__(
            message=reason,
            model=model,
            details={"error_type": "authentication"}
        )
        self.error_code = "LLM_AUTH_ERROR"


class LLMTimeoutError(LLMError):
    """LLM demorou muito para responder."""
    
    def __init__(self, model: str, timeout_seconds: int):
        super().__init__(
            message=f"Timeout apÃ³s {timeout_seconds}s",
            model=model,
            details={"error_type": "timeout", "timeout_seconds": timeout_seconds}
        )
        self.error_code = "LLM_TIMEOUT_ERROR"


# ===== ERROS DE PERSISTÃŠNCIA =====

class PersistenceError(QuintaFeirError):
    """Erro ao acessar banco de dados."""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="PERSISTENCE_ERROR",
            details=details
        )


class DatabaseConnectionError(PersistenceError):
    """Falha ao conectar ao banco."""
    
    def __init__(self, database_path: str, reason: Optional[str] = None):
        super().__init__(
            message=f"Falha ao conectar em {database_path}" + (f": {reason}" if reason else ""),
            details={"error_type": "connection", "database_path": database_path}
        )
        self.error_code = "DB_CONNECTION_ERROR"


# ===== ERROS DE VISÃƒO =====

class VisionError(QuintaFeirError):
    """Erro ao processar visÃ£o/imagens."""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="VISION_ERROR",
            details=details
        )


class ScreenCaptureError(VisionError):
    """Erro ao capturar tela."""
    
    def __init__(self, reason: str):
        super().__init__(
            message=f"Falha ao capturar tela: {reason}",
            details={"error_type": "capture"}
        )
        self.error_code = "SCREEN_CAPTURE_ERROR"


# ===== ERROS DE VOZ =====

class VoiceError(QuintaFeirError):
    """Erro ao processar voz/TTS."""
    
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="VOICE_ERROR",
            details={"provider": provider, **(details or {})}
        )


class ElevenLabsError(VoiceError):
    """Erro especÃ­fico do ElevenLabs."""
    
    def __init__(self, message: str, reason: Optional[str] = None):
        super().__init__(
            message=f"ElevenLabs: {message}" + (f" ({reason})" if reason else ""),
            provider="elevenlabs",
            details={"error_type": "elevenlabs"}
        )
        self.error_code = "ELEVENLABS_ERROR"

