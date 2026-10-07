'use client'

/**
 * useQuintaFeiraUI — Hook de orquestração de UI.
 *
 * Responsabilidade única: compor useQuintaFeira (WS) + useSpeechRecognition
 * e derivar o estado visual (OrbState) que os componentes consomem.
 * Nenhum componente acessa os hooks primitivos diretamente.
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import {
  useQuintaFeira,
  onSpeakingChange,
  stopSpeaking,
  isNarrationEnabled,
  setNarrationEnabled,
} from './useQuintaFeira'
import { useSpeechRecognition } from './useSpeechRecognition'
import type {
  Message,
  ConnectionStatus,
  OrbState,
  IntermediateStatus,
  ApprovalRequest,
  AutonomyMode,
  AgoraActivity,
} from '@/types'
import type { ActiveMedia } from '@/components/MediaPlayer'
import type { VisorContent } from '@/components/Visor'
import type { HoloPayload } from '@/types'

// Base HTTP do backend (mesmo host/porta do WebSocket)
export const HTTP_BASE = `http://${process.env.NEXT_PUBLIC_WS_HOST || '127.0.0.1'}:${
  process.env.NEXT_PUBLIC_WS_PORT || '8000'
}`

export interface UseQuintaFeiraUIReturn {
  orbState: OrbState
  isChatOpen: boolean
  isMemoryOpen: boolean
  isMuted: boolean
  isSpeaking: boolean
  narrationOn: boolean
  ambientOn: boolean
  micWarning: string | null
  messages: Message[]
  isConnected: boolean
  isLoading: boolean
  status: ConnectionStatus
  intermediateStatus: IntermediateStatus | null
  activeMedia: ActiveMedia | null
  activeVisor: VisorContent | null
  activeHolo: HoloPayload | null
  clearHolo: () => void
  narrationIndex: number | null
  proactiveAlert: string | null
  approvals: ApprovalRequest[]
  respondApproval: (approvalId: string, permitido: boolean) => void
  autonomyMode: AutonomyMode | null
  cycleAutonomy: () => void
  activity: AgoraActivity | null
  streamingText: string | null
  canStop: boolean
  stopEverything: () => void
  toggleChat: () => void
  toggleMemory: () => void
  toggleMute: () => void
  toggleNarration: () => void
  toggleAmbient: () => void
  stopVoice: () => void
  showNews: () => void
  endSession: () => void
  clearMedia: () => void
  clearVisor: () => void
  sendTextMessage: (text: string) => Promise<void>
  onAudioStart: () => void
  onAudioEnd: () => void
}

export function useQuintaFeiraUI(): UseQuintaFeiraUIReturn {
  const [isChatOpen, setIsChatOpen] = useState(false)
  const [isMemoryOpen, setIsMemoryOpen] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [narrationOn, setNarrationOn] = useState(true)
  const [micWarning, setMicWarning] = useState<string | null>(null)
  const [ambientOn, setAmbientOn] = useState(false)

  // Refs para callbacks estáveis sem acoplamento circular entre hooks
  const sendMessageRef = useRef<(text: string) => Promise<void>>(async () => {})
  const ambientSpeechRef = useRef<(text: string) => Promise<boolean>>(async () => false)
  const setAISpeakingRef = useRef<(v: boolean) => void>(() => {})
  const audioFallbackRef = useRef<NodeJS.Timeout | null>(null)
  const speechStartRef = useRef<() => void>(() => {})
  const speechStopRef = useRef<() => void>(() => {})

  // --- Camada WS ---
  const {
    isConnected,
    connectionStatus,
    messages,
    isLoading,
    intermediateStatus,
    sendMessage,
    ambientSpeech,
    loadNews,
    disconnect,
    activeMedia,
    clearMedia,
    activeVisor,
    clearVisor,
    activeHolo,
    clearHolo,
    narrationIndex,
    proactiveAlert,
    approvals,
    respondApproval,
    activity,
    streamingText,
    stopRun,
  } = useQuintaFeira()

  // --- Autonomia: quando a Quinta pergunta antes de agir (backend GET/POST /autonomia) ---
  const [autonomyMode, setAutonomyMode] = useState<AutonomyMode | null>(null)

  useEffect(() => {
    if (!isConnected) return
    let cancelled = false
    fetch(`${HTTP_BASE}/autonomia`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d?.modo) setAutonomyMode(d.modo as AutonomyMode)
      })
      .catch(() => {
        /* backend fora: o botão simplesmente não mostra o modo */
      })
    return () => {
      cancelled = true
    }
  }, [isConnected])

  // perguntar_sempre -> so_perigoso -> autonoma -> perguntar_sempre
  const cycleAutonomy = useCallback(() => {
    if (!autonomyMode) return
    const ordem: AutonomyMode[] = ['perguntar_sempre', 'so_perigoso', 'autonoma']
    const proximo = ordem[(ordem.indexOf(autonomyMode) + 1) % ordem.length]
    // Tirar as travas é uma decisão que merece um "tem certeza?"
    if (
      proximo === 'autonoma' &&
      typeof window !== 'undefined' &&
      !window.confirm(
        'Modo AUTÔNOMO: a Quinta vai executar ações críticas (enviar WhatsApp, terminal, ' +
          'apagar arquivos) SEM pedir a sua aprovação. Ativar mesmo assim?',
      )
    ) {
      return
    }
    fetch(`${HTTP_BASE}/autonomia`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modo: proximo }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.modo) setAutonomyMode(d.modo as AutonomyMode)
      })
      .catch(() => {
        /* não mudou: o botão continua mostrando o modo real */
      })
  }, [autonomyMode])

  // Manter refs sempre atualizadas
  useEffect(() => {
    sendMessageRef.current = sendMessage
  }, [sendMessage])
  useEffect(() => {
    ambientSpeechRef.current = ambientSpeech
  }, [ambientSpeech])

  // Estado inicial da escuta ambiente (persistido)
  useEffect(() => {
    if (typeof window !== 'undefined') {
      setAmbientOn(window.localStorage.getItem('qf_ambient') === '1')
    }
  }, [])

  // --- Camada de voz ---
  // onTranscription é estável (usa ref internamente), evitando loops de dependência
  const speech = useSpeechRecognition({
    isWakeWordEnabled: !isMuted,
    ambientMode: ambientOn && !isMuted,
    onAmbientSpeech: useCallback((text: string) => {
      void ambientSpeechRef.current(text)
    }, []),
    onTranscription: useCallback(async (text: string) => {
      if (text.trim()) {
        await sendMessageRef.current(text)
      }
    }, []),
    // Voz quebrada não pode morrer em silêncio: Brave bloqueia o serviço de
    // fala e o mic negado também — o usuário precisa SABER por que ela não ouve.
    onBrowserWarning: useCallback((msg: string) => {
      setMicWarning(msg)
    }, []),
  })

  // Sync refs de controle de voz
  useEffect(() => {
    setAISpeakingRef.current = speech.setAISpeaking
    speechStartRef.current = speech.start
    speechStopRef.current = speech.stop
  }, [speech.setAISpeaking, speech.start, speech.stop])

  // Iniciar escuta passiva na montagem
  useEffect(() => {
    speechStartRef.current()
  }, []) // mount-only: ref sempre terá o valor correto

  // Estado inicial da narração (persistido em localStorage)
  useEffect(() => {
    setNarrationOn(isNarrationEnabled())
  }, [])

  // A narração TTS (chat, avisos, notícias) também conta como "falando":
  // o orbe pulsa e o microfone pausa pra não ouvir a própria voz dela.
  useEffect(() => {
    const unsubscribe = onSpeakingChange((speaking) => {
      setIsSpeaking(speaking)
      setAISpeakingRef.current(speaking)
    })
    return unsubscribe
  }, [])

  // --- Estado visual derivado ---
  const orbState = useMemo<OrbState>(() => {
    if (isSpeaking) return 'speaking'
    if (isLoading) return 'processing'
    if (speech.isListening) return 'listening'
    return 'idle'
  }, [isSpeaking, isLoading, speech.isListening])

  // --- Ações ---
  const toggleChat = useCallback(() => {
    setIsChatOpen((v) => !v)
    setIsMemoryOpen(false)
  }, [])

  const toggleMemory = useCallback(() => {
    setIsMemoryOpen((v) => !v)
    setIsChatOpen(false)
  }, [])

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const nowMuted = !prev
      // Efeito colateral agendado fora do updater para evitar side-effects em setState
      setTimeout(() => {
        if (nowMuted) {
          speechStopRef.current()
        } else {
          speechStartRef.current()
        }
      }, 0)
      return nowMuted
    })
  }, [])

  const toggleNarration = useCallback(() => {
    setNarrationOn((prev) => {
      const next = !prev
      setNarrationEnabled(next)
      return next
    })
  }, [])

  const toggleAmbient = useCallback(() => {
    setAmbientOn((prev) => {
      const next = !prev
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('qf_ambient', next ? '1' : '0')
      }
      return next
    })
  }, [])

  const stopVoice = useCallback(() => {
    stopSpeaking()
    setIsSpeaking(false)
    setAISpeakingRef.current(false)
  }, [])

  // PARAR tudo: corta a fala e manda o backend cancelar a execução e descartar a fila.
  const stopEverything = useCallback(() => {
    stopSpeaking()
    setIsSpeaking(false)
    setAISpeakingRef.current(false)
    stopRun()
  }, [stopRun])

  const canStop = isLoading || isSpeaking

  // Esc, por prioridade: 1) cartão de aprovação aberto -> é DELE (nega); 2) holograma aberto ->
  // fecha só o holograma; 3) senão, para tudo.
  const holoAberto = activeHolo !== null
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || approvals.length > 0) return
      if (holoAberto) {
        e.preventDefault()
        clearHolo()
        return
      }
      if (!canStop) return
      e.preventDefault()
      stopEverything()
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [approvals.length, canStop, stopEverything, holoAberto, clearHolo])

  const showNews = useCallback(() => {
    void loadNews()
  }, [loadNews])

  const endSession = useCallback(() => {
    stopSpeaking()
    speechStopRef.current()
    disconnect()
    setIsSpeaking(false)
  }, [disconnect])

  // Chamado pelo AudioPlayer quando o áudio começa a tocar
  const onAudioStart = useCallback(() => {
    setIsSpeaking(true)
    setAISpeakingRef.current(true)
    // Fallback de segurança: nunca ficar preso em "speaking"
    if (audioFallbackRef.current) clearTimeout(audioFallbackRef.current)
    audioFallbackRef.current = setTimeout(() => {
      setIsSpeaking(false)
      setAISpeakingRef.current(false)
    }, 60_000)
  }, [])

  // Chamado pelo AudioPlayer quando o áudio termina
  const onAudioEnd = useCallback(() => {
    if (audioFallbackRef.current) clearTimeout(audioFallbackRef.current)
    setIsSpeaking(false)
    setAISpeakingRef.current(false)
  }, [])

  useEffect(() => {
    return () => {
      if (audioFallbackRef.current) clearTimeout(audioFallbackRef.current)
    }
  }, [])

  return {
    orbState,
    isChatOpen,
    isMemoryOpen,
    isMuted,
    isSpeaking,
    narrationOn,
    ambientOn,
    micWarning,
    messages,
    isConnected,
    isLoading,
    status: connectionStatus,
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
    stopVoice,
    showNews,
    endSession,
    clearMedia,
    clearVisor,
    sendTextMessage: sendMessage,
    onAudioStart,
    onAudioEnd,
  }
}
