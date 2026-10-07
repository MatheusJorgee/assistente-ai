'use client'

/**
 * ApprovalCard — a Quinta-Feira PERGUNTA antes de fazer algo crítico.
 *
 * Aparece quando o backend pede aprovação (enviar WhatsApp, rodar comando no terminal,
 * apagar/escrever arquivo, iniciar/encerrar processo). O backend fica ESPERANDO; se o
 * cartão expirar ou você negar, a ação NÃO acontece.
 *
 * Padrão seguro:
 *   - o foco abre no botão NEGAR (Enter sem querer não aprova);
 *   - Esc nega;
 *   - mostra o que vai rodar de verdade (o comando/texto), não uma descrição vaga;
 *   - a barra mostra quanto falta pra negar sozinho.
 *
 * Só mostra o primeiro pedido; os demais aparecem como "+N na fila".
 */

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { ShieldAlert, TriangleAlert } from 'lucide-react'
import type { ApprovalRequest } from '@/types'

interface ApprovalCardProps {
  approvals: ApprovalRequest[]
  onRespond: (approvalId: string, permitido: boolean) => void
}

const NOME_FERRAMENTA: Record<string, string> = {
  whatsapp: 'WhatsApp',
  executar_terminal: 'Terminal',
  v2_os_command: 'Script do PowerShell',
  v2_file_ops: 'Arquivos',
  v2_process_control: 'Processos',
}

const NOME_ORIGEM: Record<string, string> = {
  chat: 'pedido no chat',
  agendado: 'ação agendada',
  telegram: 'Telegram',
  desconhecida: 'comando de voz ou atalho',
}

