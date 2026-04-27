"""
Backend Core: Fundação do Sistema
==================================

Exporte as abstrações e utilitários fundamentais que todo módulo usa.

Uso (exemplos):
    from . import get_config, get_logger
    from . import QuintaFeirError, ToolExecutionError
    from . import LLMProvider, Message, Response
    
    cfg = get_config()
    logger = get_logger(__name__)
    adapter = GeminiAdapter()
"""

# ===== CONFIGURAÇÃO =====
from .config import Config, get_config

# ===== LOGGING =====
from .logger import configure_logging, get_logger

# ===== ERROS =====
from .errors import (
    QuintaFeirError,
    # Config
    ConfigurationError,
    # Tools
    ToolError,
    ToolNotFoundError,
    ToolExecutionError,
    ToolValidationError,
    # Terminal
    TerminalError,
    TerminalSecurityError,
    TerminalTimeoutError,
    # LLM
    LLMError,
    LLMAuthenticationError,
    LLMTimeoutError,
    # Persistence
    PersistenceError,
    DatabaseConnectionError,
    # Vision
    VisionError,
    ScreenCaptureError,
    # Voice
    VoiceError,
    ElevenLabsError,
)

# ===== LLM ABSTRACTION =====
from .llm_provider import (
    LLMProvider,
    Message,
    Response,
    ToolDefinition,
    ToolChoice,
    FunctionCallingOrchestrator,
)
from .gemini_provider import GeminiAdapter

# ===== HOST CAPABILITY LAYER =====
from .host import (
    CommandExecutionResult,
    DirectoryEntry,
    FileDeleteResult,
    FileReadResult,
    FileSystemAdapter,
    FileWriteResult,
    PowerShellCommand,
    PowerShellExecutor,
    ProcessAdapter,
    ProcessInfo,
    ProcessStartRequest,
    ProcessStartResult,
    ProcessStopResult,
)
from .policy import (
    OSAction,
    PolicyContext,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRule,
    create_default_policy_engine,
)
from .telemetry import AuditEvent, AuditLogger, ToolCallTelemetry
from .loop import ActionOrchestrator, AsyncEventBus, AutonomousWorker, LoopEvent, ManualCommandHandler
from .audio import (
    AudioAdapter,
    AudioAvailability,
    Pyttsx3TTSAdapter,
    SpeechRecognitionSTTAdapter,
    VoiceCommandOrchestrator,
    WakeWordListener,
)
from .database import Database, Event, Image, Message, get_database
from .memory import MemoryManager

__all__ = [
    # Config
    "Config",
    "get_config",
    # Logging
    "configure_logging",
    "get_logger",
    # Errors
    "QuintaFeirError",
    "ConfigurationError",
    "ToolError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolValidationError",
    "TerminalError",
    "TerminalSecurityError",
    "TerminalTimeoutError",
    "LLMError",
    "LLMAuthenticationError",
    "LLMTimeoutError",
    "PersistenceError",
    "DatabaseConnectionError",
    "VisionError",
    "ScreenCaptureError",
    "VoiceError",
    "ElevenLabsError",
    # LLM Abstraction
    "LLMProvider",
    "Message",
    "Response",
    "ToolDefinition",
    "ToolChoice",
    "FunctionCallingOrchestrator",
    "GeminiAdapter",
    # Host Capability Layer
    "CommandExecutionResult",
    "DirectoryEntry",
    "FileDeleteResult",
    "FileReadResult",
    "FileSystemAdapter",
    "FileWriteResult",
    "PowerShellCommand",
    "PowerShellExecutor",
    "ProcessAdapter",
    "ProcessInfo",
    "ProcessStartRequest",
    "ProcessStartResult",
    "ProcessStopResult",
    # Policy
    "OSAction",
    "PolicyContext",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyEngine",
    "PolicyRule",
    "create_default_policy_engine",
    # Telemetry
    "AuditEvent",
    "AuditLogger",
    "ToolCallTelemetry",
    # Autonomous Loop
    "AsyncEventBus",
    "AutonomousWorker",
    "LoopEvent",
    "ActionOrchestrator",
    "ManualCommandHandler",
    # Audio
    "AudioAdapter",
    "AudioAvailability",
    "Pyttsx3TTSAdapter",
    "SpeechRecognitionSTTAdapter",
    "WakeWordListener",
    "VoiceCommandOrchestrator",
    # Database
    "Database",
    "Message",
    "Event",
    "Image",
    "get_database",
    # Memory
    "MemoryManager",
]

