'use client';
import { useState, useEffect, useRef } from 'react';

export default function Page() {
  const [isTyping, setIsTyping] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [wakeWordDetected, setWakeWordDetected] = useState(false);
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    '> quinta_feira.exe inicializado',
    '> processador neural ativo',
    '> awaiting consciousness...',
  ]);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const isListeningRef = useRef<boolean>(false);

  // Focar no input quando isTyping ativar
  useEffect(() => {
    if (isTyping && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isTyping]);

  // Setup e gerenciamento do Web Speech API
  useEffect(() => {
    isListeningRef.current = isListening;

    if (!isListening) {
      // Para o reconhecimento se isListening for false
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      return;
    }

    // Verificar suporte
    if (typeof window === 'undefined') return;

    const SpeechRecognition = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SpeechRecognition) {
      setTerminalLogs((prev) => [...prev, '< [ERRO] Web Speech API não suportada']);
      setIsListening(false);
      return;
    }

    // Criar ou reusar instância
    if (!recognitionRef.current) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'pt-BR';

      recognitionRef.current.onstart = () => {
        setTerminalLogs((prev) => [...prev, '> [MIC] Escutando..']);
      };

      recognitionRef.current.onresult = (event: any) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript.toLowerCase();

          if (event.results[i].isFinal) {
            finalTranscript += transcript;
          } else {
            interimTranscript += transcript;
          }
        }

        // Combinar transcrições
        const fullTranscript = finalTranscript || interimTranscript;

        // Detectar wake word "quinta feira" ou "quinta-feira"
        const wakeWordPattern = /quinta\s*feira/i;
        const wakeWordIndex = fullTranscript.search(wakeWordPattern);

        if (wakeWordIndex !== -1 && event.results[event.results.length - 1].isFinal) {
          // Wake word detectado!
          setWakeWordDetected(true);
          setTerminalLogs((prev) => [...prev, '> [WAKE] quinta_feira detectado']);

          // Extrair comando após wake word
          const matchLength = fullTranscript.match(wakeWordPattern)?.[0].length || 0;
          const command = fullTranscript.substring(wakeWordIndex + matchLength).trim();

          if (command) {
            // Enviar comando diretamente
            setTerminalLogs((prev) => [...prev, `> ${command}`]);
            handleSendCommand(command);
            setWakeWordDetected(false);
          }
        }
      };

      recognitionRef.current.onerror = (event: any) => {
        setTerminalLogs((prev) => [...prev, `< [ERRO] ${event.error}`]);
      };

      recognitionRef.current.onend = () => {
        // Reiniciar automaticamente se isListening ainda for true
        if (isListeningRef.current) {
          try {
            recognitionRef.current?.start();
          } catch (e) {
            // Já está rodando
          }
        }
      };
    }

    // Iniciar reconhecimento
    try {
      recognitionRef.current.start();
    } catch (e) {
      // Já está rodando ou erro
      if ((e as any).name !== 'InvalidStateError') {
        setTerminalLogs((prev) => [...prev, `< [ERRO] ${String(e).substring(0, 40)}`]);
      }
    }

    return () => {
      // Cleanup: parar reconhecimento ao desmontar
      if (recognitionRef.current && !isListening) {
        recognitionRef.current.stop();
      }
    };
  }, [isListening]);

  // Clique em qualquer parte da tela ativa typing (mas apenas se não estiver escutando)
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      // Não ativar typing se for clique no botão de mic ou se já estiver digitando
      const target = e.target as HTMLElement;
      if (!isTyping && !isListening && !target.closest('[data-mic-button]')) {
        setIsTyping(true);
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener('click', handleClick);
      return () => container.removeEventListener('click', handleClick);
    }
  }, [isTyping, isListening]);

  const handleSendCommand = async (commandParam?: string) => {
    const command = commandParam || inputValue;

    if (!command.trim()) {
      setIsTyping(false);
      setInputValue('');
      return;
    }

    // Adicionar comando ao log
    setTerminalLogs((prev) => [...prev, `> ${command}`]);
    setInputValue('');

    // Enviar para backend
    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      });

      const data = await response.json();
      setTerminalLogs((prev) => [...prev, `< ${data.response || 'resposta vazia'}`]);
      setTerminalLogs((prev) => [...prev, '> ']);
    } catch (error) {
      setTerminalLogs((prev) => [...prev, `< [ERRO] ${String(error).substring(0, 60)}`]);
    }

    setIsTyping(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSendCommand(inputValue);
    } else if (e.key === 'Escape') {
      setIsTyping(false);
      setInputValue('');
    }
  };

  return (
    <div
      ref={containerRef}
      className='w-screen h-screen bg-black overflow-hidden flex items-center justify-center cursor-default relative select-none'
    >
      {/* Entidade Viva - Blob Orgânico Pulsante */}
      <div className='absolute inset-0 flex items-center justify-center pointer-events-none'>
        {/* Container principal da entidade */}
        <div className='relative w-96 h-96'>
          {/* Blob 1 - Emerald base (spin rápido) */}
          <div
            className='absolute inset-0 bg-emerald-600/35 rounded-full blur-3xl'
            style={{
              animation: 'blob-spin-fast 8s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite',
              mixBlendMode: 'screen',
            }}
          />

          {/* Blob 2 - Cyan overlay (spin reverso) */}
          <div
            className='absolute inset-0 bg-cyan-500/30 rounded-full blur-3xl'
            style={{
              animation: 'blob-spin-reverse 12s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite',
              mixBlendMode: 'lighten',
            }}
          />

          {/* Blob 3 - Verde escuro núcleo (pulse) */}
          <div
            className='absolute inset-0 bg-emerald-900/30 rounded-full blur-3xl'
            style={{
              animation: 'blob-pulse-core 5s ease-in-out infinite',
            }}
          />

          {/* Blob 4 - Azul profundo (spin lento) */}
          <div
            className='absolute inset-0 bg-blue-900/25 rounded-full blur-3xl'
            style={{
              animation: 'blob-spin-slow 14s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite',
              mixBlendMode: 'multiply',
            }}
          />

          {/* Blob 5 - Verde-azul interior (pulse inverso) */}
          <div
            className='absolute inset-0 bg-teal-600/20 rounded-full blur-3xl'
            style={{
              animation: 'blob-pulse-reverse 4s ease-in-out infinite',
            }}
          />
        </div>
      </div>

      {/* Input de Digitação (Overlay dinâmico) */}
      {isTyping && (
        <div className='absolute inset-0 flex items-center justify-center z-50 pointer-events-auto'>
          <div className='flex items-center gap-2'>
            <span className='text-emerald-700/60 text-3xl font-mono font-bold'>►</span>
            <input
              ref={inputRef}
              type='text'
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='_'
              className='bg-transparent border-none outline-none text-2xl font-mono text-white placeholder-emerald-900/50 w-96 tracking-wider caret-emerald-500'
            />
          </div>
        </div>
      )}

      {/* Terminal Logs - Canto Inferior Esquerdo (Pensamentos da Entidade) */}
      <div className='absolute bottom-6 left-6 text-[9px] font-mono text-emerald-900/45 max-w-xs max-h-40 overflow-y-auto pointer-events-none space-y-0.5'>
        {terminalLogs.slice(-12).map((log, idx) => (
          <div
            key={idx}
            className='whitespace-nowrap'
            style={{
              textShadow: '0 0 2px rgba(16, 185, 129, 0.1)',
              opacity: 0.4 + (idx / terminalLogs.length) * 0.6,
            }}
          >
            {log}
          </div>
        ))}
      </div>

      {/* Botão Flutuante de Microfone - Canto Inferior Direito */}
      <button
        data-mic-button
        onClick={(e) => {
          e.stopPropagation();
          setIsListening(!isListening);
        }}
        className={`absolute bottom-8 right-8 w-16 h-16 rounded-full font-mono font-bold text-xl transition-all duration-300 z-40 pointer-events-auto ${
          isListening
            ? 'bg-red-600/70 hover:bg-red-700/70 ring-2 ring-red-400/50 shadow-lg shadow-red-500/20 animate-pulse'
            : 'bg-emerald-700/40 hover:bg-emerald-600/50 ring-1 ring-emerald-500/30'
        }`}
        title={isListening ? 'Parar de ouvir' : 'Começar a ouvir'}
      >
        {isListening ? '🛑' : '🎤'}
      </button>

      {/* Indicator de Wake Word Detectado */}
      {wakeWordDetected && (
        <div className='absolute top-8 right-8 px-4 py-2 bg-emerald-600/40 border border-emerald-500/50 rounded-lg text-emerald-300 text-sm font-mono animate-pulse z-30'>
          ✓ Quinta-Feira Detectada
        </div>
      )}

      {/* Animations customizadas */}
      <style>{`
        @keyframes blob-spin-fast {
          0% {
            transform: rotate(0deg) scaleX(1) scaleY(1);
          }
          25% {
            transform: rotate(90deg) scaleX(1.15) scaleY(0.85);
          }
          50% {
            transform: rotate(180deg) scaleX(0.9) scaleY(1.1);
          }
          75% {
            transform: rotate(270deg) scaleX(1.05) scaleY(0.95);
          }
          100% {
            transform: rotate(360deg) scaleX(1) scaleY(1);
          }
        }

        @keyframes blob-spin-reverse {
          0% {
            transform: rotate(0deg) scaleX(0.85) scaleY(1.15);
          }
          33% {
            transform: rotate(-120deg) scaleX(1.1) scaleY(0.9);
          }
          66% {
            transform: rotate(-240deg) scaleX(0.95) scaleY(1.05);
          }
          100% {
            transform: rotate(-360deg) scaleX(0.85) scaleY(1.15);
          }
        }

        @keyframes blob-spin-slow {
          0% {
            transform: rotate(0deg) scale(0.95);
          }
          50% {
            transform: rotate(180deg) scale(1.05);
          }
          100% {
            transform: rotate(360deg) scale(0.95);
          }
        }

        @keyframes blob-pulse-core {
          0%, 100% {
            transform: scale(1) translateY(0px);
            opacity: 0.5;
          }
          50% {
            transform: scale(1.1) translateY(-8px);
            opacity: 0.8;
          }
        }

        @keyframes blob-pulse-reverse {
          0%, 100% {
            transform: scale(1.05);
            opacity: 0.4;
          }
          50% {
            transform: scale(0.95);
            opacity: 0.6;
          }
        }

        /* Suave scroll nos logs */
        div::-webkit-scrollbar {
          width: 2px;
        }

        div::-webkit-scrollbar-track {
          background: rgba(16, 185, 129, 0.05);
        }

        div::-webkit-scrollbar-thumb {
          background: rgba(16, 185, 129, 0.2);
          border-radius: 1px;
        }
      `}</style>
    </div>
  );
}
