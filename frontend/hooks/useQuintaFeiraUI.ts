'use client'

/**
 * useQuintaFeiraUI — Hook de orquestração de UI.
 *
 * Responsabilidade única: compor useQuintaFeira (WS) + useSpeechRecognition
 * e derivar o estado visual (OrbState) que os componentes consomem.
 * Nenhum componente acessa os hooks primitivos diretamente.
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { useQuintaFeira } from './useQuintaFeira'
import { useSpeechRecognition } from './useSpeechRecognition'
import type { Message, ConnectionStatus, OrbState } from '@/types'

export interface UseQuintaFeiraUIReturn {
  orbState: OrbState
  isChatOpen: boolean
  isMuted: boolean
  isSpeaking: boolean
  messages: Message[]
  isConnected: boolean
  status: ConnectionStatus
  toggleChat: () => void
  toggleMute: () => void
  endSession: () => void
  sendTextMessage: (text: string) => Promise<void>
  onAudioStart: () => void
  onAudioEnd: () => void
}

export function useQuintaFeiraUI(): UseQuintaFeiraUIReturn {
  const [isChatOpen, setIsChatOpen] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)

  // Refs para callbacks estáveis sem acoplamento circular entre hooks
  const sendMessageRef = useRef<(text: string) => Promise<void>>(async () => {})
  const setAISpeakingRef = useRef<(v: boolean) => void>(() => {})
  const audioFallbackRef = useRef<NodeJS.Timeout | null>(null)
  const speechStartRef = useRef<() => void>(() => {})
  const speechStopRef = useRef<() => void>(() => {})

  // --- Camada WS ---
  const { isConnected, status, messages, isLoading, sendMessage, disconnect } =
    useQuintaFeira({
      onMessage: useCallback((response) => {
        // Quando o backend envia áudio, sinaliza "speaking" antes do AudioPlayer tocar
        if (response.audio) {
          setIsSpeaking(true)
          setAISpeakingRef.current(true)
        }
      }, []),
    })

  // Manter ref de sendMessage sempre atualizada
  useEffect(() => {
    sendMessageRef.current = sendMessage
  }, [sendMessage])

  // --- Camada de voz ---
  // onTranscription é estável (usa ref internamente), evitando loops de dependência
  const speech = useSpeechRecognition({
    isWakeWordEnabled: !isMuted,
    onTranscription: useCallback(async (text: string) => {
      if (text.trim()) {
        await sendMessageRef.current(text)
      }
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

  // --- Estado visual derivado ---
  const orbState = useMemo<OrbState>(() => {
    if (isSpeaking) return 'speaking'
    if (isLoading) return 'processing'
    if (speech.isListening) return 'listening'
    return 'idle'
  }, [isSpeaking, isLoading, speech.isListening])

  // --- Ações ---
  const toggleChat = useCallback(() => setIsChatOpen((v) => !v), [])

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

  const endSession = useCallback(() => {
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
    isMuted,
    isSpeaking,
    messages,
    isConnected,
    status,
    toggleChat,
    toggleMute,
    endSession,
    sendTextMessage: sendMessage,
    onAudioStart,
    onAudioEnd,
  }
}
