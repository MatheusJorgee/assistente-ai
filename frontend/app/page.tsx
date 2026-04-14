'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Music, FileText, Trash2, AlertCircle } from 'lucide-react';

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

const API_BASE = 'http://localhost:8000';

export default function Dashboard() {
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    '[SISTEMA] Motor API carregado com sucesso',
    '[SISTEMA] Quinta-Feira v2.1 inicializado',
    '[SISTEMA] Aguardando conexão...',
  ]);
  const [inputCommand, setInputCommand] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [systemStatus, setSystemStatus] = useState<'online' | 'offline' | 'busy'>('offline');

  const inputRef = useRef<HTMLInputElement>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLogs]);

  useEffect(() => {
    const pollStatus = async () => {
      try {
        const response = await fetch(`${API_BASE}/status`).catch(() => null);
        setSystemStatus(response?.ok ? 'online' : 'offline');
      } catch {
        setSystemStatus('offline');
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const quickActions = [
    { id: 'lofi', label: 'Toca Lo-Fi', icon: Music, command: 'Toca uma música lo-fi' },
    { id: 'notepad', label: 'Abre Notepad', icon: FileText, command: 'Abre o bloco de notas' },
    { id: 'memory', label: 'Limpar Memória', icon: Trash2, command: 'Limpa a memória de curto prazo' },
    { id: 'status', label: 'Ver Status', icon: AlertCircle, command: 'Mostra diagnóstico completo' },
  ];

  const handleSendCommand = async (commandText?: string) => {
    const command = (commandText || inputCommand).trim();
    if (!command) return;

    setIsLoading(true);
    setSystemStatus('busy');
    setInputCommand('');
    setTerminalLogs((prev) => [...prev, `[USUÁRIO] ${command}`]);

    try {
      const response = await fetch(`${API_BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: command }),
      });

      if (response.ok) {
        const data = await response.json();
        setTerminalLogs((prev) => [...prev, `[BRAIN] ${data.response || 'Processando...'}`]);
      } else {
        setTerminalLogs((prev) => [...prev, '[ERRO] Falha ao comunicar com backend']);
      }
    } catch (error) {
      setTerminalLogs((prev) => [...prev, '[ERRO] Falha de conexão com backend']);
    } finally {
      setIsLoading(false);
      setSystemStatus('online');
      inputRef.current?.focus();
    }
  };

  const toggleListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech Recognition não suportado');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => {
      setIsListening(true);
      setTerminalLogs((prev) => [...prev, '[SPEECH] Escutando...']);
    };

    recognition.onresult = (event: any) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          const transcript = event.results[i][0].transcript;
          if (['quinta-feira', 'quinta feira'].some(w => transcript.toLowerCase().includes(w))) {
            const command = transcript.toLowerCase().replace(/quinta-feira|quinta feira/gi, '').trim();
            if (command) handleSendCommand(command);
          }
        }
      }
    };

    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="mb-12 p-4">
        <div className="flex justify-between items-start md:items-center gap-6">
          <div>
            <h1 className="text-4xl md:text-5xl font-black text-emerald-400">
              NÚCLEO QUINTA-FEIRA
            </h1>
            <p className="text-zinc-500 text-sm font-mono">Assistente de IA v2.1</p>
          </div>
          <div className={`px-5 py-3 rounded-md font-mono text-sm ${
            systemStatus === 'online' ? 'bg-emerald-950/20 text-emerald-400' : 'bg-red-950/20 text-red-400'
          }`}>
            {systemStatus === 'online' ? '🟢 ONLINE' : '🔴 OFFLINE'}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 p-4">
        <div className="lg:col-span-1 space-y-6">
          <section>
            <h2 className="text-xs font-mono font-bold text-emerald-400 mb-3">⚡ AÇÕES RÁPIDAS</h2>
            <div className="space-y-2">
              {quickActions.map((action) => (
                <button
                  key={action.id}
                  onClick={() => handleSendCommand(action.command)}
                  disabled={isLoading}
                  className="w-full px-4 py-2 bg-zinc-900/60 hover:bg-emerald-500/10 border border-emerald-500/20 rounded
                    text-emerald-400 text-xs font-mono disabled:opacity-50"
                >
                  {action.label}
                </button>
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-xs font-mono font-bold text-emerald-400">🖉 COMANDO</h2>
            <input
              ref={inputRef}
              type="text"
              value={inputCommand}
              onChange={(e) => setInputCommand(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendCommand()}
              placeholder="Digite um comando"
              className="w-full px-3 py-2 bg-zinc-950/80 text-emerald-400 border border-emerald-500/20 rounded text-sm"
            />
            <button
              onClick={() => handleSendCommand()}
              disabled={!inputCommand.trim() || isLoading}
              className="w-full px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-black text-xs font-bold rounded disabled:opacity-50"
            >
              {isLoading ? 'ENVIANDO...' : 'ENVIAR'}
            </button>
          </section>
        </div>

        <div className="lg:col-span-2">
          <h2 className="text-xs font-mono font-bold text-emerald-400 mb-3">█ TERMINAL</h2>
          <div className="bg-black/90 border border-emerald-500/20 rounded min-h-[400px] p-4 overflow-y-auto text-xs text-emerald-400 font-mono space-y-1">
            {terminalLogs.map((log, i) => (
              <div key={i}>{log}</div>
            ))}
            <div ref={terminalEndRef} />
          </div>
          <button
            onClick={toggleListening}
            className={`w-full mt-4 px-4 py-3 rounded text-xs font-bold ${
              isListening ? 'bg-red-600 text-white' : 'bg-emerald-600 text-black'
            }`}
          >
            {isListening ? '🎤 ESCUTANDO' : '🔇 MIC MUTADO'}
          </button>
        </div>
      </div>
    </div>
  );
}
'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Music, FileText, Trash2, AlertCircle } from 'lucide-react';

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

const API_BASE = 'http://localhost:8000';

export default function Dashboard() {
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    '[SISTEMA] Motor API carregado com sucesso',
    '[SISTEMA] Quinta-Feira v2.1 inicializado',
    '[SISTEMA] Aguardando conexÃ£o...',
  ]);
  const [inputCommand, setInputCommand] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [systemStatus, setSystemStatus] = useState<'online' | 'offline' | 'busy'>('offline');
  
  const inputRef = useRef<HTMLInputElement>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLogs]);

  useEffect(() => {
    const pollStatus = async () => {
      try {
        const response = await fetch(`${API_BASE}/status`).catch(() => null);
        setSystemStatus(response?.ok ? 'online' : 'offline');
      } catch {
        setSystemStatus('offline');
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const quickActions = [
    { id: 'lofi', label: 'Toca Lo-Fi', icon: Music, command: 'Toca uma mÃºsica lo-fi' },
    { id: 'notepad', label: 'Abre Notepad', icon: FileText, command: 'Abre o bloco de notas' },
    { id: 'memory', label: 'Limpar MemÃ³ria', icon: Trash2, command: 'Limpa a memÃ³ria de curto prazo' },
    { id: 'status', label: 'Ver Status', icon: AlertCircle, command: 'Mostra diagnÃ³stico completo' },
  ];

  const handleSendCommand = async (commandText?: string) => {
    const command = (commandText || inputCommand).trim();
    if (!command) return;

    setIsLoading(true);
    setSystemStatus('busy');
    setInputCommand('');
    setTerminalLogs((prev) => [...prev, `[USUÃRIO] ${command}`]);

    try {
      const response = await fetch(`${API_BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: command }),
      });

      if (response.ok) {
        const data = await response.json();
        setTerminalLogs((prev) => [...prev, `[BRAIN] ${data.response || 'Processando...'}`]);
      } else {
        setTerminalLogs((prev) => [...prev, '[ERRO] Falha ao comunicar com backend']);
      }
    } catch (error) {
      setTerminalLogs((prev) => [...prev, '[ERRO] Falha de conexÃ£o com backend']);
    } finally {
      setIsLoading(false);
      setSystemStatus('online');
      inputRef.current?.focus();
    }
  };

  const toggleListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech Recognition nÃ£o suportado');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => {
      setIsListening(true);
      setTerminalLogs((prev) => [...prev, '[SPEECH] Escutando...']);
    };

    recognition.onresult = (event: any) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          const transcript = event.results[i][0].transcript;
          if (['quinta-feira', 'quinta feira'].some(w => transcript.toLowerCase().includes(w))) {
            const command = transcript.toLowerCase().replace(/quinta-feira|quinta feira/gi, '').trim();
            if (command) handleSendCommand(command);
          }
        }
      }
    };

    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="mb-12 p-4">
        <div className="flex justify-between items-start md:items-center gap-6">
          <div>
            <h1 className="text-4xl md:text-5xl font-black text-emerald-400">
              NÃšCLEO QUINTA-FEIRA
            </h1>
            <p className="text-zinc-500 text-sm font-mono">Assistente de IA v2.1</p>
          </div>
          <div className={`px-5 py-3 rounded-md font-mono text-sm ${
            systemStatus === 'online' ? 'bg-emerald-950/20 text-emerald-400' : 'bg-red-950/20 text-red-400'
          }`}>
            {systemStatus === 'online' ? 'ðŸŸ¢ ONLINE' : 'ðŸ”´ OFFLINE'}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 p-4">
        <div className="lg:col-span-1 space-y-6">
          <section>
            <h2 className="text-xs font-mono font-bold text-emerald-400 mb-3">âš¡ AÃ‡Ã•ES RÃPIDAS</h2>
            <div className="space-y-2">
              {quickActions.map((action) => (
                <button
                  key={action.id}
                  onClick={() => handleSendCommand(action.command)}
                  disabled={isLoading}
                  className="w-full px-4 py-2 bg-zinc-900/60 hover:bg-emerald-500/10 border border-emerald-500/20 rounded
                    text-emerald-400 text-xs font-mono disabled:opacity-50"
                >
                  {action.label}
                </button>
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-xs font-mono font-bold text-emerald-400">ðŸ–‰ COMANDO</h2>
            <input
              ref={inputRef}
              type="text"
              value={inputCommand}
              onChange={(e) => setInputCommand(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendCommand()}
              placeholder="Digite um comando"
              className="w-full px-3 py-2 bg-zinc-950/80 text-emerald-400 border border-emerald-500/20 rounded text-sm"
            />
            <button
              onClick={() => handleSendCommand()}
              disabled={!inputCommand.trim() || isLoading}
              className="w-full px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-black text-xs font-bold rounded disabled:opacity-50"
            >
              {isLoading ? 'ENVIANDO...' : 'ENVIAR'}
            </button>
          </section>
        </div>

        <div className="lg:col-span-2">
          <h2 className="text-xs font-mono font-bold text-emerald-400 mb-3">â–ˆ TERMINAL</h2>
          <div className="bg-black/90 border border-emerald-500/20 rounded min-h-[400px] p-4 overflow-y-auto text-xs text-emerald-400 font-mono space-y-1">
            {terminalLogs.map((log, i) => (
              <div key={i}>{log}</div>
            ))}
            <div ref={terminalEndRef} />
          </div>
          <button
            onClick={toggleListening}
            className={`w-full mt-4 px-4 py-3 rounded text-xs font-bold ${
              isListening ? 'bg-red-600 text-white' : 'bg-emerald-600 text-black'
            }`}
          >
            {isListening ? 'ðŸŽ¤ ESCUTANDO' : 'ðŸ”‡ MIC MUTADO'}
          </button>
        </div>
      </div>
    </div>
  );
}
 * Adicione isso no seu main.py do backend para aceitar requisiÃ§Ãµes do frontend:
 * 
 * from fastapi.middleware.cors import CORSMiddleware
 * 
 * app.add_middleware(
 *   CORSMiddleware,
 *   allow_origins=["http://localhost:3000"],
 *   allow_credentials=True,
 *   allow_methods=["*"],
 *   allow_headers=["*"],
 * )
 */

