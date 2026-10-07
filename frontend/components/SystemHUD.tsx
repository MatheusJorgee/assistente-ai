'use client'

/**
 * SystemHUD — painel de telemetria no canto superior esquerdo.
 *
 * Relógio + data, clima, barras de CPU/RAM, bateria, app em foco,
 * jogo rodando e uptime de sessão. Os dados vêm de GET /context
 * (ContextSensor do backend) via useSystemContext.
 *
 * Mesma linguagem visual do resto da página: vidro escuro, ciano, mono.
 */

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Cpu,
  MemoryStick,
  BatteryCharging,
  BatteryLow,
  Battery,
  Cloud,
  Gamepad2,
  AppWindow,
  Timer,
} from 'lucide-react'
import type { SystemSnapshot } from '@/hooks/useSystemContext'

interface SystemHUDProps {
  snapshot: SystemSnapshot | null
  online: boolean
}

/** Relógio local (1s). Começa NULO pra o 1º render do cliente bater com o do
 *  servidor (SSR) — só liga o horário depois de montar, evitando hydration mismatch. */
function useClock() {
  const [now, setNow] = useState<Date | null>(null)
  useEffect(() => {
    setNow(new Date())  // primeira leitura só no cliente
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

function barColor(pct: number): string {
  if (pct >= 88) return 'rgba(248,113,113,0.85)'
  if (pct >= 70) return 'rgba(251,191,36,0.85)'
  return 'rgba(6,182,212,0.85)'
}

function MetricBar({ icon, label, pct }: { icon: React.ReactNode; label: string; pct?: number }) {
  const value = typeof pct === 'number' ? Math.max(0, Math.min(100, pct)) : null
  return (
    <div className="flex items-center gap-2">
      <span className="text-cyan-500/60 flex-shrink-0">{icon}</span>
      <span className="w-8 text-[10px] font-mono uppercase tracking-wider text-slate-400/80">
        {label}
      </span>
      <div className="flex-1 h-1.5 rounded-full overflow-hidden bg-white/[0.06]">
        {value !== null ? (
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: barColor(value) }}
            animate={{ width: `${value}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          />
        ) : null}
      </div>
      <span className="w-9 text-right text-[11px] font-mono text-slate-300/90">
        {value !== null ? `${value}%` : '—'}
      </span>
    </div>
  )
}

function BatteryRow({ pct, plugged }: { pct?: number; plugged?: boolean }) {
  if (typeof pct !== 'number') return null
  const Icon = plugged ? BatteryCharging : pct <= 20 ? BatteryLow : Battery
  const color = pct <= 20 && !plugged ? 'rgba(248,113,113,0.9)' : 'rgba(52,211,153,0.85)'
  return (
    <div className="flex items-center gap-2 text-[11px] font-mono">
      <Icon size={13} style={{ color }} />
      <span style={{ color }}>{pct}%</span>
      <span className="text-slate-500">{plugged ? 'na tomada' : 'na bateria'}</span>
    </div>
  )
}

export function SystemHUD({ snapshot, online }: SystemHUDProps) {
  const now = useClock()
  // Placeholders idênticos no servidor e no 1º render do cliente (evita mismatch)
  const hora = now ? now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '--:--'
  const segundos = now ? now.toLocaleTimeString('pt-BR', { second: '2-digit' }).padStart(2, '0') : '--'
  const data = now ? now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' }) : ''

  const clima = snapshot?.clima
  const uptime = snapshot?.uptime_sessao_min ?? null

  return (
    <motion.aside
      className="fixed top-6 left-6 z-30 hidden md:flex flex-col gap-3 w-[250px] select-none"
      initial={{ x: -24, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.1, ease: [0, 0, 0.2, 1] }}
    >
      {/* Relógio + data */}
      <div
        className="rounded-2xl px-5 py-4"
        style={{
          background: 'linear-gradient(160deg, rgba(10,20,32,0.78), rgba(6,13,22,0.72))',
          backdropFilter: 'blur(18px)',
          WebkitBackdropFilter: 'blur(18px)',
          border: '1px solid rgba(6,182,212,0.12)',
          boxShadow: '0 8px 40px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05)',
        }}
      >
        <div className="flex items-baseline gap-1.5">
          <span
            className="text-4xl font-light font-mono tracking-tight text-slate-100"
            style={{ textShadow: '0 0 24px rgba(6,182,212,0.25)' }}
          >
            {hora}
          </span>
          <span className="text-sm font-mono text-cyan-500/60">{segundos}</span>
        </div>
        <p className="mt-1 text-[11px] font-mono uppercase tracking-[0.14em] text-slate-400/80">
          {data}
        </p>
        {clima ? (
          <div className="mt-2.5 flex items-center gap-2 text-[11px] font-mono text-slate-300/85">
            <Cloud size={13} className="text-cyan-500/60" />
            <span>
              {typeof clima.temp === 'number' ? `${Math.round(clima.temp)}°C` : ''}{' '}
              {clima.descricao}
              {clima.cidade ? ` · ${clima.cidade}` : ''}
            </span>
          </div>
        ) : null}
      </div>

      {/* Telemetria do sistema */}
      <div
        className="rounded-2xl px-4 py-3.5 flex flex-col gap-2.5"
        style={{
          background: 'linear-gradient(160deg, rgba(10,20,32,0.78), rgba(6,13,22,0.72))',
          backdropFilter: 'blur(18px)',
          WebkitBackdropFilter: 'blur(18px)',
          border: '1px solid rgba(6,182,212,0.12)',
          boxShadow: '0 8px 40px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05)',
        }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-cyan-400/70">
            Sistema
          </span>
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: online ? 'rgba(52,211,153,0.9)' : 'rgba(100,116,139,0.6)',
              boxShadow: online ? '0 0 6px rgba(52,211,153,0.5)' : 'none',
            }}
          />
        </div>

        {online && snapshot ? (
          <>
            <MetricBar icon={<Cpu size={13} />} label="CPU" pct={snapshot.cpu_pct} />
            <MetricBar icon={<MemoryStick size={13} />} label="RAM" pct={snapshot.ram_pct} />
            <BatteryRow pct={snapshot.bateria_pct} plugged={snapshot.na_tomada} />

            {snapshot.jogo_rodando ? (
              <div className="flex items-center gap-2 text-[11px] font-mono text-emerald-300/85">
                <Gamepad2 size={13} className="flex-shrink-0" />
                <span className="truncate">{snapshot.jogo_rodando}</span>
              </div>
            ) : snapshot.app_em_foco ? (
              <div className="flex items-center gap-2 text-[11px] font-mono text-slate-300/80">
                <AppWindow size={13} className="text-cyan-500/60 flex-shrink-0" />
                <span className="truncate" title={snapshot.janela_em_foco}>
                  {snapshot.app_em_foco}
                </span>
              </div>
            ) : null}

            {uptime !== null ? (
              <div className="flex items-center gap-2 text-[11px] font-mono text-slate-500">
                <Timer size={12} className="flex-shrink-0" />
                <span>
                  sessão {uptime >= 60 ? `${Math.floor(uptime / 60)}h${String(uptime % 60).padStart(2, '0')}` : `${uptime}min`}
                </span>
              </div>
            ) : null}
          </>
        ) : (
          <p className="text-[11px] font-mono text-slate-500">
            backend offline — sem telemetria
          </p>
        )}
      </div>
    </motion.aside>
  )
}
