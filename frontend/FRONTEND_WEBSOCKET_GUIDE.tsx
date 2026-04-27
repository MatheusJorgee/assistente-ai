/**
 * FRONTEND WEBSOCKET INTEGRATION - Guia Completo
 * ===============================================
 *
 * Estrutura implementada:
 * 1. Types (frontend/types/quinta.ts) - MessageEnvelope, DTOs type-safe
 * 2. Hook (frontend/hooks/useQuintaFeira.ts) - Gerenciador de WebSocket
 * 3. Component (frontend/components/QuintaTerminal.tsx) - Interface visual
 *
 * Filosofia:
 * - Type-safe (TypeScript strict)
 * - Sem bloqueios (async/await everywhere)
 * - Cleanup adequado (evita memory leaks)
 * - Reconexão automática (exponential backoff)
 * - Pragmático (TailwindCSS, sem dependências pesadas)
 */

// ===== 1. TYPES (frontend/types/index.ts) =====

/**
 * MessageEnvelope é o padrão base para TODAS mensagens
 *
 * Exemplo de entrada (Frontend → Backend):
 * {
 *   "type": "user_message",
 *   "payload": {
 *     "text": "Qual é seu nome?",
 *     "mode": "streaming"
 *   },
 *   "timestamp": "2026-04-17T10:30:45.123456Z",
 *   "request_id": "1713348645123_abc123def456"
 * }
 *
 * Exemplo de saída (Backend → Frontend):
 * {
 *   "type": "brain_response",
 *   "payload": {
 *     "text": "Meu nome é Quinta-Feira",
 *     "tools_used": ["gemini_adapter"],
 *     "execution_time_ms": 450.5,
 *     "confidence": 0.95
 *   },
 *   "timestamp": "2026-04-17T10:30:46.654321Z",
 *   "request_id": "1713348645123_abc123def456"
 * }
 */

// ===== 2. HOOK (frontend/hooks/useQuintaFeira.ts) =====

/**
 * Custom hook que gerencia o ciclo de vida do WebSocket
 *
 * Responsabilidades:
 * - Conectar/desconectar
 * - Reconexão com exponential backoff
 * - Gerenciar histórico de mensagens
 * - Gerenciar status intermediário
 * - Enfileirar mensagens se desconectado
 * - Cleanup adequado no unmount
 *
 * Exponential Backoff (padrão):
 * - Base: 1000ms
 * - Max: 30000ms
 * - Formula: min(1000 * (2 ^ attempt), 30000)
 *
 * Exemplo de tentativas:
 * 1ª: 1000ms
 * 2ª: 2000ms
 * 3ª: 4000ms
 * 4ª: 8000ms
 * 5ª: 16000ms
 * 6ª+: 30000ms (máximo)
 */

// ===== 3. COMPONENT (frontend/components/QuintaTerminal.tsx) =====

/**
 * Componente visual que:
 * - Renderiza histórico de mensagens
 * - Mostra status intermediário (thinking, processing, etc)
 * - Input de texto com Ctrl+Enter para enviar
 * - Indicadores de conexão
 * - Seletor de modo (streaming/deliberativo/interativo)
 * - TailwindCSS para styling
 *
 * Props:
 * - wsUrl?: string - URL WebSocket (padrão: ws://localhost:8000/ws/quinta)
 * - onConnectionChange?: (connected: boolean) => void
 * - onError?: (error: string) => void
 */

// ===== EXEMPLO DE USO =====

import React from 'react';
import { QuintaTerminal } from '@/components/QuintaTerminal';

export default function Page() {
  return (
    <div className="h-screen w-full bg-slate-950 p-4 flex items-center justify-center">
      <QuintaTerminal
        wsUrl="ws://localhost:8000/ws/quinta"
        onConnectionChange={(connected) => {
          console.log(`[APP] Conexão: ${connected ? 'ativa' : 'inativa'}`);
        }}
        onError={(error) => {
          console.error(`[APP] Erro: ${error}`);
        }}
      />
    </div>
  );
}

