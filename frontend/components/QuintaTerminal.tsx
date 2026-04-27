/**
 * QuintaTerminal: Componente Visual para Comunicação com Brain
 * ============================================================
 *
 * Renderiza:
 * - Histórico de mensagens (usuário + assistente)
 * - Status intermediário durante processamento
 * - Input para enviar mensagens
 * - Indicadores de conexão e erro
 *
 * Pragmático: Usa TailwindCSS, sem dependências pesadas
 * Acessível: Suporta keyboard (Enter para enviar)
 * Responsivo: Mobile-first design
 */

'use client';

import React, { useRef, useEffect, useState } from 'react';
import { useQuintaFeira } from '@/hooks/useQuintaFeira';
import type { ChatMessage, ConnectionStatus } from '@/types';

interface QuintaTerminalProps {
  /**
   * URL do WebSocket (padrão: ws://localhost:8000/ws/quinta)
   */
  wsUrl?: string;

  /**
   * Callback quando conexão muda
   */
  onConnectionChange?: (connected: boolean) => void;

  /**
   * Callback quando há erro
   */
  onError?: (error: string) => void;
}

export function QuintaTerminal({
  wsUrl,
  onConnectionChange,
  onError,
}: QuintaTerminalProps) {
  // ===== HOOK PRINCIPAL =====
  const {
    isConnected,
    connectionStatus,
    messages,
    intermediateStatus,
    error,
    isLoading,
    sendMessage,
    disconnect,
  } = useQuintaFeira({
    wsUrl,
  });

  // ===== ESTADOS LOCAIS =====
  const [inputValue, setInputValue] = useState('');
  const [mode, setMode] = useState<'streaming' | 'deliberative' | 'interactive'>('streaming');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ===== EFFECTS =====

  // Scroll para a última mensagem
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, intermediateStatus]);

  // Notificar mudança de conexão
  useEffect(() => {
    onConnectionChange?.(isConnected);
  }, [isConnected, onConnectionChange]);

  // Notificar erros
  useEffect(() => {
    if (error) {
      onError?.(error);
    }
  }, [error, onError]);

  // ===== HANDLERS =====

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!inputValue.trim() || isLoading || !isConnected) {
      return;
    }

    await sendMessage(inputValue.trim(), mode);
    setInputValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Send on Ctrl+Enter ou Cmd+Enter
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSendMessage(e as any);
    }
  };

  // ===== UTILS =====

  const getConnectionColor = (status: ConnectionStatus): string => {
    switch (status) {
      case 'connected':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'connecting':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'disconnected':
        return 'bg-gray-100 text-gray-800 border-gray-300';
      case 'error':
        return 'bg-red-100 text-red-800 border-red-300';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getConnectionLabel = (status: ConnectionStatus): string => {
    switch (status) {
      case 'connected':
        return '● Conectado';
      case 'connecting':
        return '◐ Conectando...';
      case 'disconnected':
        return '○ Desconectado';
      case 'error':
        return '✕ Erro';
      default:
        return 'Desconhecido';
    }
  };

  // ===== RENDER =====

  return (
    <div className="flex flex-col h-full max-w-2xl mx-auto bg-gradient-to-b from-slate-900 to-slate-800 rounded-lg shadow-2xl border border-slate-700">
      {/* ===== HEADER ===== */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-600 bg-slate-800">
        <div className="flex items-center gap-3">
          <div className={`text-xs font-semibold px-3 py-1 rounded border ${getConnectionColor(connectionStatus)}`}>
            {getConnectionLabel(connectionStatus)}
          </div>
          <h1 className="text-lg font-bold text-slate-100">Quinta-Feira</h1>
        </div>

        {/* Mode selector */}
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as any)}
          disabled={!isConnected}
          className="text-xs px-2 py-1 rounded bg-slate-700 text-slate-200 border border-slate-600 cursor-pointer disabled:opacity-50"
        >
          <option value="streaming">Streaming</option>
          <option value="deliberative">Deliberativo</option>
          <option value="interactive">Interativo</option>
        </select>
      </div>

      {/* ===== MESSAGES AREA ===== */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-slate-900">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-slate-400">
              <p className="text-sm mb-2">Nenhuma mensagem ainda</p>
              <p className="text-xs text-slate-500">
                {isConnected
                  ? 'Comece digitando uma pergunta'
                  : 'Aguardando conexão com o Brain...'}
              </p>
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {/* ===== STATUS INTERMEDIÁRIO ===== */}
            {intermediateStatus && (
              <div className="animate-pulse">
                <div className="bg-blue-900 border-l-4 border-blue-500 text-blue-100 p-3 rounded text-sm">
                  <div className="font-semibold mb-1">🔄 {intermediateStatus.step}</div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-blue-800 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-blue-500 h-full transition-all duration-300"
                        style={{ width: `${(intermediateStatus.progress || 0) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs whitespace-nowrap">
                      {Math.round((intermediateStatus.progress || 0) * 100)}%
                    </span>
                  </div>
                  {intermediateStatus.details && (
                    <div className="text-xs mt-2 text-blue-200 opacity-75">
                      {Object.entries(intermediateStatus.details).map(([key, value]) => (
                        <div key={key}>
                          {key}: {String(value)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ===== LOADING INDICATOR ===== */}
            {isLoading && !intermediateStatus && (
              <div className="animate-pulse">
                <div className="bg-blue-900 text-blue-100 p-3 rounded text-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                    </div>
                    <span>Pensando...</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* ===== ERROR BANNER ===== */}
      {error && (
        <div className="px-4 py-2 bg-red-900 border-t border-red-700 text-red-100 text-sm flex items-start gap-2">
          <span className="mt-0.5">⚠</span>
          <span className="flex-1">{error}</span>
          <button
            onClick={() => {
              // Error será limpo quando próxima ação bem-sucedida
            }}
            className="text-xs underline hover:text-red-200"
          >
            ✕
          </button>
        </div>
      )}

      {/* ===== INPUT AREA ===== */}
      <form onSubmit={handleSendMessage} className="border-t border-slate-600 bg-slate-800 p-3 space-y-2">
        <div className="flex gap-2">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Digite sua mensagem... (Ctrl+Enter para enviar)"
            disabled={!isConnected || isLoading}
            maxLength={10000}
            rows={2}
            className="flex-1 px-3 py-2 rounded bg-slate-700 text-slate-100 placeholder-slate-500 border border-slate-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          />

          <button
            type="submit"
            disabled={!isConnected || isLoading || !inputValue.trim()}
            className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors disabled:bg-slate-600 disabled:cursor-not-allowed text-sm h-fit"
          >
            {isLoading ? '⏳' : '→'}
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span>{inputValue.length}/10000</span>
          {!isConnected && <span className="text-yellow-500">Aguardando conexão...</span>}
          {isLoading && <span className="text-blue-500 animate-pulse">Processando...</span>}
        </div>
      </form>
    </div>
  );
}

// ===== COMPONENT: MESSAGE BUBBLE =====

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-xs px-4 py-2 rounded-lg ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-none'
            : 'bg-slate-700 text-slate-100 rounded-bl-none'
        }`}
      >
        {/* ===== CONTEÚDO PRINCIPAL ===== */}
        <p className="text-sm leading-relaxed">{message.content}</p>

        {/* ===== METADATA (Apenas assistente) ===== */}
        {!isUser && (message.execution_time_ms !== undefined || message.tools_used?.length) && (
          <div className="text-xs mt-2 text-slate-300 border-t border-slate-600 pt-1">
            {message.execution_time_ms !== undefined && (
              <div>⏱ {message.execution_time_ms.toFixed(0)}ms</div>
            )}
            {message.tools_used?.length ? (
              <div>🔧 {message.tools_used.join(', ')}</div>
            ) : null}
          </div>
        )}

        {/* ===== ERRO (Se houver) ===== */}
        {message.error && (
          <div className="text-xs mt-2 text-red-300 border-t border-red-700 pt-1">
            ✕ {message.error}
          </div>
        )}

        {/* ===== TIMESTAMP ===== */}
        <div className="text-xs mt-1 opacity-70">
          {new Date(message.timestamp).toLocaleTimeString('pt-BR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}
