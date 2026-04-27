'use client'

import { useMemo } from 'react'
import { useQuintaFeiraUI } from '@/hooks/useQuintaFeiraUI'
import { VoiceOrb } from '@/components/VoiceOrb'
import { ChatOverlay } from '@/components/ChatOverlay'
import { ControlDeck } from '@/components/ControlDeck'
import { AudioPlayer } from '@/components/AudioPlayer'

// Label de estado exibido abaixo do orbe
const STATE_LABEL: Record<string, string> = {
  idle:       'Aguardando',
  listening:  'Ouvindo...',
  processing: 'Processando',
  speaking:   'Respondendo',
}

export default function Page() {
  const {
    orbState,
    isChatOpen,
    isMuted,
    isSpeaking,
    messages,
    isConnected,
    status,
    toggleChat,
    toggleMute,
    endSession,
    sendTextMessage,
    onAudioStart,
    onAudioEnd,
  } = useQuintaFeiraUI()

  // Último áudio da IA para tocar via AudioPlayer
  const latestAudio = useMemo(() => {
    const assistantMsgs = messages.filter((m) => m.role === 'assistant' && m.audio)
    return assistantMsgs.at(-1)?.audio
  }, [messages])

  return (
    <main className="w-screen h-screen overflow-hidden flex items-center justify-center relative select-none deck-bg">

      {/* Grade HUD de fundo */}
      <div className="hud-grid absolute inset-0 pointer-events-none" />

      {/* --- Blob atmosférico (preservado do design original) --- */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="relative w-96 h-96">
          <div
            className="absolute inset-0 rounded-full blur-3xl"
            style={{
              backgroundColor:
                orbState === 'listening'  ? 'rgba(52,211,153,0.28)' :
                orbState === 'processing' ? 'rgba(99,102,241,0.22)' :
                orbState === 'speaking'   ? 'rgba(20,184,166,0.32)' :
                                            'rgba(6,182,212,0.18)',
              animation: 'blob-spin-fast 8s cubic-bezier(.25,.46,.45,.94) infinite',
              mixBlendMode: 'screen',
              transition: 'background-color 0.6s ease',
            }}
          />
          <div
            className="absolute inset-0 rounded-full blur-3xl"
            style={{
              backgroundColor: 'rgba(6,182,212,0.22)',
              animation: 'blob-spin-reverse 12s cubic-bezier(.25,.46,.45,.94) infinite',
              mixBlendMode: 'lighten',
            }}
          />
          <div
            className="absolute inset-0 rounded-full blur-3xl"
            style={{
              backgroundColor: 'rgba(15,23,42,0.25)',
              animation: 'blob-pulse-core 5s ease-in-out infinite',
            }}
          />
          <div
            className="absolute inset-0 rounded-full blur-3xl"
            style={{
              backgroundColor: 'rgba(30,58,138,0.20)',
              animation: 'blob-spin-slow 14s cubic-bezier(.25,.46,.45,.94) infinite',
              mixBlendMode: 'multiply',
            }}
          />
          <div
            className="absolute inset-0 rounded-full blur-3xl"
            style={{
              backgroundColor: 'rgba(20,184,166,0.14)',
              animation: 'blob-pulse-reverse 4s ease-in-out infinite',
            }}
          />
        </div>
      </div>

      {/* --- VoiceOrb central --- */}
      <div className="relative z-10 flex flex-col items-center gap-5">
        <VoiceOrb state={orbState} onClick={toggleMute} />

        {/* Label de estado */}
        <p
          className="text-xs font-mono tracking-[0.20em] uppercase transition-all duration-300"
          style={{
            color:
              orbState === 'idle'
                ? 'rgba(100,116,139,0.55)'
                : 'rgba(6,182,212,0.70)',
            textShadow:
              orbState !== 'idle'
                ? '0 0 12px rgba(6,182,212,0.35)'
                : 'none',
          }}
        >
          {STATE_LABEL[orbState]}
        </p>
      </div>

      {/* --- ChatOverlay (painel lateral) --- */}
      <ChatOverlay
        isOpen={isChatOpen}
        messages={messages}
        onClose={toggleChat}
        onSendMessage={sendTextMessage}
      />

      {/* --- ControlDeck (dock inferior) --- */}
      <ControlDeck
        isChatOpen={isChatOpen}
        isMuted={isMuted}
        isConnected={isConnected}
        status={status}
        onToggleChat={toggleChat}
        onToggleMute={toggleMute}
        onEndSession={endSession}
      />

      {/* --- AudioPlayer oculto (reproduz respostas com áudio) --- */}
      {latestAudio && (
        <AudioPlayer
          audioBase64={latestAudio}
          autoplay
          onPlayStart={onAudioStart}
          onPlayEnd={onAudioEnd}
        />
      )}

      {/* Animações CSS dos blobs (preservadas do design original) */}
      <style>{`
        @keyframes blob-spin-fast {
          0%   { transform: rotate(0deg)   scaleX(1)    scaleY(1);    }
          25%  { transform: rotate(90deg)  scaleX(1.15) scaleY(0.85); }
          50%  { transform: rotate(180deg) scaleX(0.9)  scaleY(1.1);  }
          75%  { transform: rotate(270deg) scaleX(1.05) scaleY(0.95); }
          100% { transform: rotate(360deg) scaleX(1)    scaleY(1);    }
        }
        @keyframes blob-spin-reverse {
          0%   { transform: rotate(0deg)    scaleX(0.85) scaleY(1.15); }
          33%  { transform: rotate(-120deg) scaleX(1.1)  scaleY(0.9);  }
          66%  { transform: rotate(-240deg) scaleX(0.95) scaleY(1.05); }
          100% { transform: rotate(-360deg) scaleX(0.85) scaleY(1.15); }
        }
        @keyframes blob-spin-slow {
          0%   { transform: rotate(0deg)   scale(0.95); }
          50%  { transform: rotate(180deg) scale(1.05); }
          100% { transform: rotate(360deg) scale(0.95); }
        }
        @keyframes blob-pulse-core {
          0%, 100% { transform: scale(1)    translateY(0px);  opacity: 0.5; }
          50%      { transform: scale(1.1)  translateY(-8px); opacity: 0.8; }
        }
        @keyframes blob-pulse-reverse {
          0%, 100% { transform: scale(1.05); opacity: 0.4; }
          50%      { transform: scale(0.95); opacity: 0.6; }
        }
      `}</style>
    </main>
  )
}