// ===== CUSTOMIZAÇÃO AVANÇADA (SEM COMPONENTE) =====

/**
 * Se você quer usar o hook diretamente sem o componente:
 */

import { useQuintaFeira } from '@/hooks/useQuintaFeira';

function MyCustomComponent() {
  const {
    isConnected,
    connectionStatus,
    messages,
    intermediateStatus,
    error,
    isLoading,
    sendMessage,
    ping,
    disconnect,
  } = useQuintaFeira({
    wsUrl: 'ws://localhost:8000/ws/quinta',
    autoReconnect: true,
    maxReconnectAttempts: 5,
    baseReconnectDelay: 1000,
    maxReconnectDelay: 30000,
  });

  // Seu próprio UI...
  return (
    <div>
      <h1>Conectado: {isConnected ? 'Sim' : 'Não'}</h1>
      <p>Status: {connectionStatus}</p>
      <p>Mensagens: {messages.length}</p>

      {intermediateStatus && (
        <div>
          <p>Processando: {intermediateStatus.step}</p>
          <div
            style={{
              width: `${(intermediateStatus.progress || 0) * 100}%`,
              height: '4px',
              backgroundColor: 'blue',
            }}
          />
        </div>
      )}

      {error && <p style={{ color: 'red' }}>{error}</p>}

      <button onClick={() => sendMessage('Olá!')}>Enviar</button>
      <button onClick={() => ping()}>Ping (Keep-Alive)</button>
      <button onClick={disconnect}>Desconectar</button>
    </div>
  );
}

// ===== FLUXO COMPLETO =====

/**
 * 1. Usuario digita: "Qual é seu nome?"
 * 2. Click "Enviar" (ou Ctrl+Enter)
 *
 * 3. Hook envia MessageEnvelope:
 *    {
 *      "type": "user_message",
 *      "payload": { "text": "Qual é seu nome?", "mode": "streaming" },
 *      "timestamp": "...",
 *      "request_id": "..."
 *    }
 *
 * 4. Backend recebe em /ws/quinta
 * 5. Backend chama Brain.ask()
 *
 * 6. Backend emite status intermediário:
 *    {
 *      "type": "intermediate_status",
 *      "payload": { "step": "thinking", "progress": 0.0 },
 *      "timestamp": "...",
 *      "request_id": "..." (MESMO de antes)
 *    }
 *
 * 7. Hook recebe e atualiza intermediateStatus (UI exibe "Pensando...")
 * 8. UI renderiza progress bar
 *
 * 9. Backend emite resposta final:
 *    {
 *      "type": "brain_response",
 *      "payload": {
 *        "text": "Meu nome é Quinta-Feira",
 *        "tools_used": ["gemini_adapter"],
 *        "execution_time_ms": 450.5
 *      },
 *      "timestamp": "...",
 *      "request_id": "..." (MESMO)
 *    }
 *
 * 10. Hook recebe, adiciona ao messages[], limpa intermediateStatus
 * 11. Component renderiza: "Meu nome é Quinta-Feira" com metadata
 */

// ===== DEBUGGING =====

/**
 * Para ver logs da comunicação:
 * Abra DevTools → Console
 *
 * Você verá:
 * [WS] Conectando em: ws://localhost:8000/ws/quinta
 * [WS] ✓ Conectado ao backend
 * [WS] Mensagem enviada: Qual é seu nome?
 * [WS] Status: thinking (0%)
 * [WS] Status: processing (50%)
 * [WS] Resposta recebida: Meu nome é Quinta-Feira
 *
 * Problemas comuns:
 *
 * 1. "WebSocket is closed" → Backend offline
 *    Solução: Verificar se backend está rodando (uvicorn main:app --reload)
 *
 * 2. "CORS error" → Frontend em origem diferente
 *    Solução: Verificar CORS em backend main.py
 *
 * 3. Múltiplas conexões → Modo dev React StrictMode
 *    Solução: Normal, useQuintaFeira lida com isso (cleanup correto)
 *
 * 4. Mensagem não envia → WebSocket não está conectado
 *    Solução: Aguardar isConnected === true antes de enviar
 */

