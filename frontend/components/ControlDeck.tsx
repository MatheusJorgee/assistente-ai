'use client'

/**
 * ControlDeck — Dock de ações fixo na parte inferior da tela.
 *
 * Botões em pílula de vidro:
 *   MessageSquare    → abre/fecha ChatOverlay
 *   Mic / MicOff     → ativa/desativa microfone
 *   Newspaper        → recarrega o carrossel de notícias no visor
 *   BrainCircuit     → abre/fecha o painel de memória (o que ela aprendeu)
 *   Volume2/VolumeX  → liga/desliga a narração por voz (persistido)
 *   Square           → PARAR tudo: fala + execução + fila (só aparece enquanto ela trabalha/fala)
 *   Power            → encerra sessão
 *
 * Indicador de conexão no canto direito do dock.
 */

import { motion, AnimatePresence } from 'framer-motion'
import {
  MessageSquare,
  Mic,
  MicOff,
  Newspaper,
  BrainCircuit,
  Volume2,
  VolumeX,
  Square,
  Power,
  Wifi,
  WifiOff,
  Ear,
  ShieldCheck,
  ShieldQuestion,
  ShieldOff,
} from 'lucide-react'
import type { ConnectionStatus, AutonomyMode } from '@/types'

interface ControlDeckProps {
  isChatOpen: boolean
  isMuted: boolean
  isMemoryOpen: boolean
  narrationOn: boolean
  ambientOn: boolean
  canStop: boolean
  isConnected: boolean
  status: ConnectionStatus
  autonomyMode: AutonomyMode | null
  onCycleAutonomy: () => void
  onToggleChat: () => void
  onToggleMute: () => void
  onShowNews: () => void
  onToggleMemory: () => void
  onToggleNarration: () => void
  onToggleAmbient: () => void
  onStop: () => void
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

function Separator() {
  return (
    <span
      className="w-px h-5 mx-0.5 rounded-full"
      style={{ backgroundColor: 'rgba(255,255,255,0.08)' }}
    />
  )
}

const AUTONOMIA_ROTULO: Record<AutonomyMode, string> = {
  perguntar_sempre: 'Autonomia: pergunto antes de qualquer ação (clique para mudar)',
  so_perigoso: 'Autonomia: pergunto só nas ações críticas (clique para mudar)',
  autonoma: 'Autonomia: SEM perguntar, tudo liberado (clique para mudar)',
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
  isMemoryOpen,
  narrationOn,
  ambientOn,
  canStop,
  isConnected,
  status,
  autonomyMode,
  onCycleAutonomy,
  onToggleChat,
  onToggleMute,
  onShowNews,
  onToggleMemory,
  onToggleNarration,
  onToggleAmbient,
  onStop,
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
        {/* Conversa */}
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

        {/* Escuta ambiente: ela decide sozinha se a fala foi com ela */}
        <DeckButton
          icon={<Ear size={16} />}
          label={ambientOn ? 'Escuta ambiente LIGADA (ela entende se é com ela)' : 'Ligar escuta ambiente (sem precisar dizer "Quinta")'}
          onClick={onToggleAmbient}
          active={ambientOn}
        />

        <Separator />

        {/* Conteúdo */}
        <DeckButton
          icon={<Newspaper size={16} />}
          label="Notícias do dia"
          onClick={onShowNews}
        />

        <DeckButton
          icon={<BrainCircuit size={16} />}
          label={isMemoryOpen ? 'Fechar memória' : 'O que ela aprendeu'}
          onClick={onToggleMemory}
          active={isMemoryOpen}
        />

        <Separator />

        {/* Voz */}
        <DeckButton
          icon={narrationOn ? <Volume2 size={16} /> : <VolumeX size={16} />}
          label={narrationOn ? 'Desligar narração por voz' : 'Ligar narração por voz'}
          onClick={onToggleNarration}
          active={narrationOn}
        />

        {/* PARAR — só existe enquanto ela trabalha ou fala; corta a voz, cancela a execução
            e descarta a fila (Esc faz o mesmo) */}
        <AnimatePresence>
          {canStop ? (
            <motion.div
              initial={{ width: 0, opacity: 0, scale: 0.6 }}
              animate={{ width: 'auto', opacity: 1, scale: 1 }}
              exit={{ width: 0, opacity: 0, scale: 0.6 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <DeckButton
                icon={<Square size={13} fill="currentColor" />}
                label="Parar tudo (Esc): para de falar e cancela o que ela estiver fazendo"
                onClick={onStop}
                danger
              />
            </motion.div>
          ) : null}
        </AnimatePresence>

        <Separator />

        {/* Autonomia: quando ela pergunta antes de agir. Clique alterna o modo. */}
        {autonomyMode ? (
          <DeckButton
            icon={
              autonomyMode === 'perguntar_sempre' ? (
                <ShieldQuestion size={16} />
              ) : autonomyMode === 'so_perigoso' ? (
                <ShieldCheck size={16} />
              ) : (
                <ShieldOff size={16} />
              )
            }
            label={AUTONOMIA_ROTULO[autonomyMode]}
            onClick={onCycleAutonomy}
            active={autonomyMode !== 'autonoma'}
            danger={autonomyMode === 'autonoma'}
          />
        ) : null}

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
