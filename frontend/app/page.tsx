"use client";

import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Componentes para melhor renderização de markdown
const markdownComponents = {
  h1: ({ node, ...props }: any) => <h1 className="text-3xl font-bold mt-4 mb-2" {...props} />,
  h2: ({ node, ...props }: any) => <h2 className="text-2xl font-bold mt-3 mb-1" {...props} />,
  h3: ({ node, ...props }: any) => <h3 className="text-xl font-bold mt-2 mb-1" {...props} />,
  p: ({ node, ...props }: any) => <p className="text-base leading-relaxed my-2" {...props} />,
  ul: ({ node, ...props }: any) => <ul className="list-disc list-inside my-2 space-y-1" {...props} />,
  ol: ({ node, ...props }: any) => <ol className="list-decimal list-inside my-2 space-y-1" {...props} />,
  li: ({ node, ...props }: any) => <li className="ml-2" {...props} />,
  code: ({ node, inline, ...props }: any) => 
    inline ? 
      <code className="bg-gray-200 px-2 py-1 rounded text-sm font-mono" {...props} /> :
      <code className="bg-gray-900 text-gray-100 p-3 rounded my-2 block overflow-x-auto font-mono text-sm" {...props} />,
  pre: ({ node, ...props }: any) => <pre className="bg-gray-900 p-4 rounded my-2 overflow-x-auto" {...props} />,
  blockquote: ({ node, ...props }: any) => <blockquote className="border-l-4 border-blue-500 pl-4 italic my-2" {...props} />,
  strong: ({ node, ...props }: any) => <strong className="font-bold" {...props} />,
  em: ({ node, ...props }: any) => <em className="italic" {...props} />,
  a: ({ node, ...props }: any) => <a className="text-blue-500 hover:underline" target="_blank" rel="noopener noreferrer" {...props} />,
  table: ({ node, ...props }: any) => <table className="border-collapse border border-gray-300 my-2" {...props} />,
  th: ({ node, ...props }: any) => <th className="border border-gray-300 bg-gray-100 px-2 py-1 font-bold" {...props} />,
  td: ({ node, ...props }: any) => <td className="border border-gray-300 px-2 py-1" {...props} />,
};

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export default function QuintaFeiraV2Interface() {
  const [status, setStatus] = useState("Conectando...");
  const [mensagem, setMensagem] = useState("");
  const [historico, setHistorico] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  
  const ws = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Auto-scroll ao fim do chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historico]);

  // Conectar ao WebSocket do backend
  useEffect(() => {
    const connectWebSocket = () => {
      try {
        // Tentar conectar ao backend local (será expandido para 0.0.0.0 na Fase 3)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const backendUrl = `${protocol}//${window.location.hostname}:8000/api/chat/ws`;
        
        ws.current = new WebSocket(backendUrl);

        ws.current.onopen = () => {
          setStatus("✅ Conectado ao Assistente");
          setWsConnected(true);
          setError(null);
        };

        ws.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            // Diferentes tipos de mensagens do backend
            switch (data.type) {
              case 'streaming':
                // Streaming de resposta (por caracteres)
                if (data.content) {
                  setHistorico(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant') {
                      // Atualizar última mensagem do assistente
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
                // Resposta completa
                setIsLoading(false);
                setMensagem("");
                break;

              case 'error':
                setError(data.message || "Erro ao processar mensagem");
                setIsLoading(false);
                break;

              case 'status':
                setStatus(data.message);
                break;
            }
          } catch (e) {
            console.error("Erro ao processar mensagem:", e);
          }
        };

        ws.current.onerror = (error) => {
          console.error("Erro WebSocket:", error);
          setError("Erro de conexão com servidor");
          setStatus("❌ Desconectado");
          setWsConnected(false);
        };

        ws.current.onclose = () => {
          setStatus("❌ Desconectado");
          setWsConnected(false);
          // Tentar reconectar após 3 segundos
          setTimeout(connectWebSocket, 3000);
        };
      } catch (error) {
        console.error("Erro ao conectar WebSocket:", error);
        setError("Falha ao conectar ao servidor");
      }
    };

    connectWebSocket();

    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  // Enviar mensagem
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!mensagem.trim()) return;
    if (!wsConnected) {
      setError("Conexão com servidor não disponível");
      return;
    }

    // Adicionar mensagem do usuário ao histórico
    const userMessage: Message = {
      role: 'user',
      content: mensagem,
      timestamp: new Date()
    };
    setHistorico(prev => [...prev, userMessage]);

    // Preparar mensagem do assistente
    const assistantMessage: Message = {
      role: 'assistant',
      content: '',
      timestamp: new Date()
    };
    setHistorico(prev => [...prev, assistantMessage]);

    setMensagem("");
    setIsLoading(true);
    setError(null);

    // Enviar pelo WebSocket
    try {
      ws.current?.send(JSON.stringify({
        message: mensagem,
        user_id: "user_" + Date.now(), // ID único por sessão
        timestamp: new Date().toISOString()
      }));
    } catch (error) {
      console.error("Erro ao enviar mensagem:", error);
      setError("Erro ao enviar mensagem");
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">🎯 Quinta-Feira v2.1+</h1>
            <p className="text-sm text-gray-600">Assistente de IA Autônomo</p>
          </div>
          <div className="flex items-center space-x-2">
            <div className="w-3 h-3 rounded-full bg-green-500"></div>
            <span className="text-sm font-medium text-gray-700">{status}</span>
          </div>
        </div>
      </header>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-4xl mx-auto space-y-4">
          {historico.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-4xl mb-4">💬</div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Bem-vindo ao Quinta-Feira</h2>
              <p className="text-gray-600 max-w-md mx-auto">
                Você pode me pedir para tocar música, enviar mensagens, controlar vídeos e muito mais! 
                Tente digitar um comando abaixo.
              </p>
            </div>
          ) : (
            historico.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-2xl px-4 py-3 rounded-lg ${
                    msg.role === 'user'
                      ? 'bg-blue-500 text-white rounded-br-none'
                      : 'bg-gray-200 text-gray-900 rounded-bl-none'
                  }`}
                >
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={markdownComponents}
                      className="prose prose-sm max-w-none"
                    >
                      {msg.content || "..."}
                    </ReactMarkdown>
                  ) : (
                    <p className="text-sm leading-relaxed">{msg.content}</p>
                  )}
                  <span className="text-xs opacity-70 mt-1 block">
                    {msg.timestamp.toLocaleTimeString('pt-BR')}
                  </span>
                </div>
              </div>
            ))
          )}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-gray-200 px-4 py-3 rounded-lg rounded-bl-none">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce animation-delay-200"></div>
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce animation-delay-400"></div>
                </div>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mx-4 mb-4 max-w-4xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm">
            ⚠️ {error}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 px-4 py-4">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={handleSendMessage} className="flex gap-3">
            <input
              ref={inputRef}
              type="text"
              value={mensagem}
              onChange={(e) => setMensagem(e.target.value)}
              placeholder="Escreva seu comando aqui... (ex: 'toca Bohemian Rhapsody' ou 'mande mensagem pro whatsapp')"
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              disabled={!wsConnected || isLoading}
            />
            <button
              type="submit"
              disabled={!wsConnected || isLoading || !mensagem.trim()}
              className="px-6 py-3 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? "Enviando..." : "Enviar"}
            </button>
          </form>
          
          <div className="mt-2 text-xs text-gray-500 flex items-center justify-between">
            <span>
              {!wsConnected ? "⚠️ Aguardando conexão..." : "✅ Conectado"}
            </span>
            <span>{historico.length} mensagens na sessão</span>
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes bounce {
          0%, 80%, 100% { opacity: 0.5; }
          40% { opacity: 1; }
        }
        .animation-delay-200 {
          animation-delay: 200ms;
        }
        .animation-delay-400 {
          animation-delay: 400ms;
        }
      `}</style>
    </div>
  );
}