// ===== TESTES MANUAIS =====

/**
 * 1. Backend rodando?
 *    curl http://localhost:8000/health
 *
 * 2. Frontend rodando?
 *    npm run dev (em frontend/)
 *
 * 3. Abrir http://localhost:3000
 *
 * 4. Verificar console:
 *    [WS] ✓ Conectado ao backend
 *
 * 5. Digitar na interface:
 *    "Qual é seu nome?"
 *
 * 6. Você deve ver:
 *    - "Pensando..." (status intermediário)
 *    - Resposta do Brain
 *    - Metadata (tempo execução, ferramentas usadas)
 *
 * 7. Desconectar backend (Ctrl+C em uvicorn)
 *    - UI muda para "Desconectado"
 *    - Começa reconexão automática
 *    - Mensagens enfileiradas
 *
 * 8. Reconectar backend (uvicorn main:app --reload)
 *    - UI muda para "Conectando..."
 *    - Conecta e envia mensagens enfileiradas
 */

// ===== PRÓXIMAS FASES =====

/**
 * Phase 6: Audio Streaming
 * - Estender DTOs com audio_chunk
 * - Adicionar recorder de áudio
 * - Transmitir chunks em tempo real
 *
 * Phase 7: Multi-user
 * - JWT authentication
 * - User-scoped broadcasts
 * - Persistência de sessão
 *
 * Phase 8: Advanced UI
 * - Dark mode toggle
 * - Copy/edit messages
 * - Regenerate responses
 * - Clear history
 *
 * Phase 9: Analytics
 * - Rastrear uso (com consentimento)
 * - Performance metrics
 * - Error tracking
 */

export default function IntegrationGuide() {
  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-4">Frontend WebSocket Integration Guide</h1>

      <section className="mb-8">
        <h2 className="text-2xl font-bold mb-4">Estrutura</h2>
        <pre className="bg-gray-800 text-gray-100 p-4 rounded overflow-x-auto">
          {`frontend/
├── types/
│   └── index.ts          # MessageEnvelope, DTOs
├── hooks/
│   └── useQuintaFeira.ts # Custom hook + exponential backoff
├── components/
│   └── QuintaTerminal.tsx # UI component
└── app/
    └── page.tsx          # Usar <QuintaTerminal />
`}
        </pre>
      </section>

      <section className="mb-8">
        <h2 className="text-2xl font-bold mb-4">Importar & Usar</h2>
        <pre className="bg-gray-800 text-gray-100 p-4 rounded overflow-x-auto">
          {`import { QuintaTerminal } from '@/components/QuintaTerminal';

export default function Page() {
  return (
    <div className="h-screen">
      <QuintaTerminal wsUrl="ws://localhost:8000/ws/quinta" />
    </div>
  );
}
`}
        </pre>
      </section>

      <section className="mb-8">
        <h2 className="text-2xl font-bold mb-4">Features Implementadas</h2>
        <ul className="list-disc list-inside space-y-2">
          <li>✅ Type-safe (TypeScript strict)</li>
          <li>✅ Reconexão automática com exponential backoff</li>
          <li>✅ Status intermediário durante processamento</li>
          <li>✅ Histórico de mensagens</li>
          <li>✅ Enfileiramento de mensagens (desconectado)</li>
          <li>✅ Cleanup adequado (sem memory leaks)</li>
          <li>✅ TailwindCSS responsive</li>
          <li>✅ Keyboard shortcuts (Ctrl+Enter)</li>
          <li>✅ Indicadores visuais (conexão, erro, loading)</li>
        </ul>
      </section>
    </div>
  );
}
