/**
 * useQuintaFeira: Custom Hook - Gerenciador WebSocket
 * ====================================================
 *
 * Responsabilidades:
 * - Gerenciar ciclo de vida do WebSocket
 * - Conectar/desconectar com reconexão automática (exponential backoff)
 * - Gerenciar histórico de mensagens
 * - Gerenciar status intermediário (thinking, processing, etc)
 * - Type-safe: Espelha DTOs do backend
 *
 * FILOSOFIA: Transport layer (não faz lógica de negócio)
 * - Apenas Orquestra comunicação com backend
 * - Callbacks/Context no componente pai fazem trabalho real
 *
 * CRÍTICO: Cleanup adequado para:
 * - Evitar vazamentos de memória
 * - Evitar múltiplas conexões em modo dev (React StrictMode)
 * - Fechar timers de reconexão
 */

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type {
  MessageEnvelope,
  MessageType,
  ChatMessage,
  ConnectionStatus,
  UserMessagePayload,
  OutgoingMessageEnvelope,
  IncomingMessageEnvelope,
  IntermediateStatus,
  RuntimeEventPayload,
} from '@/types';
import type { ActiveMedia } from '@/components/MediaPlayer';

interface UseQuintaFeira {
  isConnected: boolean;
  connectionStatus: ConnectionStatus;
  messages: ChatMessage[];
  intermediateStatus: IntermediateStatus | null;
  lastAiResponse: string | null;
  error: string | null;
  isLoading: boolean;
  activeMedia: ActiveMedia | null;
  clearMedia: () => void;
  sendMessage: (text: string, mode?: 'streaming' | 'deliberative' | 'interactive') => Promise<void>;
  ping: () => Promise<void>;
  disconnect: () => void;
}

interface Config {
  wsUrl?: string;
  autoReconnect?: boolean;
  maxReconnectAttempts?: number;
  baseReconnectDelay?: number; // ms
  maxReconnectDelay?: number; // ms
}

/**
 * Hook principal para comunicação com Brain via WebSocket
 *
 * Uso:
 * const { isConnected, messages, sendMessage } = useQuintaFeira();
 *
 * Exemplo:
 * await sendMessage('Qual é seu nome?', 'streaming');
 */
