'use client'

import { useCallback } from 'react'
import { useQuintaFeiraUI, HTTP_BASE } from '@/hooks/useQuintaFeiraUI'
import { useSystemContext } from '@/hooks/useSystemContext'
import { VoiceOrb } from '@/components/VoiceOrb'
import { ChatOverlay } from '@/components/ChatOverlay'
import { ControlDeck } from '@/components/ControlDeck'
import { MediaPlayer } from '@/components/MediaPlayer'
import { Visor } from '@/components/Visor'
import { HologramLayer } from '@/components/holo/HologramLayer'
import { SystemHUD } from '@/components/SystemHUD'
import { MemoryPanel } from '@/components/MemoryPanel'
import { ApprovalCard } from '@/components/ApprovalCard'
import { NowStrip } from '@/components/NowStrip'

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
    isMemoryOpen,
    isMuted,
    narrationOn,
    ambientOn,
    micWarning,
    messages,
    isConnected,
    isLoading,
    status,
    intermediateStatus,
    activeMedia,
    activeVisor,
    activeHolo,
    clearHolo,
    narrationIndex,
    proactiveAlert,
    approvals,
    respondApproval,
    autonomyMode,
    cycleAutonomy,
    activity,
    streamingText,
    canStop,
    stopEverything,
    toggleChat,
    toggleMemory,
    toggleMute,
    toggleNarration,
    toggleAmbient,
    showNews,
    endSession,
    clearMedia,
    clearVisor,
    sendTextMessage,
    onAudioStart,
    onAudioEnd,
  } = useQuintaFeiraUI()

  const { snapshot, online } = useSystemContext(HTTP_BASE)

  // Chip de sugestão: abre o chat e já envia a pergunta
  const askQuick = useCallback(
    (text: string) => {
      if (!isChatOpen) toggleChat()
      void sendTextMessage(text)
    },
    [isChatOpen, toggleChat, sendTextMessage],
  )

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

      {/* --- HUD de sistema (relógio, clima, CPU/RAM, bateria, app em foco) --- */}
      <SystemHUD snapshot={snapshot} online={online} />

      {/* --- VoiceOrb central --- */}
      <div className="relative z-10 flex flex-col items-center gap-5">
        <VoiceOrb state={orbState} onClick={toggleMute} />

        {/* Label de estado + passo intermediário */}
        <div className="flex flex-col items-center gap-1.5 min-h-[40px]">
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
          {/* Faixa "Agora": o que ela está fazendo (ferramenta, aprovação pendente ou pensando) */}
          <NowStrip activity={activity} isLoading={isLoading} waitingApproval={approvals.length > 0} />
          {micWarning && !isMuted ? (
            <p className="max-w-xs text-center text-[11px] leading-relaxed text-amber-300/80">
              {micWarning}
            </p>
          ) : null}
          {!micWarning && orbState === 'listening' ? (
            <p className="text-[10px] font-mono tracking-widest text-emerald-300/50">
              diga &quot;Quinta&quot; + seu comando
            </p>
          ) : null}
        </div>
      </div>

      {/* --- Chips de sugestão (só com a tela limpa) --- */}
      {!isChatOpen && !isMemoryOpen ? (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-30 flex flex-wrap justify-center gap-2 max-w-[92vw]">
          {[
            { label: 'O que importa hoje?', run: showNews },
            { label: 'Como está o sistema?', run: () => askQuick('Como está o sistema agora? CPU, memória, bateria.') },
            { label: 'Me dá um conselho', run: () => askQuick('Olha meu contexto de agora e me dá um conselho útil.') },
            { label: 'O que você sabe de mim?', run: toggleMemory },
          ].map((chip) => (
            <button
              key={chip.label}
              onClick={chip.run}
              className="px-3.5 py-1.5 rounded-full text-[11px] font-mono transition-all
                         text-slate-400 hover:text-cyan-200 hover:scale-105"
              style={{
                background: 'rgba(10,20,32,0.62)',
                border: '1px solid rgba(6,182,212,0.14)',
                backdropFilter: 'blur(12px)',
                WebkitBackdropFilter: 'blur(12px)',
              }}
            >
              {chip.label}
            </button>
          ))}
        </div>
      ) : null}

      {/* --- ChatOverlay (painel lateral direito) --- */}
      <ChatOverlay
        isOpen={isChatOpen}
        messages={messages}
        isConnected={isConnected}
        isLoading={isLoading}
        intermediateStatus={intermediateStatus}
        streamingText={streamingText}
        onClose={toggleChat}
        onSendMessage={sendTextMessage}
      />

      {/* --- MemoryPanel (painel lateral esquerdo: o que ela aprendeu) --- */}
      <MemoryPanel isOpen={isMemoryOpen} httpBase={HTTP_BASE} onClose={toggleMemory} />

      {/* --- ControlDeck (dock inferior) --- */}
      <ControlDeck
        isChatOpen={isChatOpen}
        isMuted={isMuted}
        isMemoryOpen={isMemoryOpen}
        narrationOn={narrationOn}
        ambientOn={ambientOn}
        canStop={canStop}
        isConnected={isConnected}
        status={status}
        autonomyMode={autonomyMode}
        onCycleAutonomy={cycleAutonomy}
        onToggleChat={toggleChat}
        onToggleMute={toggleMute}
        onShowNews={showNews}
        onToggleMemory={toggleMemory}
        onToggleNarration={toggleNarration}
        onToggleAmbient={toggleAmbient}
        onStop={stopEverything}
        onEndSession={endSession}
      />

      {/* --- MediaPlayer flutuante (YouTube + áudio base64) --- */}
      <MediaPlayer
        media={activeMedia}
        onClose={clearMedia}
        onPlayStart={onAudioStart}
        onPlayEnd={onAudioEnd}
      />

      {/* --- Visor visual (card de notícia / gráfico / imagem) --- */}
      <Visor content={activeVisor} onClose={clearVisor} activeIndex={narrationIndex} />

      {/* --- Holograma (globo 3D + painéis de mapa/viagem) --- */}
      <HologramLayer holo={activeHolo} onClose={clearHolo} />

      {/* --- Aprovação: a Quinta pergunta antes de agir (WhatsApp, terminal, arquivos...) --- */}
      <ApprovalCard approvals={approvals} onRespond={respondApproval} />

      {/* --- Toast de aviso proativo (bateria, CPU, clima, pausa...) --- */}
      {proactiveAlert ? (
        <div
          className="fixed top-5 left-1/2 -translate-x-1/2 z-50 max-w-[90vw]
                     rounded-full border border-cyan-500/30 bg-zinc-950/90 backdrop-blur-xl
                     px-5 py-2.5 shadow-2xl shadow-cyan-950/40 flex items-center gap-3"
          style={{ animation: 'fadeInDown 0.35s ease-out' }}
        >
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse flex-shrink-0" />
          <span className="text-sm text-zinc-100">{proactiveAlert}</span>
          <style>{`
            @keyframes fadeInDown {
              0%   { opacity: 0; transform: translate(-50%, -10px); }
              100% { opacity: 1; transform: translate(-50%, 0); }
            }
          `}</style>
        </div>
      ) : null}

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
