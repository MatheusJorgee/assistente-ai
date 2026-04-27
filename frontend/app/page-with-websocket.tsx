/**
 * EXEMPLO: Usar QuintaTerminal em page.tsx
 * ========================================
 *
 * Este arquivo mostra como integrar o componente WebSocket
 * na página principal do Next.js
 */

'use client';

import { useState } from 'react';
import { QuintaTerminal } from '@/components/QuintaTerminal';

export default function Page() {
  const [isConnected, setIsConnected] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  return (
    <div className="h-screen w-full bg-slate-950 p-4 flex flex-col">
      {/* ===== HEADER COM STATUS =====*/}
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-100">Quinta-Feira v1.0</h1>

        <div className="flex items-center gap-4">
          {/* Status Indicator */}
          <div className={`text-sm font-semibold px-3 py-1 rounded ${
            isConnected
              ? 'bg-green-100 text-green-800'
              : 'bg-yellow-100 text-yellow-800'
          }`}>
            {isConnected ? '● Backend Online' : '◐ Backend Conectando...'}
          </div>

          {/* Error Display */}
          {lastError && (
            <div className="text-sm bg-red-900 text-red-100 px-3 py-1 rounded max-w-xs truncate">
              ⚠ {lastError}
            </div>
          )}
        </div>
      </div>

      {/* ===== MAIN COMPONENT ===== */}
      <div className="flex-1 flex items-center justify-center">
        <QuintaTerminal
          wsUrl="ws://localhost:8000/ws/quinta"
          onConnectionChange={(connected) => {
            setIsConnected(connected);
            console.log(`[PAGE] Connection changed: ${connected}`);
          }}
          onError={(error) => {
            setLastError(error);
            console.error(`[PAGE] Error: ${error}`);
            
            // Auto-clear error after 5 seconds
            setTimeout(() => setLastError(null), 5000);
          }}
        />
      </div>

      {/* ===== FOOTER COM SHORTCUTS ===== */}
      <div className="mt-4 text-xs text-slate-500 text-center space-y-1">
        <p>💡 Atalhos: <kbd className="bg-slate-800 px-1 rounded">Ctrl</kbd> + <kbd className="bg-slate-800 px-1 rounded">Enter</kbd> para enviar</p>
        <p>📡 Backend em: ws://localhost:8000/ws/quinta</p>
      </div>
    </div>
  );
}
