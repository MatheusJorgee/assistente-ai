// frontend/components/StatusIndicator.tsx
// Indicador de status visual

"use client";

interface StatusIndicatorProps {
  wsConnected: boolean;
  isListening: boolean;
  isLoading: boolean;
  status?: string;
}

const statusMessages: Record<string, { color: string; icon: string; label: string }> = {
  connecting: { icon: '🔄', color: 'yellow', label: 'Conectando...' },
  connected: { icon: '🟢', color: 'green', label: 'Conectado' },
  disconnected: { icon: '🔴', color: 'red', label: 'Desconectado' },
  listening: { icon: '🎤', color: 'blue', label: 'Escutando' },
  processing: { icon: '⚙️', color: 'cyan', label: 'Processando' },
  error: { icon: '❌', color: 'red', label: 'Erro' },
};

export function StatusIndicator({ 
  wsConnected, 
  isListening, 
  isLoading,
  status = 'idle'
}: StatusIndicatorProps) {
  
  let displayStatus = 'connected';
  
  if (!wsConnected) displayStatus = 'disconnected';
  else if (isLoading) displayStatus = 'processing';
  else if (isListening) displayStatus = 'listening';
  else displayStatus = 'connected';

  const statusInfo = statusMessages[displayStatus] || statusMessages['connected'];

  return (
    <div className={`
      flex items-center gap-2 px-3 py-1 rounded-full text-sm font-mono
      border border-${statusInfo.color}-500
      bg-${statusInfo.color}-900/30
      text-${statusInfo.color}-300
    `}>
      <span className="text-lg">{statusInfo.icon}</span>
      <span>{statusInfo.label}</span>
    </div>
  );
}
