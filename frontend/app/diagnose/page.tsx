// frontend/app/diagnose/page.tsx
// Página de Diagnóstico do Sistema

"use client";

import { useState, useEffect } from 'react';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';

interface DiagnosticResult {
  name: string;
  status: 'pass' | 'fail' | 'warning' | 'checking';
  message: string;
  help?: string;
}

export default function DiagnosticsPage() {
  const [diagnostics, setDiagnostics] = useState<DiagnosticResult[]>([]);
  const [userAgent, setUserAgent] = useState('');
  const [backendHost, setBackendHost] = useState('localhost');
  const speechRecognition = useSpeechRecognition();

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setUserAgent(window.navigator.userAgent);
      setBackendHost(window.location.hostname || 'localhost');
    }
    runDiagnostics();
  }, []);

  async function runDiagnostics() {
    if (typeof window === 'undefined') return;

    const results: DiagnosticResult[] = [];

    // 1. Navegador
    const isChrome = /Chrome/.test(navigator.userAgent) && /Google Inc/.test(navigator.vendor);
    results.push({
      name: 'Navegador',
      status: isChrome ? 'pass' : 'warning',
      message: isChrome ? 'Google Chrome ✓' : navigator.userAgent.split(' ').slice(-1)[0],
      help: isChrome ? 'Suporte completo' : 'Melhor suporte com Google Chrome'
    });

    // 2. Speech Recognition API
    const hasAPI = speechRecognition.isSupported();
    results.push({
      name: 'Speech Recognition API',
      status: hasAPI ? 'pass' : 'fail',
      message: hasAPI ? 'Disponível ✓' : 'Não suportado',
      help: hasAPI ? '' : 'Use Google Chrome para suporte completo'
    });

    // 3. Microfone
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(t => t.stop());
      results.push({
        name: 'Microfone',
        status: 'pass',
        message: 'Acessível ✓'
      });
    } catch (e) {
      const error = e as { name?: string };
      results.push({
        name: 'Microfone',
        status: 'fail',
        message: `Erro: ${error.name || 'desconhecido'}`,
        help: 'Conceda permissão de microfone no navegador'
      });
    }

    // 4. WebSocket
    results.push({
      name: 'WebSocket',
      status: 'checking',
      message: 'Testando...'
    });

    try {
      const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:8000/ws`;
      const ws = new WebSocket(wsUrl);
      
      const wsPromise = new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(false), 3000);
        
        ws.onopen = () => {
          clearTimeout(timeout);
          ws.close();
          resolve(true);
        };
        
        ws.onerror = () => {
          clearTimeout(timeout);
          resolve(false);
        };
      });

      const wsConnected = await wsPromise;
      setDiagnostics(prev => prev.map((r, i) => 
        i === 3 ? {
          ...r,
          status: wsConnected ? 'pass' : 'fail',
          message: wsConnected ? `Conectado ✓` : 'Backend offline',
          help: wsConnected ? '' : 'Verifique se backend está rodando: python -m uvicorn main:app --reload'
        } : r
      ));
    } catch (error) {
      setDiagnostics(prev => prev.map((r, i) => 
        i === 3 ? {
          ...r,
          status: 'fail',
          message: 'Erro de conexão',
          help: 'Backend não está respondendo'
        } : r
      ));
    }

    // 5. Performance
    const navWithDeviceMemory = navigator as Navigator & { deviceMemory?: number };
    results.push({
      name: 'Performance',
      status: 'pass',
      message: `Device: ${navWithDeviceMemory.deviceMemory || '?'}GB RAM, ${navigator.hardwareConcurrency || '?'} cores`
    });

    setDiagnostics(results);
  }

  return (
    <div className="min-h-screen bg-gray-950 text-cyan-300 p-8 font-mono">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-2 text-cyan-400">🔧 Diagnóstico do Sistema</h1>
        <p className="text-gray-400 mb-8">Verificação de compatibilidade e funcionalidades</p>

        {/* Resultados */}
        <div className="space-y-4 mb-8">
          {diagnostics.map((diag, idx) => (
            <DiagnosticCard key={idx} result={diag} />
          ))}
        </div>

        {/* Speech Recognition Test */}
        <div className="border-2 border-cyan-600 rounded p-4 bg-gray-900/50 mb-8">
          <h2 className="text-xl font-bold mb-4 text-cyan-400">🎤 Teste de Fala</h2>
          
          <div className="space-y-3">
            <button
              onClick={() => speechRecognition.start()}
              disabled={speechRecognition.isListening}
              className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 px-4 py-2 rounded"
            >
              {speechRecognition.isListening ? '⏸️ Escutando...' : '▶️ Iniciar Teste'}
            </button>

            {speechRecognition.diagnostic && (
              <div className="bg-gray-900 border border-cyan-500 p-3 rounded text-sm whitespace-pre-wrap">
                {speechRecognition.diagnostic}
              </div>
            )}

            {speechRecognition.lastTranscription && (
              <div className="bg-green-900 border border-green-500 p-3 rounded">
                <div className="text-sm text-gray-300">Transcrito:</div>
                <div className="font-bold">{speechRecognition.lastTranscription.text}</div>
                <div className="text-xs text-gray-400 mt-1">
                  Confiança: {(speechRecognition.lastTranscription.confidence * 100).toFixed(0)}%
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Informações de Debug */}
        <div className="border-2 border-yellow-600 rounded p-4 bg-gray-900/50">
          <h2 className="text-lg font-bold mb-2 text-yellow-400">📊 Informações de Debug</h2>
          <pre className="text-xs bg-black p-2 rounded overflow-auto max-h-64">
{`User Agent:
${userAgent || 'carregando...'}

Backend: ws://${backendHost}:8000/ws

Console (F12): Abra DevTools para mais detalhes`}
          </pre>
        </div>
      </div>
    </div>
  );
}

function DiagnosticCard({ result }: { result: DiagnosticResult }) {
  const icons = {
    pass: '✓',
    fail: '✗',
    warning: '⚠️',
    checking: '🔄'
  };

  const colors = {
    pass: 'bg-green-900 border-green-600 text-green-300',
    fail: 'bg-red-900 border-red-600 text-red-300',
    warning: 'bg-yellow-900 border-yellow-600 text-yellow-300',
    checking: 'bg-blue-900 border-blue-600 text-blue-300'
  };

  return (
    <div className={`border-2 rounded p-3 ${colors[result.status]}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icons[result.status]}</span>
          <span className="font-bold">{result.name}</span>
        </div>
        <span className="text-sm">{result.message}</span>
      </div>
      {result.help && (
        <div className="mt-2 text-xs opacity-75">
          💡 {result.help}
        </div>
      )}
    </div>
  );
}