export function useQuintaFeira({
  wsUrl = 'ws://127.0.0.1:8000/ws/quinta',
  autoReconnect = true,
  maxReconnectAttempts = 5,
  baseReconnectDelay = 1000,
  maxReconnectDelay = 30000,
}: Config = {}): UseQuintaFeira {
  // ===== ESTADOS =====
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [intermediateStatus, setIntermediateStatus] = useState<IntermediateStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastAiResponse, setLastAiResponse] = useState<string | null>(null);
  const [activeMedia, setActiveMedia] = useState<ActiveMedia | null>(null);

  const clearMedia = useCallback(() => setActiveMedia(null), []);

  // ===== REFS (não causam re-render) =====
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isConnectingRef = useRef(false); // Previne múltiplas tentativas simultâneas
  const messageQueueRef = useRef<OutgoingMessageEnvelope[]>([]);
  const cleanupRef = useRef(false); // Flag para cleanup no unmount

  // ===== EXPONENTIAL BACKOFF =====
  /**
   * Calcula delay com exponential backoff:
   * delay = min(baseDelay * (2 ^ attemptNumber), maxDelay)
   *
   * Exemplo (base=1000, max=30000):
   * - Tentativa 0: 1000ms
   * - Tentativa 1: 2000ms
   * - Tentativa 2: 4000ms
   * - Tentativa 3: 8000ms
   * - Tentativa 4: 16000ms
   * - Tentativa 5+: 30000ms (máximo)
   */
  const getReconnectDelay = useCallback((attempt: number): number => {
    const exponentialDelay = baseReconnectDelay * Math.pow(2, attempt);
    return Math.min(exponentialDelay, maxReconnectDelay);
  }, [baseReconnectDelay, maxReconnectDelay]);

  // ===== GERAR UUID PARA REQUEST_ID =====
  const generateUUID = useCallback((): string => {
    return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  // ===== CRIAR MESSAGE ENVELOPE =====
  const createMessageEnvelope = useCallback(
    <T extends Record<string, any>>(type: MessageType, payload: T): MessageEnvelope<T> => ({
      type,
      payload,
      timestamp: new Date().toISOString(),
      request_id: generateUUID(),
    }),
    [generateUUID]
  );

  // ===== CONECTAR WEBSOCKET =====
  const connect = useCallback(() => {
    if (cleanupRef.current) {
      console.log('[WS] Cleanup está em progresso, abortando conexão');
      return;
    }

    if (isConnectingRef.current) {
      console.log('[WS] Já conectando, ignorando tentativa duplicada');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WS] WebSocket já está OPEN');
      return;
    }

    try {
      isConnectingRef.current = true;
      setConnectionStatus('connecting');
      console.log(`[WS] Conectando em: ${wsUrl}`);

      const ws = new WebSocket(wsUrl);

      // ===== ON OPEN =====
      ws.onopen = () => {
        console.log('[WS] ✓ Conectado ao backend');
        wsRef.current = ws;
        isConnectingRef.current = false;
        setIsConnected(true);
        setConnectionStatus('connected');
        setError(null);
        reconnectCountRef.current = 0;

        // Enviar mensagens enfileiradas
        while (messageQueueRef.current.length > 0 && ws.readyState === WebSocket.OPEN) {
          const queued = messageQueueRef.current.shift();
          if (queued) {
            ws.send(JSON.stringify(queued));
            console.log('[WS] Mensagem enfileirada enviada');
          }
        }
      };

      // ===== ON MESSAGE =====
      ws.onmessage = (event: MessageEvent) => {
        try {
          const envelope = JSON.parse(event.data) as IncomingMessageEnvelope;
          console.log('[WS] Mensagem recebida:', envelope.type);

          // Despachar por tipo de mensagem
          switch (envelope.type) {
            case 'intermediate_status': {
              // Status intermediário durante processamento
              const status = envelope as MessageEnvelope<IntermediateStatus>;
              setIntermediateStatus(status.payload);
              console.log(`[WS] Status: ${status.payload.step} (${(status.payload.progress * 100).toFixed(0)}%)`);
              break;
            }

            case 'brain_response': {
              // Resposta final do Brain
              const response = envelope as any;
              const msg: ChatMessage = {
                id: `assistant_${Date.now()}`,
                role: 'assistant',
                content: response.payload.text || '',
                timestamp: Date.now(),
                tools_used: response.payload.tools_used,
                execution_time_ms: response.payload.execution_time_ms,
              };
              setMessages(prev => [...prev, msg]);
              setIntermediateStatus(null); // Limpar status intermediário
              setIsLoading(false);
              console.log('[WS] Resposta recebida:', msg.content.substring(0, 50) + '...');
              break;
            }

            case 'error': {
              // Erro do backend
              const errorEnv = envelope as MessageEnvelope<{ error_code: string; message: string }>;
              const errorMsg = errorEnv.payload.message;
              setError(errorMsg);
              setIsLoading(false);
              setIntermediateStatus(null);
              console.error('[WS] Erro recebido:', errorMsg);
              break;
            }

            case 'pong': {
              // Resposta a ping (keep-alive)
              console.log('[WS] Pong recebido (keep-alive OK)');
              break;
            }

            case 'runtime_event': {
              // Gateway pode entregar `event_type`/`data` no root OU dentro de `payload`.
              const anyEnv = envelope as any;
              const event_type: string =
                anyEnv.event_type ?? anyEnv.payload?.event_type ?? '';
              const data: Record<string, any> =
                anyEnv.data ?? anyEnv.payload?.data ?? anyEnv.payload ?? {};

              if (event_type === 'manual_command_completed') {
                setLastAiResponse(data.response ?? null);
              } else if (event_type === 'action_failed') {
                setLastAiResponse(data.reason ?? null);
              } else if (event_type === 'media_playback_requested') {
                // Backend delega reprodução para o cliente.
                setActiveMedia({
                  provider: data.provider ?? 'youtube',
                  video_id: data.video_id,
                  video_url: data.video_url,
                  search_query: data.search_query,
                  audio_base64: data.audio_base64,
                  autoplay: data.autoplay !== false,
                  title: data.title ?? data.search_query,
                });
              } else if (event_type === 'media_playback_stopped') {
                setActiveMedia(null);
              }
              break;
            }

            default: {
              console.warn('[WS] Tipo de mensagem desconhecido:', envelope.type);
            }
          }
        } catch (err) {
          console.error('[WS] Erro ao parsear mensagem:', err);
          setError('Erro ao processar resposta do servidor');
        }
      };

      // ===== ON ERROR =====
      ws.onerror = () => {
        console.warn(`[WS] Falha ao conectar em: ${wsUrl} — aguardando reconexão`);
        isConnectingRef.current = false;
        setConnectionStatus('error');
        setError('Erro na conexão WebSocket');
      };

      // ===== ON CLOSE =====
      ws.onclose = () => {
        console.log('[WS] Desconectado do backend');
        wsRef.current = null;
        isConnectingRef.current = false;
        setIsConnected(false);
        setConnectionStatus('disconnected');

        if (!cleanupRef.current && autoReconnect && reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          const delay = getReconnectDelay(reconnectCountRef.current - 1);
          console.log(
            `[WS] Reconectando em ${delay}ms (tentativa ${reconnectCountRef.current}/${maxReconnectAttempts})`
          );

          // Agendaar reconexão
          reconnectTimerRef.current = setTimeout(() => {
            if (!cleanupRef.current) {
              connect();
            }
          }, delay);
        } else if (reconnectCountRef.current >= maxReconnectAttempts) {
          console.error(`[WS] Falha após ${maxReconnectAttempts} tentativas`);
          setError('Não foi possível conectar ao backend');
        }
      };
    } catch (err) {
      console.error('[WS] Erro ao conectar:', err);
      isConnectingRef.current = false;
      setConnectionStatus('error');
      setError('Erro ao conectar ao WebSocket');
    }
  }, [wsUrl, autoReconnect, maxReconnectAttempts, getReconnectDelay]);

  // ===== DESCONECTAR =====
  const disconnect = useCallback(() => {
    console.log('[WS] Desconectando manualmente...');

    // Lipar timers
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    // Fechar WebSocket
    if (wsRef.current) {
      wsRef.current.close(1000, 'Desconexão manual');
      wsRef.current = null;
    }

    isConnectingRef.current = false;
    setIsConnected(false);
    setConnectionStatus('disconnected');
  }, []);

  // ===== ENVIAR MENSAGEM =====
  const sendMessage = useCallback(
    async (text: string, mode: 'streaming' | 'deliberative' | 'interactive' = 'streaming'): Promise<void> => {
      if (!text.trim()) {
        console.warn('[WS] Texto vazio, ignorando');
        return;
      }

      // Adicionar ao histórico (lado do usuário)
      const userMsg: ChatMessage = {
        id: `user_${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, userMsg]);

      // Criar Message Envelope
      const payload: UserMessagePayload = {
        text,
        mode,
      };
      const envelope = createMessageEnvelope('user_message', payload);

      // Enviar (ou enfileirar se desconectado)
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify(envelope));
          setIsLoading(true);
          console.log('[WS] Mensagem enviada:', text.substring(0, 50) + '...');
        } catch (err) {
          console.error('[WS] Erro ao enviar:', err);
          setError('Erro ao enviar mensagem');
          // Remover mensagem do histórico se falhar
          setMessages(prev => prev.filter(m => m.id !== userMsg.id));
        }
      } else {
        console.log('[WS] WebSocket não está conectado, enfileirando...');
        messageQueueRef.current.push(envelope);
        setError('Desconectado. Mensagem será enviada ao reconectar.');
      }
    },
    [createMessageEnvelope]
  );

  // ===== PING (Keep-Alive) =====
  const ping = useCallback(async (): Promise<void> => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn('[WS] WebSocket não está conectado');
      return;
    }

    const envelope = createMessageEnvelope('ping', {});
    wsRef.current.send(JSON.stringify(envelope));
    console.log('[WS] Ping enviado');
  }, [createMessageEnvelope]);

  // ===== EFEITO: CONECTAR AO MONTAR =====
  useEffect(() => {
    cleanupRef.current = false;
    connect();

    // ===== CLEANUP NO UNMOUNT =====
    return () => {
      console.log('[WS] Cleanup: desmontando componente');
      cleanupRef.current = true;

      // Cancelar reconexões pendentes
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      // Fechar WebSocket
      if (wsRef.current) {
        wsRef.current.close(1000, 'Componente desmontado');
        wsRef.current = null;
      }

      isConnectingRef.current = false;
    };
  }, []); // Dependências VAZIAS - roda apenas uma vez

  return {
    isConnected,
    connectionStatus,
    messages,
    intermediateStatus,
    lastAiResponse,
    error,
    isLoading,
    activeMedia,
    clearMedia,
    sendMessage,
    ping,
    disconnect,
  };
}

