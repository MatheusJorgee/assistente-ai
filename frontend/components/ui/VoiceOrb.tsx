'use client';

import { motion } from 'framer-motion';
import type { OrbState } from '@/hooks/useQuintaFeiraUI';

interface VoiceOrbProps {
  state: OrbState;
}

export function VoiceOrb({ state }: VoiceOrbProps) {
  return (
    <div className="relative flex items-center justify-center w-64 h-64">
      {/* Outer pulse ring */}
      <motion.div
        className="absolute rounded-full bg-emerald-500/10"
        animate={{
          scale: state === 'listening' ? [1, 1.45, 1] : state === 'processing' ? [1, 1.25, 1] : [1, 1.06, 1],
          opacity: [0.2, 0.5, 0.2],
        }}
        transition={{
          duration: state === 'idle' ? 3.5 : 1.4,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
        style={{ width: 230, height: 230 }}
      />

      {/* Mid ring */}
      <motion.div
        className="absolute rounded-full bg-cyan-500/10"
        animate={{
          scale: state === 'processing' ? [1, 1.18, 1] : 1,
          opacity: state !== 'idle' ? [0.3, 0.6, 0.3] : 0.15,
        }}
        transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut', delay: 0.25 }}
        style={{ width: 165, height: 165 }}
      />

      {/* Core orb */}
      <motion.div
        className="relative z-10 h-32 w-32 rounded-full flex items-center justify-center select-none"
        style={{
          background: 'radial-gradient(circle at 35% 30%, #34d399, #06b6d4, #1e3a5f)',
        }}
        animate={{
          scale:
            state === 'listening'
              ? [1, 1.09, 1]
              : state === 'processing'
              ? [1, 1.04, 1]
              : 1,
          boxShadow:
            state === 'processing'
              ? [
                  '0 0 40px rgba(16,185,129,0.45)',
                  '0 0 80px rgba(16,185,129,0.75)',
                  '0 0 40px rgba(16,185,129,0.45)',
                ]
              : [
                  '0 0 18px rgba(16,185,129,0.2)',
                  '0 0 36px rgba(16,185,129,0.38)',
                  '0 0 18px rgba(16,185,129,0.2)',
                ],
        }}
        transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
      >
        <div className="flex flex-col items-center gap-1">
          <span className="text-white text-[10px] font-bold font-mono tracking-widest">QF</span>
          {state === 'processing' && (
            <span className="flex gap-0.5">
              <span className="h-1 w-1 rounded-full bg-white/70 animate-bounce" />
              <span className="h-1 w-1 rounded-full bg-white/70 animate-bounce [animation-delay:120ms]" />
              <span className="h-1 w-1 rounded-full bg-white/70 animate-bounce [animation-delay:240ms]" />
            </span>
          )}
        </div>
      </motion.div>
    </div>
  );
}
