// frontend/components/VoiceControl.tsx
// Controle de voz modular com V1 Silent ACK Duplo restaurado

"use client";

import { useState, useSyncExternalStore, useCallback, useRef, useEffect } from 'react';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';

interface VoiceControlProps {
  onCommand: (command: string) => void;
  isDisabled?: boolean;
  isWakeWordEnabled?: boolean;  // ← Novo: Controlar escuta contínua
  onWakeWordEnabledChange?: (enabled: boolean) => void;  // ← Novo: Callback para mudar estado
  size?: 'sm' | 'md' | 'lg';
  onBargein?: () => void;  // ← Callback para interrupção
  onBrowserWarning?: (msg: string) => void;
  onAISpeakingStateChange?: (isSpeaking: boolean) => void;  // ← Novo: Controlar quando IA está a falar
}

const normalizarTexto = (texto: string) => {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9\s-]/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase()
    .trim();
};

// ===== V1 SILENT ACK: Dois tons diferentes =====
// Sucesso: 660Hz (frequência harmônica, aguda)
// Erro: 800Hz (ligeiramente mais grave)
const playToneSilentAck = (frequency: number, duration: number, type: 'success' | 'error') => {
  try {
    const w = window as typeof window & {
      webkitAudioContext?: typeof AudioContext;
    };

    const AudioContextCtor = w.AudioContext || w.webkitAudioContext;
    if (!AudioContextCtor) return;

    const audioCtx = new AudioContextCtor();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    
    oscillator.frequency.value = frequency;
    oscillator.type = 'sine';
    
    // Volume discreto (silencioso)
    gainNode.gain.setValueAtTime(0.05, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + duration / 1000);
    
    oscillator.start(audioCtx.currentTime);
    oscillator.stop(audioCtx.currentTime + duration / 1000);
    
    console.log(`[SILENT_ACK] ${type === 'success' ? '✓ 660Hz' : '✗ 800Hz'}`);
  } catch (e) {
    console.log('Silent ACK not available', e);
  }
};

// ===== V1 DICIONÁRIO: Comandos que NÃO precisam de resposta de IA =====
const deveResponderSemFala = (texto: string): boolean => {
  const t = normalizarTexto(texto);
  const regex = /pausa|resume|play\b|pause\b|volume\s*\d+|skip|proxima|proximo|anterior|prev|mudo|silencio|mute|unmute|next|previous/i;
  return regex.test(t);
};

// ===== NOVO: Som de Ativação Wake Word (Radar) =====
const playWakeWordActivationSound = () => {
  try {
    const w = window as typeof window & {
      webkitAudioContext?: typeof AudioContext;
    };

    const AudioContextCtor = w.AudioContext || w.webkitAudioContext;
    if (!AudioContextCtor) return;

    const audioCtx = new AudioContextCtor();
    
    // Tom duplo para ativação: 440Hz (A4) + 880Hz (A5) - notas musicais
    const now = audioCtx.currentTime;
    const duration = 0.3;
    
    // Primeiro tom (440Hz - Lá)
    const osc1 = audioCtx.createOscillator();
    const gain1 = audioCtx.createGain();
    osc1.connect(gain1);
    gain1.connect(audioCtx.destination);
    osc1.frequency.value = 440;
    osc1.type = 'sine';
    gain1.gain.setValueAtTime(0.15, now);
    gain1.gain.exponentialRampToValueAtTime(0.01, now + duration);
    osc1.start(now);
    osc1.stop(now + duration);
    
    // Segundo tom (880Hz - Lá agudo, 1 oitava acima)
    const osc2 = audioCtx.createOscillator();
    const gain2 = audioCtx.createGain();
    osc2.connect(gain2);
    gain2.connect(audioCtx.destination);
    osc2.frequency.value = 880;
    osc2.type = 'sine';
    gain2.gain.setValueAtTime(0.15, now + duration * 0.3);
    gain2.gain.exponentialRampToValueAtTime(0.01, now + duration * 0.8);
    osc2.start(now + duration * 0.3);
    osc2.stop(now + duration * 0.8);
    
    console.log('[WAKE_WORD_SOUND] 📡 Radar ativado: 440Hz + 880Hz');
  } catch (e) {
    console.log('Wake word activation sound not available', e);
  }
};

