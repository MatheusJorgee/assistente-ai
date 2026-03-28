"use client";

import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Componentes para markdown com tema dark
const markdownComponents = {
  h1: ({ node, ...props }: any) => <h1 className="text-3xl font-bold mt-4 mb-2 text-cyan-400" {...props} />,
  h2: ({ node, ...props }: any) => <h2 className="text-2xl font-bold mt-3 mb-1 text-cyan-300" {...props} />,
  h3: ({ node, ...props }: any) => <h3 className="text-xl font-bold mt-2 mb-1 text-cyan-300" {...props} />,
  p: ({ node, ...props }: any) => <p className="text-gray-100 leading-relaxed my-2" {...props} />,
  ul: ({ node, ...props }: any) => <ul className="list-disc list-inside my-2 space-y-1 text-gray-100" {...props} />,
  ol: ({ node, ...props }: any) => <ol className="list-decimal list-inside my-2 space-y-1 text-gray-100" {...props} />,
  li: ({ node, ...props }: any) => <li className="ml-2 text-gray-100" {...props} />,
  code: ({ node, inline, ...props }: any) => 
    inline ? 
      <code className="bg-slate-800 text-cyan-400 px-2 py-1 rounded text-sm font-mono" {...props} /> :
      <code className="bg-slate-950 text-cyan-300 p-3 rounded my-2 block overflow-x-auto font-mono text-sm border border-cyan-500 border-opacity-30" {...props} />,
  pre: ({ node, ...props }: any) => <pre className="bg-slate-950 p-4 rounded my-2 overflow-x-auto border border-cyan-500 border-opacity-30" {...props} />,
  blockquote: ({ node, ...props }: any) => <blockquote className="border-l-4 border-cyan-500 pl-4 italic my-2 text-gray-300" {...props} />,
  strong: ({ node, ...props }: any) => <strong className="font-bold text-cyan-300" {...props} />,
  em: ({ node, ...props }: any) => <em className="italic text-gray-200" {...props} />,
  a: ({ node, ...props }: any) => <a className="text-cyan-400 hover:text-cyan-300 underline" target="_blank" rel="noopener noreferrer" {...props} />,
  table: ({ node, ...props }: any) => <table className="border-collapse border border-cyan-500 border-opacity-30 my-2" {...props} />,
  th: ({ node, ...props }: any) => <th className="border border-cyan-500 border-opacity-30 bg-slate-800 px-2 py-1 font-bold text-cyan-300" {...props} />,
  td: ({ node, ...props }: any) => <td className="border border-cyan-500 border-opacity-30 px-2 py-1 text-gray-100" {...props} />,
};

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export default function QuintaFeiraUI() {
  const [status, setStatus] = useState("Desconectado");
  const [mensagem, setMensagem] = useState("");
  const [historico, setHistorico] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  
  const ws = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<any>(null);

  // Inicializar Speech Recognition
  useEffect(() => {
    const SpeechRecognition = window.webkitSpeechRecognition || window.SpeechRecognition;
    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.lang = 'pt-BR';
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = false;

      recognitionRef.current.onstart = () => setIsListening(true);
      recognitionRef.current.onend = () => setIsListening(false);
      
      recognitionRef.current.onresult = (event: any) => {
        const transcript = Array.from(event.results)
          .map((result: any) => result[0].transcript)
          .join('');
        
        if (transcript.trim()) {
          setMensagem(transcript.trim());
          // Auto-enviar após reconhecimento
          setTimeout(() => {
            if (wsConnected && transcript.trim()) {
              handleSendMessage({ preventDefault: () => {} } as any, transcript.trim());
            }
          }, 500);
        }
      };
    }
  }, [wsConnected]);

  // Auto-scroll ao fim do chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historico]);

  // Conectar ao WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const backendUrl = `${protocol}//${window.location.hostname}:8000/api/chat/ws`;
        
        ws.current = new WebSocket(backendUrl);

        ws.current.onopen = () => {
          setStatus("🟢 Conectado";
          setWsConnected(true);
          setError(null);
        };

        ws.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            switch (data.type) {
              case 'streaming':
                if (data.content) {
                  setHistorico(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant') {
                      return [...prev.slice(0, -1), {
                        ...lastMsg,
                        content: lastMsg.content + data.content
                      }];
                    }
                    return prev;
                  });
                }
                break;
              
              case 'complete':
                setIsLoading(false);
                break;

              case 'error':
                setError(data.message || "Erro ao processar");
                setIsLoading(false);
                break;
            }
          } catch (e) {
            console.error("Erro ao processar:", e);
          }
        };

        ws.current.onerror = () => {
          setError("Erro de conexão");
          setStatus("🔴 Desconectado");
          setWsConnected(false);
        };

        ws.current.onclose = () => {
          setStatus("🔴 Desconectado");
          setWsConnected(false);
          setTimeout(connectWebSocket, 3000);
        };
      } catch (error) {
        console.error("Erro WebSocket:", error);
        setError("Falha ao conectar");
      }
    };

    connectWebSocket();

    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);

  // Enviar mensagem
  const handleSendMessage = async (e: any, forceMessage?: string) => {
    e?.preventDefault?.();
    
    const textToSend = forceMessage || mensagem;
    
    if (!textToSend.trim()) return;
    if (!wsConnected) {
      setError("Servidor desconectado");
      return;
    }

    setHistorico(prev => [...prev, {
      role: 'user',
      content: textToSend,
      timestamp: new Date()
    }]);

    setHistorico(prev => [...prev, {
      role: 'assistant',
      content: '',
      timestamp: new Date()
    }]);

    setMensagem("");
    setIsLoading(true);
    setError(null);

    try {
      ws.current?.send(JSON.stringify({
        message: textToSend,
        user_id: "user_" + Date.now(),
        timestamp: new Date().toISOString()
      }));
    } catch (error) {
      console.error("Erro ao enviar:", error);
      setError("Erro ao enviar mensagem");
      setIsLoading(false);
    }
  };

  const toggleMicrophone = () => {
    if (recognitionRef.current) {
      if (isListening) {
        recognitionRef.current.stop();
      } else {
        recognitionRef.current.start();
      }
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-gray-100 font-sans">
      {/* Header */}
      <header className="bg-slate-800 border-b border-cyan-500 border-opacity-30 px-6 py-4 shadow-lg">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-cyan-400">🎯 Quinta-Feira</h1>
            <p className="text-sm text-gray-400">Assistente de IA com Consciência de Contexto</p>
          </div>
          <div className="flex items-center space-x-3">
            <div className={`w-3 h-3 rounded-full ${wsConnected ? 'bg-cyan-400' : 'bg-red-500'} animate-pulse`}></div>
            <span className="text-sm font-medium">{status}</span>
          </div>
        </div>
      </header>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-4xl mx-auto space-y-4">
          {historico.length === 0 ? (
            <div className="text-center py-20">
              <div className="text-6xl mb-4">🎤</div>
              <h2 className="text-3xl font-bold text-cyan-400 mb-4">Bem-vindo ao Quinta-Feira</h2>
              <p className="text-gray-400 max-w-md mx-auto text-lg">
                Fale seus comandos: tocar música, enviar mensagens, controlar vídeos, controlar mídia em aplicativos específicos...
              </p>
              <p className="text-gray-500 mt-4 text-sm">Use o botão microfone ou digite abaixo</p>
            </div>
          ) : (
            historico.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-2xl px-5 py-4 rounded-lg ${
                    msg.role === 'user'
                      ? 'bg-cyan-600 rounded-br-none shadow-md'
                      : 'bg-slate-800 rounded-bl-none border-l-4 border-cyan-500'
                  }`}
                >
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={markdownComponents}
                    >
                      {msg.content || '...'}
                    </ReactMarkdown>
                  ) : (
                    <p className="text-white">{msg.content}</p>
                  )}
                  <span className="text-xs text-gray-400 mt-2 block">
                    {msg.timestamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
            ))
          )}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-slate-800 px-5 py-4 rounded-lg rounded-bl-none border-l-4 border-cyan-500">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                </div>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-6 mb-4 max-w-4xl mx-auto">
          <div className="bg-red-900 bg-opacity-50 border-l-4 border-red-500 px-4 py-3 text-red-200">
            ⚠️ {error}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="bg-slate-800 border-t border-cyan-500 border-opacity-30 px-6 py-4">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={handleSendMessage} className="flex gap-3 items-center">
            <input
              ref={inputRef}
              type="text"
              value={mensagem}
              onChange={(e) => setMensagem(e.target.value)}
              placeholder="Digite seu comando ou use o microfone..."
              className="flex-1 px-4 py-3 bg-slate-700 text-white border border-cyan-500 border-opacity-50 rounded focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500 focus:ring-opacity-30 disabled:opacity-50"
              disabled={!wsConnected || isLoading}
            />
            
            {/* Botão de Microfone - VERMELHO PULSANTE */}
            <button
              type="button"
              onClick={toggleMicrophone}
              disabled={!wsConnected || isLoading}
              className={`px-5 py-3 rounded font-bold transition-all ${
                isListening
                  ? 'bg-red-600 text-white animate-pulse shadow-lg shadow-red-600'
                  : 'bg-red-500 hover:bg-red-600 text-white disabled:bg-gray-600'
              }`}
              title="Ativar/desativar microfone"
            >
              🎤
            </button>

            {/* Botão de Envio */}
            <button
              type="submit"
              disabled={!wsConnected || isLoading || !mensagem.trim()}
              className="px-6 py-3 bg-cyan-600 hover:bg-cyan-500 text-white rounded font-bold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? '⏳' : '➤'}
            </button>
          </form>
          
          <div className="mt-2 text-xs text-gray-500 text-center">
            {!wsConnected ? '🔌 Conectando...' : '✅ Pronto'}
          </div>
        </div>
      </div>

      <style jsx>{`
        ::-webkit-scrollbar {
          width: 8px;
        }
        ::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.5);
        }
        ::-webkit-scrollbar-thumb {
          background: rgba(34, 211, 238, 0.5);
          border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
          background: rgba(34, 211, 238, 0.8);
        }
      `}</style>
    </div>
  );
}
