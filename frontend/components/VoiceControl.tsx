// frontend/components/VoiceControl.tsx
// Controle de voz modular com V1 Silent ACK Duplo restaurado

"use client";

import { useState, useSyncExternalStore, useCallback, useRef, useEffect } from 'react';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';

interface VoiceControlProps {
  onCommand: (command: string) => void;
  isDisabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
  onBargein?: () => void;  // ← Callback para interrupção
  onBrowserWarning?: (msg: string) => void;
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

export function VoiceControl({ 
  onCommand, 
  isDisabled = false, 
  size = 'md',
  onBargein,
  onBrowserWarning,
}: VoiceControlProps) {
  const [adjustedCommand, setAdjustedCommand] = useState("");
  const [browserWarning, setBrowserWarning] = useState<string | null>(null);
  const pendingSilentAckRef = useRef(false);  // ← V1 RESTORED

  const isClient = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );

  const speechRecognition = useSpeechRecognition({
    language: 'pt-BR',
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
