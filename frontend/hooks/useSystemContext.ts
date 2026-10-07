'use client'

/**
 * useSystemContext — telemetria viva do PC para o HUD de sistema.
 *
 * Faz polling leve em GET /context (ContextSensor do backend): CPU, RAM,
 * bateria, clima, app em foco, jogo rodando e uptime de sessão.
 * Se o backend estiver fora, `online` vira false e o HUD degrada com graça.
 */

import { useEffect, useState } from 'react'

export interface SystemSnapshot {
  ok?: boolean
  hora?: string
  dia_semana?: string
  data?: string
  uptime_sessao_min?: number
  ocioso_seg?: number | null
  app_em_foco?: string
  janela_em_foco?: string
  apps_abertos?: string[]
  jogo_rodando?: string
  cpu_pct?: number
  ram_pct?: number
  bateria_pct?: number
  na_tomada?: boolean
  clima?: { descricao?: string; temp?: number; cidade?: string }
}

interface UseSystemContextReturn {
  snapshot: SystemSnapshot | null
  online: boolean
}

export function useSystemContext(
  httpBase = 'http://127.0.0.1:8000',
  intervalMs = 8000,
): UseSystemContextReturn {
  const [snapshot, setSnapshot] = useState<SystemSnapshot | null>(null)
  const [online, setOnline] = useState(false)

  useEffect(() => {
    let stopped = false

    const poll = async () => {
      try {
        const r = await fetch(`${httpBase}/context`)
        const d: SystemSnapshot = await r.json()
        if (stopped) return
        if (d?.ok) {
          setSnapshot(d)
          setOnline(true)
        } else {
          setOnline(false)
        }
      } catch {
        if (!stopped) setOnline(false)
      }
    }

    void poll()
    const id = window.setInterval(poll, intervalMs)
    return () => {
      stopped = true
      window.clearInterval(id)
    }
  }, [httpBase, intervalMs])

  return { snapshot, online }
}
