"use client";

// frontend/hooks/useSpeechRecognition.ts
// Hook customizado para Speech Recognition com V1 State Machine restaurada
// Máquina de Estados: IDLE → LISTENING → WAKE_DETECTED → AWAITING_COMMAND

import { useEffect, useRef, useState, useCallback } from 'react';

type SpeechRecognitionInstance = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: ((event: SpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

type SpeechResult = {
  isFinal: boolean;
  0: {
    transcript: string;
    confidence: number;
  };
};

type SpeechResultEvent = {
  resultIndex: number;
  results: ArrayLike<SpeechResult>;
};

type SpeechErrorEvent = {
  error: string;
};

interface UseSpeechRecognitionConfig {
  language?: string;
  onTranscription?: (text: string) => void;
  onError?: (error: string) => void;
  flushTimeout?: number;
  maxAlternatives?: number;
  continuous?: boolean;
  interimResults?: boolean;
  onWakewordDetected?: () => void;
  onBrowserWarning?: (msg: string) => void;
}

interface TranscriptionResult {
  text: string;
  isFinal: boolean;
  confidence: number;
  timestamp: number;
}

// ========== STATE MACHINE TYPES ==========
type WakeWordState = 'idle' | 'listening' | 'wake_detected' | 'awaiting_command';

interface WakeWordStateMachine {
  state: WakeWordState;
  wakeWordBuffer: string;
  partialTranscript: string;
  wakeTimeout?: NodeJS.Timeout;
  commandTimeout?: NodeJS.Timeout;
  detectedTime?: number;
}

interface BrowserCompatibility {
  isChrome: boolean;
  isBrave: boolean;
  isEdge: boolean;
  warning?: string;
}

export function useSpeechRecognition({
  language = 'pt-BR',
  onTranscription,
  onError,
  onWakewordDetected,
  onBrowserWarning,
  flushTimeout = 1400,
  maxAlternatives = 1,
  continuous = true,
  interimResults = true,
}: UseSpeechRecognitionConfig = {}) {

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const bufferRef = useRef<string>("");
  const flushTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // ===== V1 STATE MACHINE: Wake Word + Await Command =====
  const stateRef = useRef<WakeWordStateMachine>({
    state: 'idle',
    wakeWordBuffer: '',
    partialTranscript: '',
    detectedTime: undefined,
  });
  
  const [isListening, setIsListening] = useState(false);
  const [diagnostic, setDiagnostic] = useState("");
  const [lastTranscription, setLastTranscription] = useState<TranscriptionResult | null>(null);
  const [browserCompat, setBrowserCompat] = useState<BrowserCompatibility>({ isChrome: false, isBrave: false, isEdge: false });
  
  // ===== PREVENT INFINITE COMPAT UPDATES =====
  const prevCompatRef = useRef<string>("");

  const getSpeechRecognitionConstructor = useCallback(() => {
    if (typeof window === "undefined") return undefined;
    const w = window as typeof window & {
      SpeechRecognition?: SpeechRecognitionCtor;
      webkitSpeechRecognition?: SpeechRecognitionCtor;
    };
    return w.SpeechRecognition || w.webkitSpeechRecognition;
  }, []);

  // ===== BROWSER COMPATIBILITY CHECK =====
  const detectBrowserCompat = useCallback((): BrowserCompatibility => {
    if (typeof window === "undefined") {
      return { isChrome: false, isBrave: false, isEdge: false };
    }
    
    const ua = navigator.userAgent;
    const isChrome = /Chrome/.test(ua) && !/Chromium/.test(ua) && !/Brave/.test(ua);
    const isBrave = /Brave/.test(ua);
    const isEdge = /Edg/.test(ua);
    
    let warning: string | undefined;
    if (isBrave) {
      warning = "⚠️ AVISO: Brave + Speech Recognition = erro de 'network'. Use Google Chrome para melhor compatibilidade.";
    }
    
    const compat = { isChrome, isBrave, isEdge, warning };
    
    // ===== ONLY UPDATE IF COMPAT ACTUALLY CHANGED =====
    const compatJson = JSON.stringify(compat);
    if (prevCompatRef.current !== compatJson) {
      prevCompatRef.current = compatJson;
      setBrowserCompat(compat);
    }
    
    if (warning && onBrowserWarning) {
      onBrowserWarning(warning);
    }
    
    return compat;
  }, [onBrowserWarning]);

  // Chamar ao mount (apenas uma vez)
  useEffect(() => {
    detectBrowserCompat();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Validar que navegador suporta
  const isSupported = useCallback(() => {
    return !!getSpeechRecognitionConstructor();
  }, [getSpeechRecognitionConstructor]);

  // Normalizar texto (remover acentos, símbolos, etc)
  const normalizeText = useCallback((text: string): string => {
    return text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-zA-Z0-9\s\-]/g, " ")
      .replace(/\s+/g, " ")
      .toLowerCase()
      .trim();
  }, []);

  // ===== V1 WAKE WORD DETECTION (Máquina de Estados) =====
  const contemPalavraQueinta = useCallback((texto: string): boolean => {
    const t = normalizeText(texto);
    return /quinta[\s-]*(feira|fera)/.test(t) || 
           t.includes("quintafeira") || 
           t.includes("quintafera");
  }, [normalizeText]);

  const handleWakeWordDetected = useCallback(() => {
    const state = stateRef.current;
    state.state = 'wake_detected';
    state.detectedTime = Date.now();
    state.wakeWordBuffer = '';
    
    // Emitir callback
    if (onWakewordDetected) onWakewordDetected();
    
    console.log('[WAKE_WORD] Detectado! Aguardando comando...');
    setDiagnostic("🔔 Palavra-chave detectada. Fale seu comando (timeout 3.2s)");
    
    // Timeout: aguardar comando por 3.2s
    if (state.commandTimeout) clearTimeout(state.commandTimeout);
    state.commandTimeout = setTimeout(() => {
      console.log('[TIMEOUT] Nenhum comando recebido em 3.2s');
      state.state = 'idle';
      setDiagnostic("⏱️ Timeout: nenhum comando detectado");
    }, 3200);
  }, [onWakewordDetected]);

  // ===== V1 PARTIAL WAKE WORD BUFFER: Ouve "quinta" → espera "feira" por 2.2s =====
  const handlePartialQuinta = useCallback((texto: string) => {
    const state = stateRef.current;
    const t = normalizeText(texto);
    
    // Se ouve "quinta" mas não "feira"
    if (t.includes("quinta") && !t.includes("feira")) {
      state.wakeWordBuffer = 'quinta_pending';
      console.log('[BUFFER_QUINTA] Ouviu "quinta", aguardando "feira"...');
      setDiagnostic("🔊 Detectei 'quinta'... aguardando 'feira' (2.2s)");
      
      if (state.wakeTimeout) clearTimeout(state.wakeTimeout);
      state.wakeTimeout = setTimeout(() => {
        // Completar comando mesmo sem "feira"?
        if (state.wakeWordBuffer === 'quinta_pending') {
          console.log('[TIMEOUT_QUINTA] Palavra "feira" não completada');
          state.wakeWordBuffer = '';
        }
      }, 2200);
    }
  }, [normalizeText]);

  // Extrai comando após wake
  const extrairComando = useCallback((texto: string): string => {
    return normalizeText(texto)
      .replace(/quintafeira/gi, "")
      .replace(/quinta[\s-]*feira/gi, "")
      .trim();
  }, [normalizeText]);

  // Flush do buffer: envia transcricao quando termina
  const flushBuffer = useCallback(() => {
    const text = bufferRef.current.trim();
    bufferRef.current = "";
    const state = stateRef.current;
    
    if (!text) {
      setDiagnostic("❌ Nenhuma transcrição capturada");
      return;
    }

    const normalized = normalizeText(text);
    
    // ===== V1 STATE MACHINE LOGIC =====
    if (state.state === 'idle' || state.state === 'listening') {
      // Estado IDLE/LISTENING: procura wake word
      if (contemPalavraQueinta(text)) {
        handleWakeWordDetected();
        // Checar se tem comando inline ("quinta feira toca rock")
        const comando = extrairComando(text);
        if (comando) {
          console.log('[INLINE_COMMAND] Detectado: ' + comando);
          state.state = 'idle';
          if (state.commandTimeout) clearTimeout(state.commandTimeout);
          setLastTranscription({
            text: comando,
            isFinal: true,
            confidence: 0.85,
            timestamp: Date.now()
          });
          onTranscription?.(comando);
        }
      } else {
        handlePartialQuinta(text);
      }
    } else if (state.state === 'wake_detected' || state.state === 'awaiting_command') {
      // Estado WAKE: aguardando comando
      const comando = extrairComando(text);
      if (comando) {
        console.log('[COMMAND_RECEIVED] ' + comando);
        state.state = 'idle';
        if (state.commandTimeout) clearTimeout(state.commandTimeout);
        
        setLastTranscription({
          text: comando,
          isFinal: true,
          confidence: 0.85,
          timestamp: Date.now()
        });
        onTranscription?.(comando);
      } else {
        console.log('[NO_COMMAND] Silêncio após wake word');
        state.state = 'idle';
      }
    }
  }, [normalizeText, contemPalavraQueinta, handleWakeWordDetected, handlePartialQuinta, extrairComando, onTranscription]);

  // Iniciar escuta
  const start = useCallback(() => {
    if (!isSupported()) {
      const msg = "Navegador não suporta Speech Recognition. Use Google Chrome.";
      setDiagnostic(`❌ ${msg}`);
      onError?.(msg);
      return;
    }

    const SpeechRecognitionCtor = getSpeechRecognitionConstructor();
    if (!SpeechRecognitionCtor) {
      const msg = "Speech Recognition indisponivel neste ambiente.";
      setDiagnostic(msg);
      onError?.(msg);
      return;
    }

    const recognition = new SpeechRecognitionCtor();
    recognitionRef.current = recognition;

    recognition.lang = language;
    recognition.continuous = continuous;
    recognition.interimResults = interimResults;
    recognition.maxAlternatives = maxAlternatives;

    recognition.onstart = () => {
      setIsListening(true);
      setDiagnostic("🎤 Microfone ativo, pode falar...");
      bufferRef.current = "";
    };

    recognition.onresult = (event: SpeechResultEvent) => {
      let isFinal = false;
      
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (!result?.[0]) continue;

        isFinal = result.isFinal;
        
        if (isFinal) {
          bufferRef.current = `${bufferRef.current} ${result[0].transcript}`.trim();
          
          // Log detalhado para debug
          console.log('[SPEECH]', {
            transcript: result[0].transcript,
            confidence: result[0].confidence,
            isFinal: true,
            timestamp: new Date().toLocaleTimeString()
          });
        } else {
          // Resultado interim (em progresso)
          // Mostrar em tempo real
          setDiagnostic(`🔊 ${result[0].transcript}...`);
        }
      }

      // Se foi final, agendar flush
      if (isFinal) {
        if (flushTimeoutRef.current) clearTimeout(flushTimeoutRef.current);
        flushTimeoutRef.current = setTimeout(() => {
          try {
            recognition.stop();
          } catch {}
          flushBuffer();
        }, flushTimeout);
      }
    };

    recognition.onerror = (event: SpeechErrorEvent) => {
      const errorMsg = `Erro mic: ${event.error}`;
      if (event.error !== "no-speech") {
        setDiagnostic(`❌ ${errorMsg}`);
        onError?.(event.error);
      }
      console.error('[SPEECH ERROR]', event.error);
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      if (flushTimeoutRef.current) clearTimeout(flushTimeoutRef.current);
    };

    try {
      recognition.start();
    } catch (e) {
      console.error("Erro ao iniciar recognition:", e);
      setDiagnostic(`❌ Erro ao iniciar microfone`);
      onError?.((e as Error).message);
    }
  }, [isSupported, getSpeechRecognitionConstructor, language, continuous, interimResults, maxAlternatives, flushTimeout, flushBuffer, onError]);

  // Parar escuta
  const stop = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }

    if (flushTimeoutRef.current) {
      clearTimeout(flushTimeoutRef.current);
      flushTimeoutRef.current = null;
    }

    setIsListening(false);
  }, []);

    // Limpar recursos ao desmontar
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    isListening,
    diagnostic,
    lastTranscription,
    start,
    stop,
    isSupported,
    normalizeText,
    browserCompat,
    wakeMachineState: stateRef.current.state,
  };
}
