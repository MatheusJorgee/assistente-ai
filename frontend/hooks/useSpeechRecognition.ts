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
  isWakeWordEnabled?: boolean;  // ← Novo: Controlar se está em modo radar
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
  isWakeWordEnabled = false,  // ← Novo: Default false (desativado por segurança)
}: UseSpeechRecognitionConfig = {}) {

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const bufferRef = useRef<string>("");
  const flushTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isTransitioningRef = useRef(false);  // ← FIX CRÍTICO: Flag de transição para evitar 'aborted'
  
  // ===== HIGH AVAILABILITY: Monitorar saúde do microfone =====
  const ensureListeningIntervalRef = useRef<NodeJS.Timeout | null>(null);  // ← NOVO
  
  // ===== CONTINUOUS LISTENING: Controla parada intencional vs automática =====
  const intentionalStopRef = useRef(false);  // true = utilizador pediu parar; false = apenas aguardando mais fala
  const restartTimeoutRef = useRef<NodeJS.Timeout | null>(null);  // Timeout para reiniciar após silêncio
  const isAISpeakingRef = useRef(false);  // true = IA está a falar; não ativar mic
  
  // ===== WATCHDOG SENSITIVITY: Tracking de silêncio e detecção de fala =====
  const lastResultTimestampRef = useRef<number>(Date.now());  // Timestamp do último resultado isFinal
  const watchdogPausedRef = useRef(false);  // true = watchdog pausado (durante fala)
  
  // ===== WAKE WORD LISTENING: Modo passivo/ativo =====
  const listeningModeRef = useRef<'passive' | 'active'>('passive');  // passive = esperando "Quinta-Feira"; active = gravando comando
  const wakeWordDetectedRef = useRef(false);  // true quando detetou o wake word
  
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
  
  // ===== WATCHDOG: Timer para ressurreição periódica do microfone ✓ NOVO =====
  const microphoneWatchdogRef = useRef<NodeJS.Timeout | null>(null);  // ← Timer de 3 segundos (aumentado)
  
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

  // ===== V1 WAKE WORD DETECTION (Máquina de Estados) - COM SENSIBILIDADE AUMENTADA ✓ NOVO =====
  const contemPalavraQueinta = useCallback((texto: string): boolean => {
    const t = normalizeText(texto);
    
    // ✓ SENSIBILIDADE AUMENTADA: Múltiplas variantes fonéticas + parciais
    return (
      // Variantes normalizadas
      /quinta[\s-]*(feira|fera)/.test(t) || 
      t.includes("quintafeira") || 
      t.includes("quintafera") ||
      // Variantes com erro fonético comum (Speech Recognition errado)
      t.includes("quintafeira") ||
      t.includes("quinta feira") ||
      t.includes("quinta fera") ||
      // PRE-ATIVAÇÃO: Apenas "quinta" sem "feira" ainda (detecção antecipada)
      // Isto torna a detecção MUITO mais rápida
      (/^quinta[\s-]?$/.test(t) || t.endsWith("quinta") || /quinta$/.test(t)) ||
      // Variantes com "q" apenas (muito veloz)
      t === "quinta" ||
      // Erros fonéticos comuns de reconhecimento de fala português
      t.includes("quintafeira") ||
      t.includes("quinte fáira") ||
      t.includes("quinta féra")
    );
  }, [normalizeText]);

  const handleWakeWordDetected = useCallback(() => {
    const state = stateRef.current;
    state.state = 'wake_detected';
    state.detectedTime = Date.now();
    state.wakeWordBuffer = '';
    
    // Mudar para modo ATIVO quando detecta wake word
    listeningModeRef.current = 'active';
    wakeWordDetectedRef.current = true;
    
    // Emitir callback
    if (onWakewordDetected) onWakewordDetected();
    
    console.log('[WAKE_WORD] Detectado! Entrando em modo ATIVO...');
    setDiagnostic("🔔 Palavra-chave detectada. Fale seu comando (timeout 3.2s)");
    
    // Timeout: aguardar comando por 3.2s
    if (state.commandTimeout) clearTimeout(state.commandTimeout);
    state.commandTimeout = setTimeout(() => {
      console.log('[TIMEOUT] Nenhum comando recebido em 3.2s');
      state.state = 'idle';
      listeningModeRef.current = 'passive';  // Voltar ao modo passivo
      wakeWordDetectedRef.current = false;
      setDiagnostic("⏱️ Timeout: nenhum comando detectado. Voltando ao modo passivo...");
    }, 3200);
  }, [onWakewordDetected]);

  // ===== V1 PARTIAL WAKE WORD BUFFER (COM SENSIBILIDADE AUMENTADA) ✓ NOVO =====
  const handlePartialQuinta = useCallback((texto: string) => {
    const state = stateRef.current;
    const t = normalizeText(texto);
    
    // ✓ SENSIBILIDADE AUMENTADA: Detectar "quinta" isolado (não precisa "feira" imediatamente)
    // Isto faz ativação MUITO mais rápida
    if (t.includes("quinta")) {
      state.wakeWordBuffer = 'quinta_pending';
      console.log('[BUFFER_QUINTA] ⚡ Detectei "quinta" - ativação RÁPIDA');
      setDiagnostic("🔔 ⚡ DETECTEI 'QUINTA' - Fale seu comando agora!");
      
      // ✓ TIMEOUT AUMENTADO: 1.5s para receber "feira" (foi 2.2s, agora mais agressivo)
      if (state.wakeTimeout) clearTimeout(state.wakeTimeout);
      state.wakeTimeout = setTimeout(() => {
        // Mesmo sem "feira", se temos "quinta", considera completo
        if (state.wakeWordBuffer === 'quinta_pending') {
          console.log('[TIMEOUT_QUINTA] Completando wake word sem "feira"');
          state.wakeWordBuffer = 'quinta_complete';
          handleWakeWordDetected();  // Ativar MESMO SEM "feira"
        }
      }, 1500);  // ← REDUZIDO de 2.2s para 1.5s (mais rápido)
    }
  }, [normalizeText, handleWakeWordDetected]);

  // Extrai comando após wake
  const extrairComando = useCallback((texto: string): string => {
    // ===== BYPASS: Remover "Quinta Feira" do comando final =====
    let comando = normalizeText(texto)
      .replace(/quintafeira/gi, "")
      .replace(/quinta[\s-]*feira/gi, "")
      .replace(/quinta[\s-]*fera/gi, "")  // ← Adicionar variante
      .replace(/\s+/g, " ")  // Limpar espaços múltiplos
      .trim();
    
    console.log(`[BYPASS_COMANDO] Original: "${texto}" → Limpo: "${comando}"`);
    return comando;
  }, [normalizeText]);

  // ===== HIGH AVAILABILITY: Monitorar saúde do microfone ✓ NOVO =====
  const ensureListeningIsHealthy = useCallback(() => {
    // Limpar qualquer interval anterior
    if (ensureListeningIntervalRef.current) {
      clearInterval(ensureListeningIntervalRef.current);
    }
    
    // Verificar a cada 1 segundo se o radar está ligado mas o microfone desligado
    ensureListeningIntervalRef.current = setInterval(() => {
      // Condições para "doente":
      // 1. Wake word está ativado (isWakeWordEnabled = true)
      // 2. Radar deveria estar ligado (listeningModeRef.current === 'passive' ou 'active')
      // 3. isListening está false (microfone desligado)
      // 4. Não foi parada intencionalmente
      
      if (isWakeWordEnabled && 
          !intentionalStopRef.current && 
          !isAISpeakingRef.current && 
          !isListening &&
          recognitionRef.current === null) {
        
        console.warn('[HIGH_AVAILABILITY] ⚠️ Microfone MORTO detectado! Radar precisa estar ligado mas está desligado.');
        console.warn('[HIGH_AVAILABILITY] Forçando restart do microfone...');
        
        // ✓ FIX: Usar startRef para evitar dependência circular
        // Capturar via closure em vez de dependência
        try {
          // @ts-ignore - chamada dinâmica sem dependência
          if (typeof start === 'function') {
            start();
          }
        } catch (e) {
          console.error('[HIGH_AVAILABILITY] Erro ao forçar restart:', e);
        }
      }
    }, 1000);  // ← Verificar a cada 1 segundo
    
    console.log('[HIGH_AVAILABILITY] ✓ Monitoramento de saúde do microfone ativado');
  }, [isWakeWordEnabled, isListening]);

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
        listeningModeRef.current = 'passive';  // Voltar ao modo passivo após receber comando
        wakeWordDetectedRef.current = false;
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
        listeningModeRef.current = 'passive';  // Voltar ao modo passivo
        wakeWordDetectedRef.current = false;
      }
    }
  }, [normalizeText, contemPalavraQueinta, handleWakeWordDetected, handlePartialQuinta, extrairComando, onTranscription]);

  // Iniciar escuta
  const start = useCallback(() => {
    // ===== PROTEÇÃO ULTRA RIGOROSA: Evitar múltiplas chamadas =====
    if (isTransitioningRef.current) {
      console.warn('[START] Já em transição. Ignorando chamada.');
      return;
    }
    
    if (recognitionRef.current !== null) {
      console.warn('[START] Reconhecimento já ativo. Ignorando start().');
      return;  // ← CRÍTICO: Não tentar start() se já há instância
    }

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

    // ===== Marcar como em transição =====
    isTransitioningRef.current = true;
    console.log('[START] Iniciando microfone (marcando como transitioning)');

    const recognition = new SpeechRecognitionCtor();
    recognitionRef.current = recognition;

    recognition.lang = language;
    // ===== LÓGICA CONDICIONAL: isWakeWordEnabled controla continuous =====
    // Se FALSE: escuta apenas quando ativado manualmente (continuous = false)
    // Se TRUE: escuta contínua e reinicia automaticamente (continuous = true)
    const continuousValue = isWakeWordEnabled ? true : continuous;
    recognition.continuous = continuousValue;
    console.log(`[HOOK_INIT] recognition.continuous configurado para: ${continuousValue} (isWakeWordEnabled=${isWakeWordEnabled})`);
    recognition.interimResults = interimResults;
    recognition.maxAlternatives = maxAlternatives;

    recognition.onstart = () => {
      isTransitioningRef.current = false;  // ← FIX: Transição concluída com sucesso
      setIsListening(true);
      setDiagnostic("🎤 Microfone ativo, pode falar...");
      bufferRef.current = "";
      console.log('[START_SUCCESS] Microfone iniciado - transição completa');
      
      // ===== HIGH AVAILABILITY: Iniciar monitoramento de saúde ✓ NOVO =====
      ensureListeningIsHealthy();
      
      // ===== WATCHDOG: Iniciar ressurreição automática a cada 2s ✓ NOVO =====
      initMicrophoneWatchdog();
    };

    recognition.onresult = (event: SpeechResultEvent) => {
      let isFinal = false;
      let partialText = "";  // ← Acumula resultados parciais para antecipação
      
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (!result?.[0]) continue;

        isFinal = result.isFinal;
        
        if (isFinal) {
          lastResultTimestampRef.current = Date.now();  // ✓ CRÍTICO: Atualizar timestamp
          bufferRef.current = `${bufferRef.current} ${result[0].transcript}`.trim();
          
          // ===== WATCHDOG: Pausar durante fala (timeout curto) =====
          // Quando recebe resultado final, há apenas 1-2s até próxima pausa
          // Não queremos Watchdog reiniciar neste período
          watchdogPausedRef.current = true;
          
          // Log detalhado para debug
          console.log('[SPEECH]', {
            transcript: result[0].transcript,
            confidence: result[0].confidence,
            isFinal: true,
            timestamp: new Date().toLocaleTimeString()
          });
        } else {
          // ===== NOVO: Detecção FRACIONADA para antecipação de Wake Word =====
          // Monitorar resultados parciais (antes da final)
          // ===== WATCHDOG: Pausar enquanto há fala parcial =====
          watchdogPausedRef.current = true;  // Utilizador está a falar!
          
          partialText = result[0].transcript;
          console.log('[PARTIAL_SPEECH] Texto parcial:', partialText);
          
          // SE detecta "Quinta" no parcial → PRE-ACTIVATE
          if (contemPalavraQueinta(partialText) && listeningModeRef.current === 'passive') {
            console.log('[PRE_ACTIVATE] Detectada "Quinta" no parcial - preparando ativação');
            listeningModeRef.current = 'active';  // ← Já passar para ATIVO (antecipação)
            setDiagnostic("🔔 ANTECIPAÇÃO: Detectei 'Quinta'... aguardando comando");
          }
          
          // Resultado interim (em progresso)
          // Mostrar em tempo real
          setDiagnostic(`🔊 ${partialText}...`);
        }
      }

      // ===== STREAM CONTÍNUO: Não chamar stop() automaticamente =====
      // SE foi final, agendar flush (mas NUNCA chamar recognition.stop())
      if (isFinal) {
        if (flushTimeoutRef.current) clearTimeout(flushTimeoutRef.current);
        flushTimeoutRef.current = setTimeout(() => {
          // ← REMOVER: recognition.stop() - deixar stream aberto!
          flushBuffer();
          // Stream continua ativo para próximo ciclo de escuta
          console.log('[STREAM_CONTINUOUS] Buffer enviado, stream continua aberto');
        }, flushTimeout);
      }
    };

    recognition.onerror = (event: SpeechErrorEvent) => {
      // ===== FIX CRÍTICO: Tratar 'aborted' silenciosamente (é transição normal) =====
      if (event.error === 'aborted') {
        console.warn('[SPEECH ERROR] Erro "aborted" detectado - isto é normal durante transições');
        isTransitioningRef.current = false;
        setIsListening(false);
        return;  // ← Não dispara som de erro nem callback de erro
      }
      
      const errorMsg = `Erro mic: ${event.error}`;
      if (event.error !== "no-speech") {
        setDiagnostic(`❌ ${errorMsg}`);
        onError?.(event.error);
        console.error('[SPEECH ERROR]', event.error);
      }
    };

    recognition.onend = () => {
      isTransitioningRef.current = false;  // ← FIX CRÍTICO: Marcar fim de transição
      setIsListening(false);
      recognitionRef.current = null;
      if (flushTimeoutRef.current) clearTimeout(flushTimeoutRef.current);
      
      // ===== WATCHDOG: Resumir verificação (onEnd é o método primário de restart) =====
      watchdogPausedRef.current = false;  // Permitir Watchdog atuar novamente
      lastResultTimestampRef.current = Date.now();  // Reset de silêncio
      
      // ===== CONTINUOUS LISTENING: Reiniciar se não foi intencional E se isWakeWordEnabled=TRUE =====
      // Este é o PRINCIPAL mecanismo de restart (Watchdog só age se isto falhar)
      if (!intentionalStopRef.current && !isAISpeakingRef.current && isWakeWordEnabled) {
        // Parada NÃO foi intencional E Wake Word está ativado (Escuta Passiva)
        // ===== DEBOUNCE CRÍTICO: 500ms (não 300ms!) para liberar hardware do navegador =====
        console.log('[CONTINUOUS_LISTENING] Microfone pausou. Reiniciando em 500ms (debounce)...');
        
        // Se estamos em modo PASSIVE, reiniciar para continuar a escutar
        if (listeningModeRef.current === 'passive') {
          setDiagnostic("⏳ Escuta passiva: reiniciando em 500ms...");
        } else {
          setDiagnostic("⏳ Escuta ativa: reiniciando em 500ms...");
        }
        
        restartTimeoutRef.current = setTimeout(() => {
          if (!intentionalStopRef.current && !isAISpeakingRef.current && isWakeWordEnabled) {
            console.log('[CONTINUOUS_LISTENING] Debounce completo - reiniciando captura de fala');
            // Resetar flag e reiniciar
            intentionalStopRef.current = false;
            try {
              start();
            } catch (e) {
              console.error('[CONTINUOUS_LISTENING] Erro ao reiniciar:', e);
            }
          }
        }, 500);  // ← CRÍTICO: 500ms (aumentado de 300ms) para evitar erro 'aborted'
      } else {
        // Parada foi intencional (utilizador clicou no botão "Parar")
        console.log('[CONTINUOUS_LISTENING] Parada intencional do utilizador');
        intentionalStopRef.current = false;  // Resetar para próxima sessão
      }
    };

    try {
      recognition.start();
    } catch (e) {
      console.error("Erro ao iniciar recognition:", e);
      setDiagnostic(`❌ Erro ao iniciar microfone`);
      onError?.((e as Error).message);
    }
  }, [isSupported, getSpeechRecognitionConstructor, language, continuous, interimResults, maxAlternatives, flushTimeout, flushBuffer, onError, isWakeWordEnabled]);

  // ===== WATCHDOG CONTROL: Pausar e resumir (durante fala de utilizador) =====
  const pauseWatchdog = useCallback(() => {
    watchdogPausedRef.current = true;
    console.log('[WATCHDOG] Pausado manualmente (durante fala)');
  }, []);
  
  const resumeWatchdog = useCallback(() => {
    watchdogPausedRef.current = false;
    lastResultTimestampRef.current = Date.now();  // Reset timestamp
    console.log('[WATCHDOG] Resumido (fala completa)');
  }, []);
  
  // Parar escuta (intencional - não reiniciar)
  const stop = useCallback(() => {
    console.log('[CONTINUOUS_LISTENING] Parando microfone (intencional)');
    intentionalStopRef.current = true;  // Marcar como parada intencional
    watchdogPausedRef.current = true;  // Pausar Watchdog também
    
    // ===== HIGH AVAILABILITY: Parar monitoramento ✓ NOVO =====
    if (ensureListeningIntervalRef.current) {
      clearInterval(ensureListeningIntervalRef.current);
      ensureListeningIntervalRef.current = null;
      console.log('[HIGH_AVAILABILITY] Monitoramento de saúde parado');
    }
    
    if (restartTimeoutRef.current) {
      clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
    
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

  // ===== WATCHDOG: Monitorar e ressuscitar microfone (com detecção inteligente de silêncio) ✓ OTIMIZADO =====
  const initMicrophoneWatchdog = useCallback(() => {
    if (microphoneWatchdogRef.current) {
      clearInterval(microphoneWatchdogRef.current);
    }
    
    watchdogPausedRef.current = false;  // Resetar estado de pausa
    
    microphoneWatchdogRef.current = setInterval(() => {
      // ✓ CRÍTICO: NÃO ressuscitar se Watchdog está pausado (durante fala)
      if (watchdogPausedRef.current) {
        console.log('[WATCHDOG] Pausado - utilizador está a falar ou resultado recente');
        return;
      }
      
      // Condições para ressuscitação:
      // 1. Radar ATIVO (isWakeWordEnabled = true)
      // 2. Microfone DESLIGADO (isListening = false)
      // 3. IA NÃO está falando (isAISpeakingRef.current = false)
      // 4. Silêncio > 5 segundos (nenhum resultado isFinal recente) - AUMENTADO para evitar cortes
      const timeSinceLastResult = Date.now() - lastResultTimestampRef.current;
      const isSilentEnough = timeSinceLastResult > 5000;  // ← AUMENTADO: 5s mínimo de silêncio (era 2s)
      
      if (isWakeWordEnabled && 
          !isListening && 
          !isAISpeakingRef.current && 
          isSilentEnough) {
        console.log(`[WATCHDOG] RESSUSCITADO (silêncio: ${timeSinceLastResult}ms, limite: 5000ms)`);
        try {
          start();
        } catch (e) {
          console.error('[WATCHDOG] Erro ao ressuscitar:', e);
        }
      }
    }, 3000);  // ← AUMENTADO: Verificar a cada 3s (era 2s)
  }, [isWakeWordEnabled, start, isListening]);

  // ===== CLEANUP RIGOROSO: Remover recursos ao desmontar (ESSENCIAL para evitar vazamento de memória) =====
  useEffect(() => {
    return () => {
      console.log('[CLEANUP] Desmontando hook - limpando recursos de Speech Recognition');
      
      // ===== HIGH AVAILABILITY: Limpar monitoramento ✓ NOVO =====
      if (ensureListeningIntervalRef.current) {
        clearInterval(ensureListeningIntervalRef.current);
        ensureListeningIntervalRef.current = null;
        console.log('[CLEANUP] HIGH AVAILABILITY interval limpo');
      }
      
      // ===== WATCHDOG: Limpar ressurreição automática ✓ NOVO =====
      if (microphoneWatchdogRef.current) {
        clearInterval(microphoneWatchdogRef.current);
        microphoneWatchdogRef.current = null;
        console.log('[CLEANUP] WATCHDOG interval limpo');
      }
      
      // Limpar todos os timeouts pendentes
      if (flushTimeoutRef.current) {
        clearTimeout(flushTimeoutRef.current);
        flushTimeoutRef.current = null;
      }
      if (restartTimeoutRef.current) {
        clearTimeout(restartTimeoutRef.current);
        restartTimeoutRef.current = null;
      }
      if (stateRef.current.wakeTimeout) {
        clearTimeout(stateRef.current.wakeTimeout);
        stateRef.current.wakeTimeout = undefined;
      }
      if (stateRef.current.commandTimeout) {
        clearTimeout(stateRef.current.commandTimeout);
        stateRef.current.commandTimeout = undefined;
      }
      
      // ===== FIX CRÍTICO: Parar e limpar recognition com tratamento de erro =====
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
          console.log('[CLEANUP] recognition.stop() executado');
        } catch (e) {
          console.log('[CLEANUP] stop() falhou (já foi abortado ou terminado)');
        }
        
        try {
          // @ts-ignore - abort() não está no tipo TypeScript, mas funciona
          if ((recognitionRef.current as any).abort) {
            (recognitionRef.current as any).abort();
            console.log('[CLEANUP] recognition.abort() executado');
          }
        } catch (e) {
          console.log('[CLEANUP] abort() falhou');
        }
        
        recognitionRef.current = null;
      }
      
      // Resetar flags críticas
      isTransitioningRef.current = false;
      intentionalStopRef.current = false;
      
      console.log('[CLEANUP] ✓ Recursos limpos com sucesso - Hook desmontado');
    };
  }, [stop]);  // ← Incluir stop() nas dependências para ativar cleanup quando stop mudar

  // ===== CONTINUOUS LISTENING: Métodos para controlar se IA está a falar =====
  // Usar quando a IA começa a responder (pausar microfone)
  const setAISpeaking = useCallback((isSpeaking: boolean) => {
    isAISpeakingRef.current = isSpeaking;
    if (isSpeaking) {
      console.log('[CONTINUOUS_LISTENING] IA começou a falar - pausando microfone');
      // Não desativar reconhecimento, apenas não reiniciar quando terminar
    } else {
      console.log('[CONTINUOUS_LISTENING] IA terminou de falar - microfone ativo novamente');
      // Se o reconhecimento foi pausado durante resposta, pode ser reiniciado
      // Automaticamente via continuous listening
      if (listeningModeRef.current === 'passive') {
        setDiagnostic("🎤 Modo passivo: aguardando 'Quinta-Feira'...");
      }
    }
  }, []);

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
    setAISpeaking,  // ← Novo método para controlar pausa durante resposta da IA
    listeningMode: listeningModeRef.current,  // ← Expor modo de escuta (passive/active)
    pauseWatchdog,  // ✓ NOVO: Controlo manual do Watchdog
    resumeWatchdog,  // ✓ NOVO: Controlo manual do Watchdog
  };
}
