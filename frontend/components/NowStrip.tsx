'use client'

/**
 * NowStrip — a faixa "Agora": o que a Quinta-Feira está fazendo neste instante.
 *
 * Fica sob o orbe e só existe enquanto ela trabalha. Prioridade do que mostra:
 *   1. aguardando a sua aprovação   (o trabalho está parado esperando você)
 *   2. a ferramenta em uso           ("pesquisando na web…" + cronômetro)
 *   3. pensando                      (entre uma ferramenta e outra)
 *
 * Transparência sem ruído: mostra só o rótulo da ação (nunca os argumentos, que podem ser
 * privados) e lembra que o Esc para tudo.
 */

import { useEffect, useState } from 'react'
import type { AgoraActivity } from '@/types'

interface NowStripProps {
  activity: AgoraActivity | null
  isLoading: boolean
  waitingApproval: boolean
}

function useSegundos(desde: number | null): number {
  const [agora, setAgora] = useState(() => Date.now())
  // O relógio só anda enquanto há atividade. O 1º tick (1 s) já corrige o valor; e como só
  // mostramos o cronômetro a partir de 2 s, um `agora` antigo nunca aparece na tela.
  useEffect(() => {
    if (desde === null) return
    const id = window.setInterval(() => setAgora(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [desde])
  return desde === null ? 0 : Math.max(0, Math.floor((agora - desde) / 1000))
}

export function NowStrip({ activity, isLoading, waitingApproval }: NowStripProps) {
  const segundos = useSegundos(activity?.since ?? null)

  const ativo = waitingApproval || Boolean(activity) || isLoading
  if (!ativo) return null

  const cor = waitingApproval ? 'rgb(251,191,36)' : 'rgb(103,232,249)'
  const texto = waitingApproval
    ? 'aguardando a sua aprovação'
    : activity
      ? activity.label
      : 'pensando'

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-mono"
      style={{
        background: 'rgba(10,20,32,0.66)',
        border: `1px solid ${waitingApproval ? 'rgba(245,158,11,0.32)' : 'rgba(6,182,212,0.20)'}`,
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        color: cor,
      }}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 flex-none rounded-full motion-safe:animate-pulse"
        style={{ background: cor, boxShadow: `0 0 6px ${cor}` }}
      />
      <span>
        {texto}
        {waitingApproval ? '' : '…'}
        {activity && !waitingApproval && segundos >= 2 ? ` ${segundos}s` : ''}
      </span>
      {/* Com um cartão de aprovação aberto o Esc NEGA o cartão; só sem ele o Esc para tudo */}
      <span className="hidden sm:inline text-slate-500">
        {waitingApproval ? '· Esc nega' : '· Esc para parar'}
      </span>
    </div>
  )
}
