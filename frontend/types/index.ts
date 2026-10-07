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
  | 'runtime_event'
  // Aprovação de ações críticas (backend/core/policy/approvals.py)
  | 'approval_requested' // servidor -> tela: "posso fazer isto?"
  | 'approval_response'  // tela -> servidor: { approval_id, permitido }
  | 'approval_resolved'  // servidor -> telas: fecha o cartão (outra aba respondeu / expirou)
  // Progresso em tempo real e parada (backend/core/runtime_progress.py)
  | 'tool_call_start'    // servidor -> tela: "estou usando X"
  | 'tool_call_result'   // servidor -> tela: "terminei X" ({ ok, duration_ms })
  | 'stop'               // tela -> servidor: pare o que está fazendo e descarte a fila
  | 'run_cancelled'      // servidor -> tela: parei ({ descartadas })
  // Streaming da resposta (backend/core/runtime_progress.py)
  | 'text_delta'         // servidor -> tela: pedaço da resposta ({ text })
  | 'text_reset'         // servidor -> tela: descarte o texto mostrado (era só preâmbulo)
  // Hologramas (backend/core/holo/schema.py)
  | 'holo_show'          // servidor -> tela: abre o holograma (payload = HoloPayload)
  | 'holo_hide'         // servidor -> tela: fecha o holograma
  | 'voice_trace'       // tela -> servidor: { request_id, primeiro_audio_ms }
  | 'spoken_report';     // tela -> servidor: { falado } o que tocou antes de ser cortada

export interface MessageEnvelope<T = Record<string, unknown>> {
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
  audio_context?: Record<string, unknown>;
}

export interface AudioChunkPayload {
  data: string; // base64
  format: string;
  is_final: boolean;
}

export interface PingPayload {
  _?: never; // sem campos
}

// ===== MESSAGE PAYLOADS (Saída) =====

export interface BrainResponsePayload {
  text: string;
  mode?: string;
  confidence?: number;
  tools_used?: string[];
  execution_time_ms?: number;
  action_taken?: Record<string, unknown>;
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

/** Pedido de aprovação de uma ação crítica (o backend espera a resposta, e nega se expirar). */
export interface ApprovalRequest {
  approval_id: string;
  ferramenta: string;
  risco: 'leitura' | 'escrita' | 'critica';
  resumo: string; // o que vai acontecer, em português (ex.: "Enviar WhatsApp para X: “...”")
  origem: string; // chat | telegram | agendado | desconhecida
  expira_em_s: number;
  recebido_em: number; // Date.now() do cliente, base do contador regressivo
  /** O pedido veio DEPOIS de ler conteúdo de terceiros (WhatsApp, web, documento...): a UI avisa. */
  contaminado?: boolean;
  fontes?: string[]; // ex.: ['mensagens do WhatsApp', 'a web']
}

/** Payloads das mensagens novas do servidor (todos os campos opcionais: o backend é a fonte). */
export interface ApprovalRequestedPayload {
  approval_id?: string;
  ferramenta?: string;
  risco?: ApprovalRequest['risco'];
  resumo?: string;
  origem?: string;
  expira_em_s?: number;
  contaminado?: boolean;
  fontes?: string[];
}

export interface ApprovalResolvedPayload {
  approval_id?: string;
  resultado?: 'aprovado' | 'negado' | 'expirou' | 'cancelado';
}

export interface ToolCallPayload {
  tool?: string;
  label?: string;
  ok?: boolean;
  duration_ms?: number;
}

export interface RunCancelledPayload {
  descartadas?: number;
}

export interface TextDeltaPayload {
  text?: string;
}

/** O que a Quinta está fazendo AGORA (ferramenta em uso), para a faixa "Agora". */
export interface AgoraActivity {
  tool: string;
  label: string; // ex.: "pesquisando na web"
  since: number; // Date.now() do cliente, base do cronômetro
}

/** Quando a Quinta pergunta antes de agir (backend: GET/POST /autonomia). */
export type AutonomyMode = 'perguntar_sempre' | 'so_perigoso' | 'autonoma';

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

// ===== ALIASES DE COMPATIBILIDADE =====

export type Message = ChatMessage;
export type IntermediateStatus = IntermediateStatusPayload;

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


// ===== HOLOGRAMAS (espelha backend/core/holo/schema.py; a tela revalida com parseHoloPayload) =====

export type HoloLink = { rotulo: string; url: string };
export type HoloFonte = { nome: string; url: string };
export type HoloStatus = 'ok' | 'parcial' | 'indisponivel';
export type HoloPoi = {
  id?: string;
  nome: string;
  categoria?: string;
  descricao?: string;
  lat?: number;
  lon?: number;
  link_mapa: string;
  wikipedia?: string;
};
export type HoloPainel =
  | { tipo: 'resumo'; texto: string; status: HoloStatus }
  | { tipo: 'hospedagem'; itens: HoloPoi[]; links: HoloLink[]; aviso: string; status: HoloStatus }
  | { tipo: 'atracoes'; itens: (HoloPoi & { id: string; lat: number; lon: number })[]; status: HoloStatus }
  | {
      tipo: 'cronograma';
      dias: { n: number; titulo: string; blocos: { periodo: 'manha' | 'tarde' | 'noite'; poi_ids: string[] }[] }[];
      metodo: 'proximidade' | 'llm';
      aviso: string;
      status: HoloStatus;
    }
  | {
      tipo: 'clima';
      rotulo: string;
      origem: 'previsao' | 'ano_anterior';
      dias: { data: string; tmin: number; tmax: number; chuva_mm: number }[];
      status: HoloStatus;
    }
  | { tipo: 'dicas'; secoes: { titulo: string; itens: string[] }[]; status: HoloStatus };

/** Polígono GeoJSON MultiPolygon: [poligono][anel][ponto][lon, lat] */
export type HoloMultiPoligono = number[][][][];

export interface HoloPayload {
  v: 1;
  id: string;
  tipo: 'mapa' | 'viagem';
  titulo: string;
  geo: {
    lat: number;
    lon: number;
    kind: 'ponto' | 'area';
    bbox?: [number, number, number, number]; // sul, norte, oeste, leste
    polygon?: HoloMultiPoligono;
  };
  paineis: HoloPainel[];
  fontes: HoloFonte[];
}
