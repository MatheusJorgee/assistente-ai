'use client'

/**
 * ChatOverlay — Painel lateral retrátil de histórico de conversa.
 *
 * Visual: Glassmorphism (backdrop-blur + bordas translúcidas).
 * Animação: Slide-in/out da direita via Framer Motion.
 * Auto-scroll para a última mensagem quando novas chegam.
 *
 * Requer: npm install framer-motion
 */

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Send } from 'lucide-react'
import type { Message } from '@/types'

interface ChatOverlayProps {
  isOpen: boolean
  messages: Message[]
  onClose: () => void
  onSendMessage: (text: string) => Promise<void>
}

const panelVariants = {
  hidden: {
    x: '100%',
    opacity: 0,
    transition: { duration: 0.32, ease: [0.4, 0, 1, 1] },
  },
  visible: {
    x: 0,
    opacity: 1,
    transition: { duration: 0.38, ease: [0, 0, 0.2, 1] },
  },
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  const time = new Date(msg.timestamp).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`flex w-full mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[82%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? 'rounded-br-sm'
            : 'rounded-bl-sm'
        }`}
        style={
          isUser
            ? {
                background: 'linear-gradient(135deg, rgba(6,182,212,0.25), rgba(59,130,246,0.20))',
                border: '1px solid rgba(6,182,212,0.30)',
                color: 'rgba(224,242,254,0.92)',
              }
            : {
                background: 'linear-gradient(135deg, rgba(15,23,42,0.70), rgba(15,23,42,0.55))',
                border: '1px solid rgba(255,255,255,0.07)',
                color: 'rgba(203,213,225,0.90)',
              }
        }
      >
        <p className="break-words whitespace-pre-wrap">{msg.content}</p>
        <span
          className="block mt-1 text-[10px] opacity-40 text-right"
        >
          {time}
        </span>
      </div>
    </div>
  )
}

export function ChatOverlay({ isOpen, messages, onClose, onSendMessage }: ChatOverlayProps) {
  const [inputValue, setInputValue] = useState('')
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll para última mensagem
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen])

  const handleSend = async () => {
    const text = inputValue.trim()
    if (!text || isSending) return
    setInputValue('')
    setIsSending(true)
    try {
      await onSendMessage(text)
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop invisível para fechar ao clicar fora */}
          <motion.div
            key="backdrop"
            className="fixed inset-0 z-40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          {/* Painel lateral */}
          <motion.aside
            key="panel"
            className="fixed right-0 top-0 bottom-0 z-50 flex flex-col"
            style={{
              width: 'min(420px, 92vw)',
              background:
                'linear-gradient(160deg, rgba(10,20,30,0.82), rgba(6,13,22,0.78))',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              borderLeft: '1px solid rgba(6,182,212,0.12)',
              boxShadow: '-24px 0 80px rgba(0,0,0,0.50), inset 1px 0 0 rgba(255,255,255,0.05)',
            }}
            variants={panelVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
          >
            {/* Cabeçalho */}
            <div
              className="flex items-center justify-between px-5 py-4 shrink-0"
              style={{ borderBottom: '1px solid rgba(6,182,212,0.10)' }}
            >
              <div className="flex items-center gap-3">
                {/* Indicador de status */}
                <span
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor: 'rgba(52,211,153,0.9)',
                    boxShadow: '0 0 6px rgba(52,211,153,0.6)',
                  }}
                />
                <span
                  className="text-sm font-semibold tracking-widest uppercase"
                  style={{ color: 'rgba(6,182,212,0.85)', letterSpacing: '0.12em' }}
                >
                  Quinta-Feira
                </span>
              </div>
              <button
                onClick={onClose}
                className="flex items-center justify-center w-8 h-8 rounded-full transition-colors"
                style={{ color: 'rgba(148,163,184,0.7)' }}
                onMouseEnter={(e) =>
                  ((e.currentTarget as HTMLButtonElement).style.color =
                    'rgba(248,250,252,0.9)')
                }
                onMouseLeave={(e) =>
                  ((e.currentTarget as HTMLButtonElement).style.color =
                    'rgba(148,163,184,0.7)')
                }
                aria-label="Fechar chat"
              >
                <X size={16} />
              </button>
            </div>

            {/* Mensagens */}
            <div className="flex-1 overflow-y-auto px-4 py-4 custom-scrollbar">
              {messages.length === 0 ? (
                <div
                  className="flex flex-col items-center justify-center h-full gap-2 text-center"
                  style={{ color: 'rgba(100,116,139,0.6)' }}
                >
                  <span className="text-3xl opacity-30">◎</span>
                  <p className="text-sm">Nenhuma mensagem ainda.</p>
                  <p className="text-xs opacity-70">Fale ou escreva algo abaixo.</p>
                </div>
              ) : (
                messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input de texto */}
            <div
              className="px-4 py-4 shrink-0"
              style={{ borderTop: '1px solid rgba(6,182,212,0.10)' }}
            >
              <div
                className="flex items-center gap-2 rounded-xl px-3 py-2"
                style={{
                  background: 'rgba(6,182,212,0.06)',
                  border: '1px solid rgba(6,182,212,0.15)',
                }}
              >
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Digite um comando..."
                  disabled={isSending}
                  className="flex-1 bg-transparent text-sm outline-none placeholder:opacity-40"
                  style={{ color: 'rgba(226,232,240,0.90)' }}
                />
                <button
                  onClick={handleSend}
                  disabled={!inputValue.trim() || isSending}
                  className="flex items-center justify-center w-7 h-7 rounded-lg transition-all disabled:opacity-30"
                  style={{
                    background: inputValue.trim()
                      ? 'rgba(6,182,212,0.20)'
                      : 'transparent',
                    color: 'rgba(6,182,212,0.85)',
                  }}
                  aria-label="Enviar"
                >
                  <Send size={13} />
                </button>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
