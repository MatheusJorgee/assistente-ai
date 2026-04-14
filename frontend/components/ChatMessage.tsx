/**
 * ChatMessage: Componente - Renderizar Mensagem Individual
 * ========================================================
 */

'use client';

import { Message } from '@/types';

interface Props {
  message: Message;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-xs px-4 py-2 rounded-lg ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-none'
            : 'bg-gray-700 text-gray-100 rounded-bl-none'
        }`}
      >
        <p className="text-sm">{message.content}</p>
        <p className="text-xs mt-1 opacity-70">
          {new Date(message.timestamp).toLocaleTimeString('pt-BR')}
        </p>
      </div>
    </div>
  );
}
