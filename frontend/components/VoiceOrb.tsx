'use client'

/**
 * VoiceOrb — Elemento visual central do assistente.
 *
 * Máquina de estados visual via Framer Motion variants.
 * Cada estado produz animações fisicamente distintas:
 *   idle       → respiração lenta (scale ±2%)
 *   listening  → anéis sonar se expandindo em onda (3 anéis com delay)
 *   processing → dois anéis orbitando em sentidos opostos
 *   speaking   → pulso rápido + glow amplificado
 *
 * Requer: npm install framer-motion
 */

import { motion, AnimatePresence } from 'framer-motion'
import type { Variants } from 'framer-motion'
import type { OrbState } from '@/types'

interface VoiceOrbProps {
  state: OrbState
  onClick?: () => void
}

// ---------------------------------------------------------------------------
// Variantes de animação do núcleo principal
// ---------------------------------------------------------------------------

const coreVariants: Variants = {
  idle: {
    scale: [1, 1.022, 1],
    transition: {
      duration: 3.6,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
  listening: {
    scale: 1.05,
    transition: { duration: 0.35, ease: [0.34, 1.56, 0.64, 1] }, // spring suave
  },
  processing: {
    scale: 1,
    transition: { duration: 0.25, ease: 'easeOut' },
  },
  speaking: {
    scale: [1, 1.06, 0.96, 1.04, 1],
    transition: {
      duration: 0.72,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
}

// Glow ambiente por estado
const glowVariants: Variants = {
  idle:       { opacity: 0.35, scale: 1.15 },
  listening:  { opacity: 0.60, scale: 1.45 },
  processing: { opacity: 0.50, scale: 1.30 },
  speaking:   { opacity: 0.80, scale: 1.60 },
}

// Ponto interior por estado
const dotVariants: Variants = {
  idle:       { scale: 1 },
  listening:  { scale: 1.4 },
  processing: { scale: [1, 1.6, 1], transition: { duration: 0.9, repeat: Infinity } },
  speaking:   { scale: [1, 1.8, 1], transition: { duration: 0.45, repeat: Infinity } },
}

// Cores CSS por estado (inline para não depender de purge de classes dinâmicas)
const STATE_STYLE: Record<OrbState, {
  glow: string
  coreBorder: string
  coreGradient: string
  dotColor: string
  ringBorder: string
}> = {
  idle: {
    glow:          'rgba(6,182,212,0.18)',
    coreBorder:    'rgba(6,182,212,0.28)',
    coreGradient:  'linear-gradient(135deg, rgba(6,182,212,0.14) 0%, rgba(59,130,246,0.10) 100%)',
    dotColor:      'rgba(6,182,212,0.75)',
    ringBorder:    'rgba(6,182,212,0.35)',
  },
  listening: {
    glow:          'rgba(52,211,153,0.30)',
    coreBorder:    'rgba(52,211,153,0.45)',
    coreGradient:  'linear-gradient(135deg, rgba(52,211,153,0.20) 0%, rgba(6,182,212,0.14) 100%)',
    dotColor:      'rgba(52,211,153,0.95)',
    ringBorder:    'rgba(52,211,153,0.45)',
  },
  processing: {
    glow:          'rgba(99,102,241,0.25)',
    coreBorder:    'rgba(99,102,241,0.45)',
    coreGradient:  'linear-gradient(135deg, rgba(59,130,246,0.20) 0%, rgba(168,85,247,0.14) 100%)',
    dotColor:      'rgba(99,102,241,0.90)',
    ringBorder:    'rgba(99,102,241,0.45)',
  },
  speaking: {
    glow:          'rgba(20,184,166,0.38)',
    coreBorder:    'rgba(20,184,166,0.60)',
    coreGradient:  'linear-gradient(135deg, rgba(20,184,166,0.24) 0%, rgba(6,182,212,0.18) 100%)',
    dotColor:      'rgba(20,184,166,1)',
    ringBorder:    'rgba(20,184,166,0.55)',
  },
}

// ---------------------------------------------------------------------------
// Sub-componentes de efeito por estado
// ---------------------------------------------------------------------------

function SonarRings({ borderColor }: { borderColor: string }) {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="absolute inset-0 rounded-full"
          style={{ border: `1px solid ${borderColor}` }}
          initial={{ scale: 1, opacity: 0.55 }}
          animate={{ scale: 2.4, opacity: 0 }}
          transition={{
            duration: 2.2,
            repeat: Infinity,
            delay: i * 0.70,
            ease: 'easeOut',
          }}
        />
      ))}
    </>
  )
}

