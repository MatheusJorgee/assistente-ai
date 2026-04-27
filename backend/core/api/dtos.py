"""
DATA TRANSFER OBJECTS (DTOs) - WebSocket Message Envelopes
===========================================================

Padroniza TODAS as mensagens entre Frontend (Next.js) e Backend (FastAPI).

Padrão Message Envelope:
- type: str (user_message, brain_response, system_status, audio_chunk, error, intermediate_status)
- payload: dict (dados específicos de cada tipo)
- timestamp: str (ISO8601 UTC)
- request_id: str (UUID para correlacionar request/response)

Benefício: Frontend sabe sempre que estrutura esperar.
Versioning: Se adicionar novo tipo, apenas estende a union, sem quebrar clientes antigos.

Padrão de Serialização:
- Entrada (Frontend → Backend): JSON puro
- Validação: Pydantic BaseModel (valida tipos, ranges, etc)
- Saída (Backend → Frontend): JSON serializado
"""

from pydantic import BaseModel, Field, UUID4
from typing import Optional, Dict, Any, Literal, List
from datetime import datetime
from uuid import UUID, uuid4
import enum


# ===== TIPOS ENUMERADOS PARA SEGURANÇA =====

class MessageType(str, enum.Enum):
    """Tipos de mensagens permitidas no protocolo WebSocket."""
    USER_MESSAGE = "user_message"
    BRAIN_RESPONSE = "brain_response"
    INTERMEDIATE_STATUS = "intermediate_status"
    SYSTEM_STATUS = "system_status"
    AUDIO_CHUNK = "audio_chunk"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class BrainMode(str, enum.Enum):
    """Modos de operação do Brain."""
    STREAMING = "streaming"      # Respostas em tempo real (padrão)
    DELIBERATIVE = "deliberative" # Resposta final apenas
    INTERACTIVE = "interactive"   # Pede confirmaçao antes de agir


class ErrorCode(str, enum.Enum):
    """Códigos de erro padronizados."""
    INVALID_INPUT = "INVALID_INPUT"
    TIMEOUT = "TIMEOUT"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    JSON_PARSE_ERROR = "JSON_PARSE_ERROR"
    UNKNOWN_MESSAGE_TYPE = "UNKNOWN_MESSAGE_TYPE"


# ===== BASE MESSAGE ENVELOPE =====

class MessageEnvelope(BaseModel):
    """
    Envelope base para TODAS as mensagens WebSocket.
    
    Garante que toda mensagem tem:
    - type: qual tipo de mensagem
    - payload: dados
    - timestamp: quando foi criada
    - request_id: para correlacionar request/response
    
    Exemplo:
    {
        "type": "user_message",
        "payload": {"text": "Qual é o seu nome?"},
        "timestamp": "2026-04-15T10:30:45.123456Z",
        "request_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    """
    type: MessageType
    payload: Dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    request_id: str = Field(default_factory=lambda: str(uuid4()))

    class Config:
        use_enum_values = False  # Keep enum objects, not strings


# ===== MENSAGENS DE ENTRADA (Frontend → Backend) =====

class UserMessagePayload(BaseModel):
    """Payload de mensagem do usuário."""
    text: str = Field(..., min_length=1, max_length=10000, description="Mensagem de texto")
    mode: BrainMode = Field(default=BrainMode.STREAMING, description="Modo de operação")
    vision_context: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Contexto visual (imagens recentes em base64)"
    )
    audio_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Contexto de áudio (transcrição, emoção, etc)"
    )


class AudioChunkPayload(BaseModel):
    """Payload de chunk de áudio (streaming de áudio do usuário)."""
    data: str = Field(..., description="Chunk de áudio em base64")
    format: str = Field(default="wav", description="Formato de áudio")
    is_final: bool = Field(default=False, description="É o último chunk?")


class PingPayload(BaseModel):
    """Payload de ping (keep-alive)."""
    pass


# ===== MENSAGENS DE SAÍDA (Backend → Frontend) =====

class BrainResponsePayload(BaseModel):
    """Payload de resposta do Brain."""
    text: str = Field(..., description="Texto da resposta")
    mode: str = Field(default="normal", description="Modo de resposta")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confiança da resposta")
    tools_used: List[str] = Field(default_factory=list, description="Ferramentas utilizadas")
    execution_time_ms: float = Field(default=0.0, description="Tempo de execução em ms")
    action_taken: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Ação automaticamente executada"
    )


