'use client'

/**
 * ControlDeck — Dock de ações fixo na parte inferior da tela.
 *
 * 4 botões em pílula de vidro:
 *   MessageSquare → abre/fecha ChatOverlay
 *   Mic / MicOff  → ativa/desativa microfone
 *   Settings      → placeholder de configurações
 *   Power         → encerra sessão
 *
 * Indicador de conexão no canto inferior direito do dock.
 *
 * Requer: npm install framer-motion lucide-react
 */

import { motion } from 'framer-motion'
import {
  MessageSquare,
  Mic,
  MicOff,
  Settings,
  Power,
  Wifi,
  WifiOff,
} from 'lucide-react'
import type { ConnectionStatus } from '@/types'

interface ControlDeckProps {
  isChatOpen: boolean
  isMuted: boolean
  isConnected: boolean
  status: ConnectionStatus
  onToggleChat: () => void
  onToggleMute: () => void
  onSettings?: () => void
  onEndSession: () => void
}

interface DeckButtonProps {
  icon: React.ReactNode
  label: string
  onClick: () => void
  active?: boolean
  danger?: boolean
}

function DeckButton({ icon, label, onClick, active = false, danger = false }: DeckButtonProps) {
  return (
    <motion.button
      onClick={onClick}
      className="relative flex items-center justify-center w-10 h-10 rounded-full transition-colors"
      style={{
        background: active
          ? 'rgba(6,182,212,0.18)'
          : danger
          ? 'rgba(239,68,68,0.10)'
          : 'transparent',
        color: active
          ? 'rgba(6,182,212,0.95)'
          : danger
          ? 'rgba(248,113,113,0.80)'
          : 'rgba(148,163,184,0.70)',
        border: active ? '1px solid rgba(6,182,212,0.25)' : '1px solid transparent',
      }}
      whileHover={{
        scale: 1.12,
        backgroundColor: danger
          ? 'rgba(239,68,68,0.20)'
          : active
          ? 'rgba(6,182,212,0.25)'
          : 'rgba(255,255,255,0.07)',
      }}
      whileTap={{ scale: 0.90 }}
      aria-label={label}
      title={label}
    >
      {icon}
    </motion.button>
  )
}

const STATUS_DOT: Record<ConnectionStatus, { color: string; glow: string }> = {
  connected:    { color: 'rgba(52,211,153,0.9)',  glow: 'rgba(52,211,153,0.5)' },
  connecting:   { color: 'rgba(251,191,36,0.9)',  glow: 'rgba(251,191,36,0.4)' },
  disconnected: { color: 'rgba(100,116,139,0.7)', glow: 'transparent' },
  error:        { color: 'rgba(248,113,113,0.9)', glow: 'rgba(248,113,113,0.4)' },
}

export function ControlDeck({
  isChatOpen,
  isMuted,
  isConnected,
  status,
  onToggleChat,
  onToggleMute,
  onSettings,
  onEndSession,
}: ControlDeckProps) {
  const dot = STATUS_DOT[status]

  return (
    <motion.nav
      className="fixed bottom-8 left-1/2 z-50"
      style={{ x: '-50%' }}
      initial={{ y: 32, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.45, delay: 0.15, ease: [0, 0, 0.2, 1] }}
    >
      <div
        className="flex items-center gap-1 px-4 py-2 rounded-full relative"
        style={{
          background:
            'linear-gradient(160deg, rgba(10,20,32,0.84), rgba(6,13,22,0.80))',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid rgba(6,182,212,0.12)',
          boxShadow:
            '0 8px 40px rgba(0,0,0,0.50), 0 1px 0 rgba(255,255,255,0.05) inset',
        }}
      >
        {/* Divider visual entre grupos */}
        <DeckButton
          icon={<MessageSquare size={16} />}
          label={isChatOpen ? 'Fechar chat' : 'Abrir chat'}
          onClick={onToggleChat}
          active={isChatOpen}
        />

        <DeckButton
          icon={isMuted ? <MicOff size={16} /> : <Mic size={16} />}
          label={isMuted ? 'Ativar microfone' : 'Silenciar microfone'}
          onClick={onToggleMute}
          active={!isMuted}
        />

        {/* Separador */}
        <span
          className="w-px h-5 mx-0.5 rounded-full"
          style={{ backgroundColor: 'rgba(255,255,255,0.08)' }}
        />

        <DeckButton
          icon={<Settings size={16} />}
          label="Configurações"
          onClick={onSettings ?? (() => {})}
        />

        <DeckButton
          icon={<Power size={15} />}
          label="Encerrar sessão"
          onClick={onEndSession}
          danger
        />

        {/* Indicador de conexão */}
        <div className="ml-2 flex items-center gap-1.5">
          {isConnected ? (
            <Wifi size={11} style={{ color: 'rgba(52,211,153,0.7)' }} />
          ) : (
            <WifiOff size={11} style={{ color: 'rgba(100,116,139,0.5)' }} />
          )}
          <motion.span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: dot.color,
              boxShadow: `0 0 5px ${dot.glow}`,
            }}
            animate={
              status === 'connecting'
                ? { opacity: [1, 0.3, 1] }
                : { opacity: 1 }
            }
            transition={{ duration: 1, repeat: Infinity }}
          />
        </div>
      </div>
    </motion.nav>
  )
}
