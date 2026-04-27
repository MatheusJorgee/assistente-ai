'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { ChatMessage } from '@/components/ChatMessage';
import type { ChatMessage as ChatMessageModel, IntermediateStatus } from '@/types';

interface ChatOverlayProps {
  isVisible: boolean;
  messages: ChatMessageModel[];
  isLoading: boolean;
  intermediateStatus: IntermediateStatus | null;
  error: string | null;
  isConnected: boolean;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  scrollEndRef: { current: HTMLDivElement | null };
}

export function ChatOverlay({
  isVisible,
  messages,
  isLoading,
  intermediateStatus,
  error,
  isConnected,
  input,
  onInputChange,
  onSend,
  scrollEndRef,
}: ChatOverlayProps) {
  return (
    <AnimatePresence>
      {isVisible && (
        <motion.aside
          key="chat-overlay"
          initial={{ x: -320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: -320, opacity: 0 }}
          transition={{ type: 'spring', damping: 28, stiffness: 220 }}
          className="w-80 flex-shrink-0 flex flex-col h-full bg-white/5 backdrop-blur-xl border-r border-white/10"
        >
          {/* Header */}
          <div className="px-4 py-3 border-b border-white/10 flex-shrink-0">
            <span className="text-[11px] font-mono text-zinc-400 uppercase tracking-widest">
              Histórico
            </span>
          </div>

          {/* Messages */}
          <div className="flex-1 min-h-0 overflow-y-auto px-3 py-4 space-y-3 scroll-smooth">
            {messages.length === 0 && !isLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center text-zinc-600 py-12">
                <div className="text-2xl mb-2">✦</div>
                <p className="text-xs">Nenhuma mensagem ainda.</p>
              </div>
            )}

            {messages.map(m => (
              <ChatMessage key={m.id} message={m} />
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="px-3 py-2 rounded-xl bg-zinc-800 border border-zinc-700 text-xs font-mono text-emerald-300">
                  <span className="inline-flex gap-1">
                    <span className="animate-bounce">·</span>
                    <span className="animate-bounce [animation-delay:120ms]">·</span>
                    <span className="animate-bounce [animation-delay:240ms]">·</span>
                  </span>
                  {intermediateStatus?.step ? ` ${intermediateStatus.step}` : ' pensando'}
                </div>
              </div>
            )}

            {error && (
              <div className="px-3 py-1.5 rounded-lg bg-red-900/30 border border-red-700/50 text-[11px] font-mono text-red-300">
                {error}
              </div>
            )}

            <div ref={scrollEndRef} />
          </div>

          {/* Input */}
          <div className="px-3 py-3 border-t border-white/10 flex-shrink-0">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={e => onInputChange(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    onSend();
                  }
                }}
                placeholder={isConnected ? 'Mensagem…' : 'Conectando…'}
                rows={1}
                disabled={!isConnected}
                className="flex-1 resize-none bg-zinc-800/70 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30 disabled:opacity-50 max-h-32"
              />
              <button
                onClick={onSend}
                disabled={!isConnected || !input.trim()}
                className="h-9 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-xs font-semibold transition-colors"
              >
                ↑
              </button>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
