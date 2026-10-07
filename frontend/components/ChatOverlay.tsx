'use client'

/**
 * ChatOverlay — Painel lateral retrátil de histórico de conversa.
 *
 * Visual: Glassmorphism (backdrop-blur + bordas translúcidas).
 * Animação: Slide-in/out da direita via Framer Motion.
 * Respostas da assistente renderizam Markdown (react-markdown + GFM),
 * mostram chips das ferramentas usadas e tempo de execução.
 * Enquanto ela processa, aparece um balão "pensando..." com o passo
 * intermediário reportado pelo WebSocket.
 */

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Send, Wrench } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, IntermediateStatus } from '@/types'

interface ChatOverlayProps {
  isOpen: boolean
  messages: Message[]
  isConnected: boolean
  isLoading: boolean
  intermediateStatus: IntermediateStatus | null
  /** Resposta chegando em pedaços (streaming); some quando a resposta final entra em `messages`. */
  streamingText: string | null
  onClose: () => void
  onSendMessage: (text: string) => Promise<void>
}

const panelVariants = {
  hidden: {
    x: '100%',
    opacity: 0,
    transition: { duration: 0.32, ease: [0.4, 0, 1, 1] as [number, number, number, number] },
  },
  visible: {
    x: 0,
    opacity: 1,
    transition: { duration: 0.38, ease: [0, 0, 0.2, 1] as [number, number, number, number] },
  },
}

// Rótulos amigáveis para os passos intermediários do backend
const STEP_LABEL: Record<string, string> = {
  thinking: 'pensando',
  processing: 'processando',
  executing: 'executando ferramenta',
  searching: 'pesquisando',
}

function ToolChips({ tools, ms }: { tools?: string[]; ms?: number }) {
  if (!tools?.length && !ms) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-2">
      {(tools ?? []).map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-mono"
          style={{
            background: 'rgba(6,182,212,0.10)',
            border: '1px solid rgba(6,182,212,0.18)',
            color: 'rgba(6,182,212,0.80)',
          }}
        >
          <Wrench size={9} />
          {t}
        </span>
      ))}
      {typeof ms === 'number' && ms > 0 ? (
        <span className="text-[10px] font-mono text-slate-500">
          {(ms / 1000).toFixed(1)}s
        </span>
      ) : null}
    </div>
  )
}

function MessageBubble({ msg, streaming = false }: { msg: Message; streaming?: boolean }) {
  const isUser = msg.role === 'user'
  const time = new Date(msg.timestamp).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`flex w-full mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[82%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
          isUser ? 'rounded-br-sm' : 'rounded-bl-sm'
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
        {isUser ? (
          <p className="break-words whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div className="chat-markdown break-words">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
          </div>
        )}

        {!isUser && !streaming ? <ToolChips tools={msg.tools_used} ms={msg.execution_time_ms} /> : null}

        {streaming ? (
          // Cursor de "ainda escrevendo" (sem animação para quem prefere menos movimento)
          <span
            aria-hidden="true"
            className="mt-1 inline-block h-3 w-1.5 rounded-sm bg-cyan-300/70 motion-safe:animate-pulse"
          />
        ) : (
          <span className="block mt-1 text-[10px] opacity-40 text-right">{time}</span>
        )}
      </div>
    </div>
  )
}

/** Balão "ela está pensando" com pontinhos animados + passo atual. */
function TypingBubble({ status }: { status: IntermediateStatus | null }) {
  const label = status ? STEP_LABEL[status.step] ?? status.step : 'pensando'
  return (
    <div className="flex w-full mb-3 justify-start">
      <div
        className="px-4 py-3 rounded-2xl rounded-bl-sm flex items-center gap-2.5"
        style={{
          background: 'linear-gradient(135deg, rgba(15,23,42,0.70), rgba(15,23,42,0.55))',
          border: '1px solid rgba(99,102,241,0.20)',
        }}
      >
        <span className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: 'rgba(99,102,241,0.85)' }}
              animate={{ opacity: [0.25, 1, 0.25], y: [0, -2, 0] }}
              transition={{ duration: 1.0, repeat: Infinity, delay: i * 0.18 }}
            />
          ))}
        </span>
        <span className="text-[11px] font-mono text-indigo-300/70">{label}...</span>
      </div>
    </div>
  )
}

export function ChatOverlay({
  isOpen,
  messages,
  isConnected,
  isLoading,
  intermediateStatus,
  streamingText,
  onClose,
  onSendMessage,
}: ChatOverlayProps) {
  const [inputValue, setInputValue] = useState('')
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Auto-scroll para última mensagem (e quando o "pensando" aparece). Durante o streaming o
  // texto cresce a cada pedaço: rolagem instantânea, para não ficar "correndo atrás" do texto.
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: streamingText ? 'auto' : 'smooth' })
    }
  }, [messages, isLoading, isOpen, streamingText])

  // Foco no input ao abrir
  useEffect(() => {
    if (isOpen) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 400)
      return () => window.clearTimeout(t)
    }
  }, [isOpen])

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
                {/* Indicador de status real da conexão */}
                <span
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor: isConnected
                      ? 'rgba(52,211,153,0.9)'
                      : 'rgba(248,113,113,0.85)',
                    boxShadow: isConnected
                      ? '0 0 6px rgba(52,211,153,0.6)'
                      : '0 0 6px rgba(248,113,113,0.5)',
                  }}
                />
                <span
                  className="text-sm font-semibold tracking-widest uppercase"
                  style={{ color: 'rgba(6,182,212,0.85)', letterSpacing: '0.12em' }}
                >
                  Quinta-Feira
                </span>
                {!isConnected ? (
                  <span className="text-[10px] font-mono text-rose-400/70">offline</span>
                ) : null}
              </div>
              <button
                onClick={onClose}
                className="flex items-center justify-center w-8 h-8 rounded-full transition-colors text-slate-400 hover:text-slate-100"
                aria-label="Fechar chat"
              >
                <X size={16} />
              </button>
            </div>

            {/* Mensagens */}
            <div className="flex-1 overflow-y-auto px-4 py-4 custom-scrollbar">
              {messages.length === 0 && !isLoading ? (
                <div
                  className="flex flex-col items-center justify-center h-full gap-2 text-center"
                  style={{ color: 'rgba(100,116,139,0.6)' }}
                >
                  <span className="text-3xl opacity-30">◎</span>
                  <p className="text-sm">Nenhuma mensagem ainda.</p>
                  <p className="text-xs opacity-70">Fale ou escreva algo abaixo.</p>
                </div>
              ) : (
                <>
                  {messages.map((msg) => (
                    <MessageBubble key={msg.id} msg={msg} />
                  ))}
                  {streamingText ? (
                    <MessageBubble
                      streaming
                      msg={{ id: 'streaming', role: 'assistant', content: streamingText, timestamp: 0 }}
                    />
                  ) : isLoading ? (
                    <TypingBubble status={intermediateStatus} />
                  ) : null}
                </>
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
                  ref={inputRef}
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
                    background: inputValue.trim() ? 'rgba(6,182,212,0.20)' : 'transparent',
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
