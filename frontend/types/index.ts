/**
 * TYPES: Tipos Compartilhados do Frontend
 * ======================================
 * Espelha os DTOs do backend (backend/core/api/dtos.py)
 * Comunicação via Message Envelope Pattern
 */

// ===== MESSAGE ENVELOPE (Base) =====
/**
 * Padrão base para TODAS as mensagens WebSocket
 * Espelha: backend.core.api.dtos.MessageEnvelope
 */
export type MessageType =
  | 'user_message'
  | 'brain_response'
  | 'intermediate_status'
  | 'system_status'
  | 'audio_chunk'
  | 'error'
  | 'ping'
  | 'pong'
  | 'runtime_event';

export interface MessageEnvelope<T = Record<string, any>> {
  type: MessageType;
  payload: T;
  timestamp: string; // ISO8601Z
  request_id: string; // UUID
}

// ===== MESSAGE PAYLOADS (Entrada) =====

export interface UserMessagePayload {
  text: string;
  mode?: 'streaming' | 'deliberative' | 'interactive';
  vision_context?: Array<{ type: string; content: string }>;
  audio_context?: Record<string, any>;
}

export interface AudioChunkPayload {
  data: string; // base64
  format: string;
  is_final: boolean;
}

export interface PingPayload {
  // Vazio
}

// ===== MESSAGE PAYLOADS (Saída) =====

export interface BrainResponsePayload {
  text: string;
  mode?: string;
  confidence?: number;
  tools_used?: string[];
  execution_time_ms?: number;
  action_taken?: Record<string, any>;
}

export interface IntermediateStatusPayload {
  step: string; // 'thinking', 'processing', 'executing', etc
  progress: number; // 0-1
  details?: Record<string, any>;
}

export interface SystemStatusPayload {
  status: 'online' | 'offline' | 'degraded';
  autonomous_enabled?: boolean;
  active_connections?: number;
  timestamp_server?: string;
}

export interface ErrorPayload {
  error_code:
    | 'INVALID_INPUT'
    | 'TIMEOUT'
    | 'SERVICE_UNAVAILABLE'
    | 'POLICY_VIOLATION'
    | 'AUTHORIZATION_FAILED'
    | 'INTERNAL_ERROR'
    | 'JSON_PARSE_ERROR'
    | 'UNKNOWN_MESSAGE_TYPE';
  message: string;
  details?: Record<string, any>;
  retry_after_seconds?: number;
}

export interface PongPayload {
  received_at: string;
}

export interface RuntimeEventPayload {
  event_type: string;
  data: Record<string, any>;
}

// ===== UNION TYPES (Facilita type-safe dispatch) =====

export type IncomingMessageEnvelope =
  | MessageEnvelope<IntermediateStatusPayload>
  | MessageEnvelope<BrainResponsePayload>
  | MessageEnvelope<SystemStatusPayload>
  | MessageEnvelope<ErrorPayload>
  | MessageEnvelope<PongPayload>
  | MessageEnvelope<RuntimeEventPayload>;

export type OutgoingMessageEnvelope =
  | MessageEnvelope<UserMessagePayload>
  | MessageEnvelope<AudioChunkPayload>
  | MessageEnvelope<PingPayload>;

// ===== HISTORIA DE CHAT =====

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  tools_used?: string[];
  execution_time_ms?: number;
  error?: string;
}

// ===== ESTADOS =====

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

// --- Orb Visual State ---
export type OrbState = 'idle' | 'listening' | 'processing' | 'speaking'

// --- Hook Return Type ---

export interface UseQuintaFeira {
  isConnected: boolean;
  connectionStatus: ConnectionStatus;
  messages: ChatMessage[];
  intermediateStatus: IntermediateStatus | null;
  lastAiResponse: string | null;
  error: string | null;
  isLoading: boolean;
  sendMessage: (text: string, mode?: 'streaming' | 'deliberative' | 'interactive') => Promise<void>;
  ping: () => Promise<void>;
  disconnect: () => void;
}
