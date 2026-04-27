'use client';

import { motion } from 'framer-motion';
import { Mic, MicOff, MessageCircle, XCircle } from 'lucide-react';
import type { ConnectionStatus } from '@/types';

interface ControlDeckProps {
  isMuted: boolean;
  isChatOpen: boolean;
  isConnected: boolean;
  connectionStatus: ConnectionStatus;
  onToggleMute: () => void;
  onToggleChat: () => void;
}

export function ControlDeck({
  isMuted,
  isChatOpen,
  isConnected,
  connectionStatus,
  onToggleMute,
  onToggleChat,
}: ControlDeckProps) {
  const statusColor =
    connectionStatus === 'connected'
      ? 'bg-emerald-500'
      : connectionStatus === 'connecting'
      ? 'bg-amber-500 animate-pulse'
      : 'bg-red-500';

  return (
    <div className="flex items-center justify-center gap-3 pb-10 pt-6">
      <motion.button
        whileTap={{ scale: 0.9 }}
        onClick={onToggleMute}
        title={isMuted ? 'Ativar som' : 'Mutar'}
        className={[
          'flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-mono border transition-colors',
          isMuted
            ? 'bg-red-600/20 border-red-500/50 text-red-300 hover:bg-red-600/30'
            : 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100',
        ].join(' ')}
      >
        {isMuted ? <MicOff size={15} /> : <Mic size={15} />}
        <span>{isMuted ? 'Mudo' : 'Som'}</span>
      </motion.button>

      <motion.button
        whileTap={{ scale: 0.9 }}
        onClick={onToggleChat}
        disabled={!isConnected}
        title={isChatOpen ? 'Fechar chat' : 'Abrir chat'}
        className={[
          'flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-mono border transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
          isChatOpen
            ? 'bg-emerald-600/20 border-emerald-500/50 text-emerald-300 hover:bg-emerald-600/30'
            : 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100',
        ].join(' ')}
      >
        {isChatOpen ? <XCircle size={15} /> : <MessageCircle size={15} />}
        <span>{isChatOpen ? 'Fechar' : 'Chat'}</span>
      </motion.button>

      <div className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-zinc-800/60 border border-zinc-700/60">
        <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${statusColor}`} />
        <span className="text-[11px] font-mono text-zinc-400">{connectionStatus}</span>
      </div>
    </div>
  );
}
