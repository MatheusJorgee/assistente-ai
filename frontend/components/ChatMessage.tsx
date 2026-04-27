/**
 * ChatMessage — Bolha individual de mensagem (apresentação pura).
 * ----------------------------------------------------------------
 * UI burra: recebe um `ChatMessage` do tipo compartilhado e renderiza.
 */

'use client';

import type { ChatMessage as ChatMessageModel } from '@/types';

interface Props {
  message: ChatMessageModel;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user';
  const time = new Date(message.timestamp).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[78%] md:max-w-[65%] px-4 py-2.5 rounded-2xl shadow-sm',
          'text-sm leading-relaxed whitespace-pre-wrap break-words',
          isUser
            ? 'bg-emerald-600 text-white rounded-br-sm'
            : 'bg-zinc-800 text-zinc-100 border border-zinc-700 rounded-bl-sm',
        ].join(' ')}
      >
        <div className='flex items-center gap-2 mb-1'>
          <span
            className={[
              'text-[10px] font-mono uppercase tracking-wider',
              isUser ? 'text-emerald-100/80' : 'text-emerald-400/80',
            ].join(' ')}
          >
            {isUser ? 'Você' : 'Quinta-Feira'}
          </span>
          <span className='text-[10px] text-zinc-400/70'>{time}</span>
        </div>

        <p className='text-[14px]'>{message.content}</p>

        {message.tools_used && message.tools_used.length > 0 && (
          <div className='mt-2 flex flex-wrap gap-1'>
            {message.tools_used.map((t) => (
              <span
                key={t}
                className='text-[9px] font-mono px-1.5 py-0.5 rounded bg-black/25 text-emerald-300/80'
              >
                ⚙ {t}
              </span>
            ))}
          </div>
        )}

        {typeof message.execution_time_ms === 'number' && (
          <div className='mt-1 text-[10px] font-mono text-zinc-400/70'>
            {message.execution_time_ms.toFixed(0)} ms
          </div>
        )}
      </div>
    </div>
  );
}
