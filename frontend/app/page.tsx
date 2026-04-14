'use client';

/**
 * CONFIGURAÇÃO CORS (Python/FastAPI)
 * Adicione isso no seu main.py do backend para aceitar requisições do frontend:
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

import { useState, useRef, useEffect } from 'react';

// Type augmentation para Web Speech API
declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

const API_BASE = 'http://localhost:8000'; // Ajuste conforme necessário

export default function Dashboard() {
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    '[SISTEMA] Motor API carregado com sucesso',
    '[SISTEMA] Quinta-Feira v2.1 inicializado',
    '[SISTEMA] Brain orquestrador ativo',
    '[SISTEMA] Tool Registry carregado (8 ferramentas)',
    '[AGUARDANDO] Pronto para receber comandos...',
  ]);

  const [inputCommand, setInputCommand] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [systemStatus, setSystemStatus] = useState<'online' | 'busy'>('online');
  const [isTyping, setIsTyping] = useState(false);
  const [isListening, setIsListening] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const isListeningRef = useRef(isListening);

  // Sincroniza ref com estado para usar em callbacks
  useEffect(() => {
    isListeningRef.current = isListening;
  }, [isListening]);

  // Focusa no input quando isTyping ativa
  useEffect(() => {
    if (isTyping) {
      inputRef.current?.focus();
    }
  }, [isTyping]);

  // Auto-scroll no terminal quando novos logs aparecem
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLogs]);

  // Polling de logs a cada 2 segundos (lê o que o backend está fazendo)
  useEffect(() => {
    const pollLogs = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/logs`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        });

        if (response.ok) {
          const data = await response.json();
          if (data.logs && Array.isArray(data.logs)) {
            // Atualiza terminal com novos logs do backend
            setTerminalLogs((prev) => {
              const newLogs = data.logs.filter(
                (log: string) => !prev.includes(log)
              );
              return [...prev, ...newLogs];
            });
          }
        }
      } catch (error) {
        // Silenciosamente falha - não queremos poluir o terminal com erros de polling
        console.debug('Polling de logs falhou (esperado se endpoint não existir):', error);
      }
    };

    const interval = setInterval(pollLogs, 2000);
    return () => clearInterval(interval);
  }, []);

  // Envio de comando para o backend
  const handleSendCommand = async (commandText?: string) => {
    const command = (commandText || inputCommand).trim();
    if (!command) return;

    // Se veio de commandText (speech), não limpa inputCommand
    if (!commandText) {
      setInputCommand('');
    }
    
    setIsLoading(true);
    setSystemStatus('busy');

    // Adiciona comando do usuário ao terminal
    setTerminalLogs((prev) => [...prev, `[USUÁRIO] ${command}`]);

    try {
      // Fetch POST para o endpoint do backend
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      });

      if (response.ok) {
        const data = await response.json();
        const resultado = data.response || 'Comando processado.';
        setTerminalLogs((prev) => [
          ...prev,
          `[QUINTA-FEIRA] ${resultado}`,
        ]);
      } else {
        const errorData = await response.json().catch(() => ({}));
        setTerminalLogs((prev) => [
          ...prev,
          `[ERRO] API respondeu com status ${response.status}: ${
            errorData.message || 'Erro desconhecido'
          }`,
        ]);
      }
    } catch (error) {
      // Erro de rede ou conexão
      setTerminalLogs((prev) => [
        ...prev,
        '[ERRO] Falha de conexão com o Núcleo',
      ]);
      console.error('Erro ao enviar comando:', error);
    } finally {
      setIsLoading(false);
      setSystemStatus('online');
    }
  };

  // Extrai comando após a wake word "quinta feira" ou "quinta-feira"
  const extractCommandAfterWakeWord = (transcript: string): string | null => {
    const lowerTranscript = transcript.toLowerCase().trim();
    
    // Padrões da wake word
    const wakeWordPatterns = [
      /quinta\s+feira/i,
      /quinta\s*-\s*feira/i,
    ];

    for (const pattern of wakeWordPatterns) {
      const match = lowerTranscript.match(pattern);
      if (match) {
        // Extrai tudo após a wake word
        const index = lowerTranscript.indexOf(match[0]);
        const endIndex = index + match[0].length;
        const commandPart = transcript.slice(endIndex).trim();
        
        // Se há comando após, retorna; senão retorna null
        return commandPart ? commandPart : null;
      }
    }
    
    return null;
  };

  // Web Speech API - Wake Word Detection
  useEffect(() => {
    if (!isListening) {
      // Para o reconhecimento se isListening for false
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      return;
    }

    // Browser support check
    const SpeechRecognition = window.SpeechRecognition || (window as any).webkitSpeechRecognition;
    
    if (!SpeechRecognition) {
      setTerminalLogs((prev) => [
        ...prev,
        '[ERRO] Web Speech API não suportada neste navegador',
      ]);
      setIsListening(false);
      return;
    }

    try {
      recognitionRef.current = new SpeechRecognition();
      const recognition = recognitionRef.current;

      // Configuração
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'pt-BR';

      // Evento: resultado de transcrição
      recognition.onresult = (event: any) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;

          if (event.results[i].isFinal) {
            finalTranscript = transcript;
          } else {
            interimTranscript += transcript;
          }
        }

        // Se há transcrição final, processa
        if (finalTranscript) {
          console.log('[SPEECH] Transcrição:', finalTranscript);

          // Procura pela wake word
          const command = extractCommandAfterWakeWord(finalTranscript);

          if (command) {
            // Wake word detectada! Envia comando
            console.log('[SPEECH] Wake word detectada! Comando:', command);
            setTerminalLogs((prev) => [
              ...prev,
              '[WAKE-WORD] "quinta-feira" detectada - processando comando',
            ]);
            
            // Envia comando extraído
            handleSendCommand(command);
          } else if (finalTranscript.toLowerCase().includes('quinta')) {
            // Capturou "quinta" mas precisa de "feira" após? Avisa
            setTerminalLogs((prev) => [
              ...prev,
              '[SPEECH] Ouvi "quinta" mas não a wake word completa',
            ]);
          }
        }

        // Log interim (visual feedback do usuário)
        if (interimTranscript) {
          console.log('[SPEECH-INTERIM]:', interimTranscript);
        }
      };

      // Evento: fim do reconhecimento (silêncio)
      recognition.onend = () => {
        console.log('[SPEECH] Reconhecimento terminado');

        // Se isListening ainda for true, reinicia
        if (isListeningRef.current) {
          console.log('[SPEECH] Reiniciando reconhecimento...');
          try {
            recognition.start();
          } catch (e) {
            console.warn('[SPEECH] Erro ao reiniciar:', e);
          }
        }
      };

      // Evento: erro
      recognition.onerror = (event: any) => {
        console.error('[SPEECH-ERROR]:', event.error);
        setTerminalLogs((prev) => [
          ...prev,
          `[SPEECH-ERROR] ${event.error}`,
        ]);
      };

      // Inicia o reconhecimento
      recognition.start();
      setTerminalLogs((prev) => [
        ...prev,
        '[SPEECH] Escuta ativada - esperando "quinta-feira"...',
      ]);

    } catch (error) {
      console.error('[SPEECH] Erro ao inicializar:', error);
      setTerminalLogs((prev) => [
        ...prev,
        '[ERRO] Falha ao inicializar Web Speech API',
      ]);
      setIsListening(false);
    }

    // Cleanup
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {
          // Ignorar erros ao desligar
        }
      }
    };
  }, [isListening]);

  const handleContainerClick = () => {
    if (!isLoading && !isTyping) {
      setIsTyping(true);
    }
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSendCommand(); // Sem argumentos = usa inputCommand do estado
      setIsTyping(false);
    } else if (e.key === 'Escape') {
      setIsTyping(false);
    }
  };

  const toggleListening = (e: React.MouseEvent) => {
    e.stopPropagation(); // Previne que o clique propague para handleContainerClick
    setIsListening(!isListening);
  };

  return (
    <div
      className="fixed inset-0 bg-black cursor-default overflow-hidden"
      onClick={handleContainerClick}
    >
      {/* Entidade Central - Blob Orgânico Pulsante */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative w-80 h-80">
          {/* Blob 1 - Verde Esmeralda */}
          <div
            className={`absolute inset-0 rounded-full blur-3xl transition-all duration-500 ${
              isListening
                ? 'bg-emerald-600/50 animate-pulse'
                : 'bg-emerald-600/30'
            }`}
            style={{
              animation: 'spin 15s linear infinite',
            }}
          />

          {/* Blob 2 - Cyan Escuro */}
          <div
            className={`absolute inset-0 rounded-full blur-3xl transition-all duration-500 ${
              isListening ? 'bg-cyan-900/60' : 'bg-cyan-900/40'
            }`}
            style={{
              animation: 'spin 20s linear infinite reverse',
            }}
          />

          {/* Blob 3 - Verde Mais Profundo */}
          <div
            className={`absolute inset-0 rounded-full blur-3xl transition-all duration-500 ${
              isListening ? 'bg-emerald-700/40' : 'bg-emerald-700/20'
            }`}
            style={{
              animation: 'spin 25s linear infinite',
            }}
          />

          {/* Input Overlay - Aparece quando isTyping */}
          {isTyping && (
            <input
              ref={inputRef}
              type="text"
              value={inputCommand}
              onChange={(e) => setInputCommand(e.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder=">_"
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
                w-96 text-center text-2xl font-mono text-white placeholder-zinc-600
                bg-transparent focus:outline-none focus:ring-0"
            />
          )}
        </div>
      </div>

      {/* Logs Sombrios - Canto Inferior Esquerdo */}
      <div className="fixed bottom-4 left-4 max-w-sm">
        <div
          className="space-y-0 font-mono text-[10px] text-emerald-900/50 overflow-y-auto"
          style={{ maxHeight: '150px' }}
        >
          {terminalLogs.map((log, index) => (
            <div key={index} className="truncate text-emerald-900/50">
              {log}
            </div>
          ))}
          <div ref={terminalEndRef} />
        </div>
      </div>

      {/* Status Indicator - Canto Superior Direito */}
      <div className="fixed top-4 right-4 flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            systemStatus === 'online'
              ? 'bg-emerald-400 animate-pulse'
              : 'bg-yellow-400 animate-pulse'
          }`}
        />
        <span className="text-xs font-mono text-zinc-700">
          {systemStatus === 'online' ? 'ONLINE' : 'BUSY'}
        </span>
      </div>

      {/* Hint de Clique (Desaparece quando isTyping) */}
      {!isTyping && (
        <div className="fixed top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 text-center mt-96">
          <p className="text-xs font-mono text-zinc-800 animate-pulse">
            [ clique para invocar ]
          </p>
        </div>
      )}

      {/* Botão Furtivo de Microfone - Inferior Central */}
      <button
        onClick={toggleListening}
        className={`fixed bottom-8 left-1/2 -translate-x-1/2 font-mono text-xs cursor-pointer
          transition-colors duration-300 focus:outline-none
          ${
            isListening
              ? 'text-emerald-500 hover:text-emerald-400'
              : 'text-zinc-600 hover:text-red-900/80'
          }`}
      >
        {isListening ? '[ 🎤 ESCUTANDO: QUINTA-FEIRA ]' : '[ 🔇 MIC: MUTADO ]'}
      </button>

      {/* Global Keyframes para Animações */}
      <style>{`
        @keyframes spin {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </div>
  );
}