export function VoiceControl({ 
  onCommand, 
  isDisabled = false, 
  isWakeWordEnabled = false,  // ← Novo
  onWakeWordEnabledChange,  // ← Novo
  size = 'md',
  onBargein,
  onBrowserWarning,
  onAISpeakingStateChange,
}: VoiceControlProps) {
  const [adjustedCommand, setAdjustedCommand] = useState("");
  const [browserWarning, setBrowserWarning] = useState<string | null>(null);
  const pendingSilentAckRef = useRef(false);  // ← V1 RESTORED
  
  // ===== CONTINUOUS LISTENING: Expor setAISpeaking para o componente pai =====
  const aISpeakingRef = useRef(false);

  const isClient = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );

  const speechRecognition = useSpeechRecognition({
    language: 'pt-BR',
    isWakeWordEnabled: isWakeWordEnabled,  // ← Novo: Passar o estado
    onTranscription: (text: string) => {
      const command = adjustBilingualCommand(text);
      setAdjustedCommand(command);
      
      // ===== V1 SILENT ACK LOGIC =====
      if (deveResponderSemFala(command)) {
        pendingSilentAckRef.current = true;
        playToneSilentAck(660, 80, 'success');  // Sucesso: 660Hz
        console.log('[SILENT_ACK_TRIGGERED] Comando simples detectado:', command);
      }
      
      onCommand(command);
    },
    onError: (error: string) => {
      console.error('Speech error:', error);
      // Tocar som de erro
      playToneSilentAck(800, 120, 'error');  // Erro: 800Hz
    },
    onWakewordDetected: () => {
      // ===== NOVO: Tocar som de ativação (Radar) =====
      playWakeWordActivationSound();
      
      // ===== V1 BARGE-IN: Chamar callback ====
      console.log('[BARGE_IN] Wake word detectado - interrompendo IA');
      if (onBargein) onBargein();
    },
    onBrowserWarning: (msg: string) => {
      setBrowserWarning(msg);
      if (onBrowserWarning) onBrowserWarning(msg);
    },
    flushTimeout: 1400,
  });

  const sizeClasses = {
    sm: "h-8 w-8 text-xs",
    md: "h-12 w-12 text-lg",
    lg: "h-16 w-16 text-2xl",
  };

  const speechSupported = isClient ? speechRecognition.isSupported() : false;

  const handleToggleListen = () => {
    if (speechRecognition.isListening) {
      speechRecognition.stop();
    } else {
      speechRecognition.start();
    }
  };

  // ===== CONTINUOUS LISTENING: Notificar quando IA começa/termina resposta =====
  useEffect(() => {
    // isDisabled torna-se true quando isLoading=true (IA a processar)
    if (isDisabled && !aISpeakingRef.current) {
      aISpeakingRef.current = true;
      console.log('[VOICE_CONTROL] IA começou a falar - pausando microfone contínuo');
      speechRecognition.setAISpeaking(true);
      onAISpeakingStateChange?.(true);
    } else if (!isDisabled && aISpeakingRef.current) {
      aISpeakingRef.current = false;
      console.log('[VOICE_CONTROL] IA terminou de falar - retomando microfone contínuo');
      speechRecognition.setAISpeaking(false);
      onAISpeakingStateChange?.(false);
    }
  }, [isDisabled, speechRecognition, onAISpeakingStateChange]);

  // ===== FORCE RESTART: Quando isWakeWordEnabled muda, reiniciar microfone para aplicar nova config =====
  useEffect(() => {
    if (speechRecognition.isListening) {
      console.log(`[WAKE_WORD_SYNC] Modo alterado para: ${isWakeWordEnabled ? '🟢 CONTINUO' : '🔵 MANUAL'}`);
      console.log('[WAKE_WORD_SYNC] Reiniciando microfone para aplicar nova configuração...');
      
      // Force restart: stop() + start() imediato
      try {
        speechRecognition.stop();
        // Aguardar 100ms para garantir que stop() foi processado
        setTimeout(() => {
          try {
            speechRecognition.start();
            console.log(`[WAKE_WORD_SYNC] Microfone reiniciado com continuous=${isWakeWordEnabled}`);
          } catch (e) {
            console.error('[WAKE_WORD_SYNC] Erro ao reiniciar:', e);
          }
        }, 100);
      } catch (e) {
        console.error('[WAKE_WORD_SYNC] Erro ao parar:', e);
      }
    }
  }, [isWakeWordEnabled, speechRecognition]);

  // Função para ajustar comandos bilingues
  const adjustBilingualCommand = (text: string) => {
    let adjusted = text
      .replace(/\b(volume\s*up|increase volume)\b/gi, "aumentar volume")
      .replace(/\b(volume\s*down|decrease volume)\b/gi, "diminuir volume")
      .replace(/\b(next track|skip)\b/gi, "proxima musica")
      .replace(/\b(play|resume)\b/gi, "retomar")
      .replace(/\b(pause|stop)\b/gi, "pausar")
      .replace(/\b(the perfect pear|the perfect pair)\b/gi, "the perfect pair")  // V1 Bilingual fix
      .replace(/\bperfeit paira\b/gi, "the perfect pair");  // V1 Phonetic fix
    
    return adjusted.trim();
  };

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Botão Principal de Voz */}
      <button
        onClick={handleToggleListen}
        disabled={isDisabled || !speechSupported}
        className={`
          ${sizeClasses[size]}
          rounded-full transition-all duration-200
          flex items-center justify-center
          ${speechRecognition.isListening
            ? 'bg-red-600 hover:bg-red-700 animate-pulse shadow-lg shadow-red-500'
            : 'bg-cyan-600 hover:bg-cyan-700 shadow-lg shadow-cyan-500'
          }
          disabled:opacity-50 disabled:cursor-not-allowed
          border-2 border-cyan-400 font-bold text-white
        `}
        title={speechSupported ? "Clique para ativar microfone (ou fale 'Quinta-Feira')" : "Navegador não suporta voz"}
      >
        {speechRecognition.isListening ? '🎤' : '🔇'}
      </button>

      {/* Warning de Browser - V1 Restored */}
      {browserWarning && (
        <div className="w-full max-w-md bg-orange-900 border-2 border-orange-500 text-orange-200 px-4 py-2 rounded text-xs font-mono">
          {browserWarning}
        </div>
      )}

      {/* Estado da Máquina - Feedback em tempo real */}
      {speechRecognition.diagnostic && (
        <div className="w-full max-w-md bg-gray-900 border border-cyan-500 rounded p-3 text-xs font-mono text-cyan-300">
          {speechRecognition.diagnostic}
        </div>
      )}

      {/* Último Comando */}
      {adjustedCommand && (
        <div className="w-full max-w-md bg-green-900 border border-green-500 rounded p-2 text-xs font-mono text-green-300">
          ✓ Enviado: <span className="font-bold">{adjustedCommand}</span>
        </div>
      )}
    </div>
  );
}

// Função auxiliar: Play beep sound (mantida para fallback)
function playBeep(duration: number, frequency: number) {
  try {
    const w = window as typeof window & {
      webkitAudioContext?: typeof AudioContext;
    };

    const AudioContextCtor = w.AudioContext || w.webkitAudioContext;
    if (!AudioContextCtor) return;

    const audioCtx = new AudioContextCtor();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    
    oscillator.frequency.value = frequency;
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + duration / 1000);
    
    oscillator.start(audioCtx.currentTime);
    oscillator.stop(audioCtx.currentTime + duration / 1000);
  } catch {
    console.log('Beep not available');
  }
}