function ProcessingRings() {
  return (
    <>
      {/* Anel externo — sentido horário */}
      <motion.span
        className="absolute rounded-full"
        style={{
          inset: '-10px',
          border: '1.5px solid transparent',
          borderTopColor: 'rgba(99,102,241,0.8)',
          borderBottomColor: 'rgba(168,85,247,0.5)',
        }}
        animate={{ rotate: 360 }}
        transition={{ duration: 2.0, repeat: Infinity, ease: 'linear' }}
      />
      {/* Anel interno — sentido anti-horário */}
      <motion.span
        className="absolute rounded-full"
        style={{
          inset: '10px',
          border: '1px solid transparent',
          borderRightColor: 'rgba(59,130,246,0.65)',
          borderLeftColor:  'rgba(168,85,247,0.50)',
        }}
        animate={{ rotate: -360 }}
        transition={{ duration: 2.8, repeat: Infinity, ease: 'linear' }}
      />
    </>
  )
}

function SpeakingWaves({ borderColor }: { borderColor: string }) {
  return (
    <>
      {[0, 1].map((i) => (
        <motion.span
          key={i}
          className="absolute inset-0 rounded-full"
          style={{ border: `1px solid ${borderColor}` }}
          initial={{ scale: 1, opacity: 0.6 }}
          animate={{ scale: [1, 1.5, 1.8], opacity: [0.6, 0.2, 0] }}
          transition={{
            duration: 1.1,
            repeat: Infinity,
            delay: i * 0.55,
            ease: 'easeOut',
          }}
        />
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function VoiceOrb({ state, onClick }: VoiceOrbProps) {
  const s = STATE_STYLE[state]

  return (
    <div
      className="relative flex items-center justify-center select-none"
      style={{ width: 200, height: 200 }}
    >
      {/* Glow ambiente — blur radial atrás do orbe */}
      <motion.div
        className="absolute rounded-full blur-3xl pointer-events-none"
        style={{ inset: '10px', backgroundColor: s.glow }}
        variants={glowVariants}
        animate={state}
        transition={{ duration: 0.55 }}
      />

      {/* Efeitos de estado (anéis, ondas) */}
      <AnimatePresence mode="wait">
        {state === 'listening' && (
          <motion.div
            key="sonar"
            className="absolute inset-0 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            <div className="relative" style={{ width: 160, height: 160 }}>
              <SonarRings borderColor={s.ringBorder} />
            </div>
          </motion.div>
        )}

        {state === 'processing' && (
          <motion.div
            key="orbit"
            className="absolute inset-0 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            <div className="relative" style={{ width: 160, height: 160 }}>
              <ProcessingRings />
            </div>
          </motion.div>
        )}

        {state === 'speaking' && (
          <motion.div
            key="waves"
            className="absolute inset-0 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            <div className="relative" style={{ width: 160, height: 160 }}>
              <SpeakingWaves borderColor={s.ringBorder} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Núcleo — orbe de vidro clicável */}
      <motion.button
        onClick={onClick}
        className="relative z-10 flex items-center justify-center rounded-full cursor-pointer focus:outline-none"
        style={{
          width: 160,
          height: 160,
          background: s.coreGradient,
          border: `1px solid ${s.coreBorder}`,
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          boxShadow: `0 0 48px ${s.glow}, inset 0 1px 0 rgba(255,255,255,0.07)`,
        }}
        variants={coreVariants}
        animate={state}
        whileTap={{ scale: 0.96 }}
        aria-label={`Assistente: ${state}`}
      >
        {/* Ponto interior — indicador de estado */}
        <motion.div
          className="rounded-full"
          style={{
            width: 14,
            height: 14,
            backgroundColor: s.dotColor,
            boxShadow: `0 0 12px ${s.dotColor}`,
          }}
          variants={dotVariants}
          animate={state}
          transition={{ duration: 0.4 }}
        />
      </motion.button>
    </div>
  )
}
