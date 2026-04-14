/**
 * AudioPlayer: Hook + Componente - Reprodutor de Áudio Base64
 * ===========================================================
 * 
 * Funcionalidade:
 * - Decodificar Base64 → Blob
 * - Criar URL do Blob
 * - Reproduzir automaticamente no <audio>
 * - Tratar erros de autoplay
 */

'use client';

import { useEffect, useRef } from 'react';

interface Props {
  audioBase64?: string;
  autoplay?: boolean;
  onPlayStart?: () => void;
  onPlayEnd?: () => void;
}

export function AudioPlayer({
  audioBase64,
  autoplay = true,
  onPlayStart,
  onPlayEnd,
}: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!audioBase64 || !audioRef.current) return;

    try {
      // Decodificar Base64 → Binary String
      const binaryString = atob(audioBase64);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);

      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Binary → Blob
      const blob = new Blob([bytes], { type: 'audio/wav' });
      const url = URL.createObjectURL(blob);

      // Atribuir ao <audio>
      audioRef.current.src = url;

      // Autoplay
      if (autoplay) {
        audioRef.current.play().catch(err => {
          console.warn('[AUDIO] Autoplay bloqueado pelo navegador:', err);
          // Navegador pode bloquear autoplay sem interação do usuário
        });
      }

      // Cleanup
      return () => {
        URL.revokeObjectURL(url);
      };
    } catch (err) {
      console.error('[AUDIO] Erro ao decodificar Base64:', err);
    }
  }, [audioBase64, autoplay]);

  return (
    <>
      <audio
        ref={audioRef}
        onPlay={onPlayStart}
        onEnded={onPlayEnd}
        controls={false}
        style={{ display: 'none' }}
      />
    </>
  );
}