class IntermediateStatusPayload(BaseModel):
    """Payload de status intermediário durante processamento."""
    step: str = Field(..., description="Nome do passo (ex: 'analyzing', 'thinking', 'executing')")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Progresso 0-1")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detalhes adicionais do passo"
    )


class SystemStatusPayload(BaseModel):
    """Payload de status do sistema."""
    status: Literal["online", "offline", "degraded"] = Field(
        default="online",
        description="Status geral"
    )
    autonomous_enabled: bool = Field(default=False, description="Loop autônomo estava ativo?")
    active_connections: int = Field(default=0, description="Conexões WebSocket ativas")
    timestamp_server: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class ErrorPayload(BaseModel):
    """Payload de erro."""
    error_code: ErrorCode = Field(
        default=ErrorCode.INTERNAL_ERROR,
        description="Código de erro"
    )
    message: str = Field(..., max_length=1000, description="Mensagem de erro")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detalhes adicionais"
    )
    retry_after_seconds: Optional[int] = Field(
        default=None,
        description="Se aplicável: segundos para retry"
    )


class PongPayload(BaseModel):
    """Payload de pong (resposta a ping)."""
    received_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ===== HELPERS PARA CRIAR MENSAGENS =====

class MessageFactory:
    """Factory para criar mensagens padronizadas."""

    @staticmethod
    def create_user_message(
        text: str,
        mode: BrainMode = BrainMode.STREAMING,
        request_id: Optional[UUID4] = None,
    ) -> MessageEnvelope:
        """Cria mensagem de usuário."""
        return MessageEnvelope(
            type=MessageType.USER_MESSAGE,
            payload={"text": text, "mode": mode.value},
            request_id=request_id or uuid4(),
        )

    @staticmethod
    def create_brain_response(
        text: str,
        tools_used: Optional[List[str]] = None,
        execution_time_ms: float = 0.0,
        request_id: Optional[UUID4] = None,
    ) -> MessageEnvelope:
        """Cria resposta do Brain."""
        return MessageEnvelope(
            type=MessageType.BRAIN_RESPONSE,
            payload={
                "text": text,
                "tools_used": tools_used or [],
                "execution_time_ms": execution_time_ms,
            },
            request_id=request_id or uuid4(),
        )

    @staticmethod
    def create_intermediate_status(
        step: str,
        progress: float = 0.0,
        request_id: Optional[UUID4] = None,
    ) -> MessageEnvelope:
        """Cria status intermediário."""
        return MessageEnvelope(
            type=MessageType.INTERMEDIATE_STATUS,
            payload={
                "step": step,
                "progress": progress,
            },
            request_id=request_id or uuid4(),
        )

    @staticmethod
    def create_error(
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[UUID4] = None,
    ) -> MessageEnvelope:
        """Cria mensagem de erro."""
        return MessageEnvelope(
            type=MessageType.ERROR,
            payload={
                "error_code": error_code.value,
                "message": message,
                "details": details or {},
            },
            request_id=request_id or uuid4(),
        )

    @staticmethod
    def create_pong(request_id: Optional[UUID4] = None) -> MessageEnvelope:
        """Cria resposta pong."""
        return MessageEnvelope(
            type=MessageType.PONG,
            payload={},
            request_id=request_id or uuid4(),
        )


# ===== VALIDADORES CUSTOMIZADOS =====

def validate_message_envelope(raw_json: Dict[str, Any]) -> MessageEnvelope:
    """
    Valida e converte raw JSON para MessageEnvelope.
    
    Lança ValueError se inválido.
    """
    try:
        return MessageEnvelope(**raw_json)
    except Exception as e:
        raise ValueError(f"JSON inválido: {str(e)}")


def validate_user_message_input(envelope: MessageEnvelope) -> UserMessagePayload:
    """
    Valida que um MessageEnvelope é mensagem de usuário válida.
    
    Lança ValueError se tipo errado ou payload inválido.
    """
    if envelope.type != MessageType.USER_MESSAGE:
        raise ValueError(f"Tipo esperado: user_message, recebido: {envelope.type}")
    
    try:
        return UserMessagePayload(**envelope.payload)
    except Exception as e:
        raise ValueError(f"Payload de user_message inválido: {str(e)}")
