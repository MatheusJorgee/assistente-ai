/**
 * TYPES: Tipos Compartilhados do Frontend
 * ======================================
 * Definições TypeScript para WebSocket, Mensagens e Respostas
 */

// --- WebSocket Message Types ---

export interface WebSocketMessage {
  type: 'chat' | 'connection' | 'response' | 'error' | 'audio' | 'streaming' | 'complete';
  payload?: string;
  message?: string;
  text?: string;
  audio?: string;
  base64?: string;
  mode?: 'responding' | 'listening' | 'thinking';
  status?: 'connected' | 'connected' | 'error';
  session_id?: string;
  error?: string;
  timestamp?: string;
  [key: string]: any;
}

// --- Chat Message Type ---

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  audio?: string; // Base64
}

// --- Brain Response Type ---

export interface BrainResponse {
  text: string;
  audio?: string; // Base64
  mode?: 'responding' | 'listening' | 'thinking';
  timestamp?: string;
}

// --- Status Type ---

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

// --- Orb Visual State ---
export type OrbState = 'idle' | 'listening' | 'processing' | 'speaking'

// --- Hook Return Type ---

export interface UseQuintaFeira {
  isConnected: boolean;
  status: ConnectionStatus;
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  disconnect: () => void;
}
