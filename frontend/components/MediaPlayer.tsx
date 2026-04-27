/**
 * MediaPlayer — Intercepta eventos `media_playback_requested` e toca
 * o conteúdo diretamente no navegador do usuário.
 *
 * Estratégia:
 *  - YouTube → <iframe> com `autoplay=1`
 *  - Áudio Base64 → <AudioPlayer>
 *
 * Componente visual mínimo: painel flutuante inferior, fechável.
 */

'use client';

import { useMemo } from 'react';
import { AudioPlayer } from './AudioPlayer';

export interface ActiveMedia {
  provider?: 'youtube' | 'audio' | string;
  video_id?: string;
  video_url?: string;
  search_query?: string;
  audio_base64?: string;
  autoplay?: boolean;
  title?: string;
}

interface Props {
  media: ActiveMedia | null;
  onClose: () => void;
}

function extractYoutubeId(src?: string): string | null {
  if (!src) return null;
  const m = src.match(
    /(?:youtube\.com\/(?:watch\?v=|embed\/|v\/)|youtu\.be\/)([A-Za-z0-9_-]{6,})/
  );
  return m ? m[1] : null;
}

export function MediaPlayer({ media, onClose }: Props) {
  const youtubeId = useMemo(() => {
    if (!media) return null;
    if (media.video_id) return media.video_id;
    const fromUrl = extractYoutubeId(media.video_url);
    if (fromUrl) return fromUrl;
    return null;
  }, [media]);

  if (!media) return null;

  const isYoutube =
    media.provider === 'youtube' ||
    !!youtubeId ||
    !!media.video_url ||
    !!media.search_query;

  const embedSrc = youtubeId
    ? `https://www.youtube.com/embed/${youtubeId}?autoplay=${
        media.autoplay === false ? 0 : 1
      }&rel=0`
    : media.search_query
    ? `https://www.youtube.com/embed?listType=search&list=${encodeURIComponent(
        media.search_query
      )}&autoplay=${media.autoplay === false ? 0 : 1}`
    : null;

  return (
    <div className='fixed bottom-4 right-4 z-50 w-80 max-w-[92vw] rounded-xl border border-zinc-700 bg-zinc-900/95 backdrop-blur shadow-2xl shadow-black/50 overflow-hidden'>
      <div className='flex items-center justify-between px-3 py-2 border-b border-zinc-800'>
        <div className='flex items-center gap-2 min-w-0'>
          <span className='text-emerald-400 text-xs font-mono'>▶</span>
          <span className='text-xs text-zinc-200 font-medium truncate'>
            {media.title || media.search_query || 'Reproduzindo mídia'}
          </span>
        </div>
        <button
          onClick={onClose}
          className='text-zinc-400 hover:text-zinc-100 transition-colors text-sm px-2'
          title='Fechar player'
        >
          ✕
        </button>
      </div>

      {isYoutube && embedSrc ? (
        <div className='relative w-full aspect-video bg-black'>
          <iframe
            key={embedSrc}
            src={embedSrc}
            title='YouTube player'
            allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share'
            allowFullScreen
            className='absolute inset-0 w-full h-full'
          />
        </div>
      ) : null}

      {media.audio_base64 ? (
        <div className='p-3'>
          <AudioPlayer audioBase64={media.audio_base64} autoplay={media.autoplay !== false} />
          <div className='text-[10px] font-mono text-zinc-400'>reproduzindo áudio…</div>
        </div>
      ) : null}

      {!isYoutube && !media.audio_base64 ? (
        <div className='p-4 text-xs text-zinc-300 font-mono'>
          [aviso] formato de mídia não suportado
        </div>
      ) : null}
    </div>
  );
}
