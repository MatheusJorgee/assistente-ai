/**
 * useQuintaFeira: Custom Hook - Gerenciador WebSocket
 * ====================================================
 * 
 * Responsabilidade ÚNICA:
 * - Gerenciar conexão WebSocket com backend
 * - Enviar/receber mensagens JSON
 * - Manter histórico de mensagens
 * - Lidar com reconexão automática
 * - Gerenciar estados de conexão
 * 
 * FILOSOFIA: Este hook é BURRO
 * - Não pensa
 * - Não valida lógica
 * - Apenas orquestra comunicação com backend
 * - Callbacks no componente pai fazem o trabalho real
 */

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type { Message, WebSocketMessage, ConnectionStatus } from '@/types';

interface Config {
  url?: string;
  onMessage?: (message: BrainResponse) => void;
  onError?: (error: string) => void;
  autoReconnect?: boolean;
  maxReconnectAttempts?: number;
}

interface BrainResponse {
  text: string;
  audio?: string;
  mode?: 'responding' | 'listening' | 'thinking';
  timestamp?: string;
}

export function useQuintaFeira({
  url = 'ws://localhost:8000/ws',
  onMessage,
  onError,
  autoReconnect = true,
  maxReconnectAttempts = 5,
}: Config = {}) {
  // --- Estados ---
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- Refs (não causam re-render) ---
  const ws = useRef<WebSocket | null>(null);
  const sessionId = useRef<string>('');
  const reconnectCount = useRef(0);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);
  const hasConnected = useRef(false);  // ← Previne múltiplas conexões

  // Atualizar refs quando callbacks mudam
  useEffect(() => {
    onMessageRef.current = onMessage;
    onErrorRef.current = onError;
  }, [onMessage, onError]);

  // --- Gerar/Recuperar Session ID (estável globalmente) ---
  useEffect(() => {
    if (!sessionId.current) {
      // Tentar recuperar sessionId do sessionStorage (persiste durante a sessão do navegador)
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('quintaFeira_sessionId') : null;
      
      if (stored) {
        sessionId.current = stored;
        console.log(`[WS] SessionId recuperado do storage: ${stored}`);
      } else {
        // Gerar novo se não existir
        sessionId.current = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('quintaFeira_sessionId', sessionId.current);
        }
        console.log(`[WS] Novo SessionId gerado: ${sessionId.current}`);
      }
    }
  }, []);

  // --- Conectar WebSocket ---
  const connect = useCallback(() => {
    // CRÍTICO: Prevenir múltiplas conexões
    if (hasConnected.current) {
      console.log('[WS] Já conectado, ignorando reconexão');
      return;
    }

    if (ws.current?.readyState === WebSocket.OPEN) {
      console.log('[WS] WebSocket já está OPEN');
      return; // Já conectado
    }

    try {
      hasConnected.current = true;  // Marcar como conectando
      setStatus('connecting');
      const wsUrl = `${url}/${sessionId.current}`;
      
      console.log(`[WS] Conectando em: ${wsUrl}`);
      ws.current = new WebSocket(wsUrl);

      // --- Evento: Conexão Aberta ---
      ws.current.onopen = () => {
        console.log('[WS] Conectado ao backend');
        setIsConnected(true);
        setStatus('connected');
        setError(null);
        reconnectCount.current = 0;
      };

      // --- Evento: Mensagem Recebida ---
      ws.current.onmessage = (event: MessageEvent) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data);
          console.log('[WS] Mensagem recebida:', data);

          // Se for resposta do cérebro
          if (data.type === 'response' || data.text) {
            const brainResponse: BrainResponse = {
              text: data.text || '',
              audio: data.audio,
              mode: data.mode as any,
              timestamp: data.timestamp,
            };

            // Callback do componente pai
            onMessageRef.current?.(brainResponse);

            // Adicionar ao histórico
            setMessages(prev => [
              ...prev,
              {
                id: `ai_${Date.now()}`,
                role: 'assistant',
                content: brainResponse.text,
                timestamp: Date.now(),
                audio: brainResponse.audio,
              },
            ]);
          }

          setIsLoading(false);
        } catch (err) {
          console.error('[WS] Erro ao parsear mensagem:', err);
          setError('Erro ao processar resposta do servidor');
        }
      };

      // --- Evento: Erro ---
      ws.current.onerror = (event: Event) => {
        console.error('[WS] Erro WebSocket:', event);
        setStatus('error');
        setError('Erro na conexão WebSocket');
        onErrorRef.current?.('Falha na conexão WebSocket');
      };

      // --- Evento: Conexão Fechada ---
      ws.current.onclose = () => {
        console.log('[WS] Desconectado do backend');
        hasConnected.current = false;  // ← RESET para permitir reconexão
        setIsConnected(false);
        setStatus('disconnected');

        // Reconectar automaticamente
        if (autoReconnect && reconnectCount.current < maxReconnectAttempts) {
          reconnectCount.current += 1;
          const delay = Math.min(1000 * reconnectCount.current, 5000); // Backoff exponencial
          console.log(`[WS] Reconectando em ${delay}ms (tentativa ${reconnectCount.current}/${maxReconnectAttempts})`);

          reconnectTimer.current = setTimeout(() => {
            connect();
          }, delay);
        } else if (reconnectCount.current >= maxReconnectAttempts) {
          setError('Falha ao conectar ao backend após várias tentativas');
          onErrorRef.current?.('Backend offline');
        }
      };
    } catch (err) {
      console.error('[WS] Erro ao conectar:', err);
      setStatus('error');
      setError('Erro ao conectar ao WebSocket');
      onErrorRef.current?.(String(err));
    }
  }, [url, autoReconnect, maxReconnectAttempts]);

  // --- Desconectar ---
  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
    }

    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }

    hasConnected.current = false; // Reset para permitir reconexão manual
    setIsConnected(false);
    setStatus('disconnected');
  }, []);

  // --- Enviar Mensagem ---
  const sendMessage = useCallback(async (text: string) => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
      setError('Não conectado ao backend');
      return;
    }

    if (!text.trim()) {
      return;
    }

    try {
      // Adicionar ao histórico (lado do usuário)
      setMessages(prev => [
        ...prev,
        {
          id: `user_${Date.now()}`,
          role: 'user',
          content: text,
          timestamp: Date.now(),
        },
      ]);

      setIsLoading(true);

      // Enviar ao backend
      const payload: WebSocketMessage = {
        type: 'chat',
        payload: text,
        message: text,
        session_id: sessionId.current,
        timestamp: new Date().toISOString(),
      };

      ws.current.send(JSON.stringify(payload));
      console.log('[WS] Mensagem enviada:', payload);
    } catch (err) {
      console.error('[WS] Erro ao enviar mensagem:', err);
      setError('Erro ao enviar mensagem');
      setIsLoading(false);
      onErrorRef.current?.(String(err));
    }
  }, []);

  // --- Conectar ao montar (apenas UMA VEZ) ---
  useEffect(() => {
    connect();

    return () => {
      // Limpar ao desmontar
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      // NÃO resetar hasConnected aqui - deixar a reconexão automática cuidar
    };
  }, []); // Dependências VAZIAS - roda apenas uma vez

  return {
    isConnected,
    status,
    messages,
    isLoading,
    error,
    sendMessage,
    disconnect,
  };
}
