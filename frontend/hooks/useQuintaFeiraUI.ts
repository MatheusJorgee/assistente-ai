'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuintaFeira } from './useQuintaFeira';
import type { ChatMessage, ConnectionStatus, IntermediateStatus } from '@/types';
import type { ActiveMedia } from '@/components/MediaPlayer';

export type OrbState = 'idle' | 'listening' | 'processing';

interface UseQuintaFeiraUIReturn {
  messages: ChatMessage[];
  isConnected: boolean;
  connectionStatus: ConnectionStatus;
  isLoading: boolean;
  intermediateStatus: IntermediateStatus | null;
  error: string | null;
  activeMedia: ActiveMedia | null;
  clearMedia: () => void;
  orbState: OrbState;
  isMuted: boolean;
  isChatOpen: boolean;
  input: string;
  setInput: (value: string) => void;
  handleSend: () => Promise<void>;
  toggleMute: () => void;
  toggleChat: () => void;
  scrollEndRef: { current: HTMLDivElement | null };
}

export function useQuintaFeiraUI(): UseQuintaFeiraUIReturn {
  const {
    messages,
    isConnected,
    connectionStatus,
    isLoading,
    intermediateStatus,
    error,
    activeMedia,
    clearMedia,
    sendMessage,
  } = useQuintaFeira({ wsUrl: 'ws://127.0.0.1:8000/ws/quinta' });

  const [isMuted, setIsMuted] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [input, setInput] = useState('');
  const scrollEndRef = useRef<HTMLDivElement>(null);

  const orbState: OrbState = isLoading ? 'processing' : 'idle';

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, intermediateStatus, isLoading]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || !isConnected) return;
    setInput('');
    try {
      await sendMessage(text, 'streaming');
    } catch {
      // errors propagated by the WS hook
    }
  }, [input, isConnected, sendMessage]);

  const toggleMute = useCallback(() => setIsMuted(prev => !prev), []);
  const toggleChat = useCallback(() => setIsChatOpen(prev => !prev), []);

  return {
    messages,
    isConnected,
    connectionStatus,
    isLoading,
    intermediateStatus,
    error,
    activeMedia,
    clearMedia,
    orbState,
    isMuted,
    isChatOpen,
    input,
    setInput,
    handleSend,
    toggleMute,
    toggleChat,
    scrollEndRef,
  };
}