/** Relógio de 250 ms só enquanto há um pedido aberto (não gasta nada em repouso). */
function useAgora(ativo: boolean): number {
  const [agora, setAgora] = useState(() => Date.now())
  useEffect(() => {
    if (!ativo) return
    const id = window.setInterval(() => setAgora(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [ativo])
  return agora
}

export function ApprovalCard({ approvals, onRespond }: ApprovalCardProps) {
  const reduzirMovimento = useReducedMotion()
  const atual = approvals[0]
  const agora = useAgora(Boolean(atual))
  const negarRef = useRef<HTMLButtonElement>(null)

  // Foco no NEGAR sempre que aparece um pedido novo: o padrão é o lado seguro.
  useEffect(() => {
    if (atual) negarRef.current?.focus()
  }, [atual?.approval_id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Esc nega.
  useEffect(() => {
    if (!atual) return
    const id = atual.approval_id
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onRespond(id, false)
      }
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [atual?.approval_id, onRespond]) // eslint-disable-line react-hooks/exhaustive-deps

  const total = atual ? Math.max(1, atual.expira_em_s) : 1
  const restante = atual ? Math.max(0, total - (agora - atual.recebido_em) / 1000) : 0
  const pct = Math.max(0, Math.min(100, (restante / total) * 100))
  const urgente = restante <= 10

  return (
    <AnimatePresence>
      {atual ? (
        <motion.div
          key={atual.approval_id}
          role="alertdialog"
          aria-modal="false"
          aria-labelledby="approval-titulo"
          aria-describedby="approval-resumo"
          className="fixed top-24 left-1/2 z-[70] w-[min(92vw,560px)]"
          style={{ x: '-50%' }}
          initial={reduzirMovimento ? { opacity: 0 } : { opacity: 0, y: -14, scale: 0.98 }}
          animate={reduzirMovimento ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
          exit={reduzirMovimento ? { opacity: 0 } : { opacity: 0, y: -10, scale: 0.98 }}
          transition={{ duration: reduzirMovimento ? 0.12 : 0.22, ease: [0, 0, 0.2, 1] }}
        >
          <div
            className="rounded-2xl overflow-hidden"
            style={{
              background: 'linear-gradient(160deg, rgba(24,18,8,0.96), rgba(12,10,6,0.96))',
              backdropFilter: 'blur(22px)',
              WebkitBackdropFilter: 'blur(22px)',
              border: '1px solid rgba(245,158,11,0.38)',
              boxShadow: '0 18px 60px rgba(0,0,0,0.6), 0 0 32px rgba(245,158,11,0.10)',
            }}
          >
            <div className="px-5 pt-4 pb-3">
              <div className="flex items-start gap-3">
                <span
                  className="mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-full"
                  style={{ background: 'rgba(245,158,11,0.14)', color: 'rgb(251,191,36)' }}
                >
                  <ShieldAlert size={18} aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 id="approval-titulo" className="text-[15px] font-medium text-zinc-50">
                    Posso fazer isto?
                  </h2>
                  <p className="text-xs text-zinc-400">
                    {NOME_FERRAMENTA[atual.ferramenta] ?? atual.ferramenta} ·{' '}
                    {NOME_ORIGEM[atual.origem] ?? atual.origem}
                    {approvals.length > 1 ? (
                      <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-300">
                        +{approvals.length - 1} na fila
                      </span>
                    ) : null}
                  </p>
                </div>
              </div>

              {/* Pedido veio depois de ler texto de terceiros: é o cenário de "prompt injection" */}
              {atual.contaminado ? (
                <div
                  role="note"
                  className="mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-xs leading-relaxed"
                  style={{
                    background: 'rgba(239,68,68,0.10)',
                    border: '1px solid rgba(239,68,68,0.32)',
                    color: 'rgb(254,202,202)',
                  }}
                >
                  <TriangleAlert size={14} className="mt-0.5 flex-none" aria-hidden="true" />
                  <span>
                    Pedido <strong>depois de ler {atual.fontes?.length ? atual.fontes.join(' e ') : 'conteúdo de fora'}</strong>.
                    Confira se foi mesmo você: texto de terceiros pode tentar mandar a Quinta fazer coisas.
                  </span>
                </div>
              ) : null}

              <pre
                id="approval-resumo"
                className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg p-3
                           font-mono text-[13px] leading-relaxed text-amber-50"
                style={{ background: 'rgba(0,0,0,0.40)', border: '1px solid rgba(255,255,255,0.06)' }}
              >
                {atual.resumo}
              </pre>
            </div>

            {/* Contador regressivo: ao zerar, o backend NEGA sozinho */}
            <div
              className="h-1 w-full"
              style={{ background: 'rgba(255,255,255,0.06)' }}
              role="progressbar"
              aria-label="Tempo restante para decidir"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={Math.round(restante)}
            >
              <div
                className="h-full"
                style={{
                  width: `${pct}%`,
                  background: urgente ? 'rgb(248,113,113)' : 'rgb(251,191,36)',
                  transition: reduzirMovimento ? 'none' : 'width 0.25s linear',
                }}
              />
            </div>

            <div className="flex items-center justify-between gap-3 px-5 py-3">
              <span className="text-xs text-zinc-500">
                {restante > 0 ? `Nego sozinha em ${Math.ceil(restante)}s` : 'Tempo esgotado'}
                <span className="ml-2 hidden sm:inline text-zinc-600">Esc nega</span>
              </span>
              <div className="flex gap-2">
                <button
                  ref={negarRef}
                  type="button"
                  onClick={() => onRespond(atual.approval_id, false)}
                  className="rounded-full px-4 py-1.5 text-sm text-zinc-200 transition-colors
                             hover:bg-white/10 focus-visible:outline focus-visible:outline-2
                             focus-visible:outline-offset-2 focus-visible:outline-cyan-400"
                  style={{ border: '1px solid rgba(255,255,255,0.16)' }}
                >
                  Negar
                </button>
                <button
                  type="button"
                  onClick={() => onRespond(atual.approval_id, true)}
                  className="rounded-full px-4 py-1.5 text-sm font-medium text-zinc-950 transition-colors
                             hover:brightness-110 focus-visible:outline focus-visible:outline-2
                             focus-visible:outline-offset-2 focus-visible:outline-amber-200"
                  style={{ background: 'rgb(251,191,36)' }}
                >
                  Permitir
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
