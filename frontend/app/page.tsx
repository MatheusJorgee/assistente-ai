"use client";

import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { VoiceControl } from '@/components/VoiceControl';

// --- markdown visual em estilo limpo e técnico ---
const markdownComponents: Components = {
  h1: ({ ...props }) => <h1 className="mt-3 mb-2 text-xl font-bold tracking-tight text-cyan-200" {...props} />,
  h2: ({ ...props }) => <h2 className="mt-2 mb-1 text-lg font-semibold text-cyan-100" {...props} />,
  h3: ({ ...props }) => <h3 className="mt-2 mb-1 text-base font-semibold text-white" {...props} />,
  p: ({ ...props }) => <p className="my-1.5 leading-relaxed text-slate-100" {...props} />,
  ul: ({ ...props }) => <ul className="my-1.5 list-disc space-y-1 pl-4" {...props} />,
  ol: ({ ...props }) => <ol className="my-1.5 list-decimal space-y-1 pl-4" {...props} />,
  li: ({ ...props }) => <li className="ml-1" {...props} />,
  code: ({ ...props }) => <code className="rounded border border-white/20 bg-black/45 px-1.5 py-0.5 text-xs text-cyan-200" {...props} />,
  pre: ({ ...props }) => <pre className="my-2" {...props} />,
  blockquote: ({ ...props }) => <blockquote className="my-2 border-l-2 border-cyan-300/60 bg-white/5 py-1 pl-3 text-slate-300" {...props} />,
  strong: ({ ...props }) => <strong className="font-semibold text-cyan-100" {...props} />,
  a: ({ ...props }) => <a className="text-cyan-300 underline hover:text-cyan-200" target="_blank" rel="noopener noreferrer" {...props} />,
  table: ({ ...props }) => <table className="my-2 w-full border-collapse border border-white/20 text-sm" {...props} />,
  th: ({ ...props }) => <th className="border border-white/20 bg-white/10 px-2 py-1 text-left font-semibold text-cyan-200" {...props} />,
  td: ({ ...props }) => <td className="border border-white/20 px-2 py-1 text-slate-100" {...props} />,
};

interface Message {
  role: 'Matheus' | 'Quinta-Feira';
  content: string;
}

export default function QuintaFeiraInterface() {
  const [wsConnected, setWsConnected] = useState(false);
  const [cloudMode, setCloudMode] = useState(false);  // ← Track cloud fallback
  const [statusLabel, setStatusLabel] = useState("Conectando...");
  const [mensagem, setMensagem] = useState("");
  const [historico, setHistorico] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [toast, setToast] = useState("");

  const ws = useRef<WebSocket | null>(null);
  const chatFimRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);  // ← V1 BARGE-IN
  const currentAudioPlayingRef = useRef(false);  // ← Track if audio is currently playing
  const wsConnectAttempts = useRef(0);  // ← Track reconnection attempts
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);  // ← Debounce scroll

  // ===== TOCAR ÁUDIO BASE64 (Firewall contra vazamento) =====
  const tocarAudioBase64 = async (audioBase64: string) => {
    try {
      console.log("[AUDIO] Tocando Base64 (tamanho: " + audioBase64.length + " chars)");
      
      // Converter Base64 → Blob
      const binaryString = atob(audioBase64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: 'audio/wav' });
      
      // Criar URL do objeto
      const audioUrl = URL.createObjectURL(blob);
      
      // Atribuir ao audio ref e tocar
      if (audioRef.current) {
        audioRef.current.src = audioUrl;
        audioRef.current.play().catch(e => console.error("[AUDIO] Erro ao tocar:", e));
        currentAudioPlayingRef.current = true;
      }
    } catch (error) {
      console.error("[AUDIO] Erro ao processar Base64:", error);
    }
  };

  // ===== AUTO-SCROLL COM DEBOUNCE (evita loop infinito de renders) =====
  useEffect(() => {
    // Limpar timeout anterior
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }
    
    // Agendar scroll para 100ms depois (debounce previne múltiplos fires)
    scrollTimeoutRef.current = setTimeout(() => {
      chatFimRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 100);
    
    // Cleanup: limpar timeout se dependências mudarem novamente
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, [historico, isLoading]);

  // ===== V1 BARGE-IN HANDLER =====
  const handleBargeinRequested = () => {
    console.log('[BARGE_IN] Interrompendo áudio da IA...');
    
    // 1. Parar áudio imediatamente
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    currentAudioPlayingRef.current = false;
    
    // 2. Cancelar loading (se houver resposta em streaming)
    setIsLoading(false);
    
    // 3. Enviar sinal de interrupção via WebSocket
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type: "interrupt",
        reason: "user_speech_detected",
        timestamp: Date.now()
      }));
      console.log('[INTERRUPT] Sinal enviado ao backend');
    }
    
    setToast("🔄 Áudio interrompido. Aguardando seu comando...");
  };

  useEffect(() => {
    const connectWebSocket = () => {
      try {
        // ✓ SSR-SAFE: Check if in browser before accessing window globals
        const isBrowser = typeof window !== 'undefined';
        
        // Smart WebSocket URL construction
        const wsProtocol = (isBrowser && window.location.protocol === "https:") ? "wss:" : "ws:";
        const wsHost = process.env.NEXT_PUBLIC_WS_HOST || (isBrowser ? window.location.hostname : "127.0.0.1");
        const wsPort = process.env.NEXT_PUBLIC_WS_PORT || "8080";  // ✓ FALLBACK PORTA 8080
        const wsPath = process.env.NEXT_PUBLIC_WS_PATH || "/ws";
        
        const wsUrl = `${wsProtocol}//${wsHost}:${wsPort}${wsPath}`;
        
        // Log se debug ativado
        if (process.env.NEXT_PUBLIC_DEBUG === 'true') {
          console.log(`[WS] Proto=${wsProtocol}, Host=${wsHost}, Port=${wsPort}, Path=${wsPath}`);
          console.log(`[WS] URL: ${wsUrl}`);
        }

        // ⏱️ Set timeout para conexão - se demorar >5s, assumir que PC está offline
        const timeout = setTimeout(() => {
          if (ws.current && ws.current.readyState === WebSocket.CONNECTING) {
            console.log("[WS] Timeout na conexão - assumindo PC offline");
            ws.current?.close();
            setWsConnected(false);
            setCloudMode(true);
            setStatusLabel("Modo Nuvem (PC offline)");
            setToast("🌐 PC não respondeu. Ativando Modo Nuvem...");
          }
        }, 5000);

        ws.current = new WebSocket(wsUrl);

        ws.current.onopen = () => {
          clearTimeout(timeout);
          wsConnectAttempts.current = 0;  // Reset attempt counter
          setWsConnected(true);
          setCloudMode(false);  // Desativar modo nuvem
          setStatusLabel("Online");
          setToast("Núcleo conectado. Pronto para comandos.");
        };

        ws.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // ===== FIREWALL: Detectar Base64 vazado em "streaming" =====
            if (data.type === 'streaming' && data.content) {
              // Detectar headers de áudio
              const isAudioBase64 = 
                data.content.startsWith("UklGR") ||    // WAV/RIFF
                data.content.startsWith("SUQz") ||     // MP3/ID3
                data.content.startsWith("/+MYxA") ||   // MP3 frame sync
                data.content.startsWith("ID3");        // ID3 tag
              
              // Detectar padrão suspeito: muito longo + sem espaços = Base64 puro
              const isLongoSemEspacos = 
                data.content.length > 1000 && 
                !data.content.includes(" ") &&
                /^[A-Za-z0-9+/=]+$/.test(data.content);
              
              // Se detectar Base64, NÃO processar como texto
              if (isAudioBase64 || isLongoSemEspacos) {
                console.warn("[FIREWALL] ⚠️ Base64 DETECTADO E BLOQUEADO! Redirecionando para áudio.");
                console.warn(`[FIREWALL] Tamanho: ${data.content.length} chars, AudioBase64: ${isAudioBase64}, LongoSemEspacos: ${isLongoSemEspacos}`);
                tocarAudioBase64(data.content);
                setIsLoading(false);
                return; // ← SAIR ANTES DE setHistorico
              }

              // Processamento NORMAL de texto
              setHistorico(prev => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.role === 'Quinta-Feira') {
                  return [...prev.slice(0, -1), { ...lastMsg, content: lastMsg.content + data.content }];
                }
                return prev;
              });
            } 
            // Novo evento específico para áudio (enviado pelo backend refatorado)
            else if (data.type === 'audio' && data.audio) {
              console.log("[WS] Áudio recebido (via type=audio)");
              tocarAudioBase64(data.audio);
            }
            else if (data.type === 'complete') {
              setIsLoading(false);
              if (data.content) {
                setHistorico(prev => {
                  const lastMsg = prev[prev.length - 1];
                  if (lastMsg?.role === 'Quinta-Feira' && !lastMsg.content) {
                    return [...prev.slice(0, -1), { role: 'Quinta-Feira', content: data.content }];
                  }
                  return prev;
                });
              }
            } else if (data.type === 'error') {
              setToast(`Erro: ${data.message || 'falha no processamento.'}`);
              setIsLoading(false);
            } else if (data.text && !data.type) {
              setHistorico(prev => [...prev, { role: "Quinta-Feira", content: data.text }]);
              setIsLoading(false);
            }
          } catch {
            setHistorico(prev => [...prev, { role: "Quinta-Feira", content: event.data }]);
            setIsLoading(false);
          }
        };

        ws.current.onclose = () => {
          setWsConnected(false);
          
          // Incrementar tentativas de reconexão
          wsConnectAttempts.current += 1;
          
          if (wsConnectAttempts.current >= 2) {
            // Depois de 2 falhas, ativar modo nuvem
            setCloudMode(true);
            setStatusLabel("🌐 Modo Nuvem (PC offline)");
            console.log("[WS] PC não acessível - ativando modo nuvem permanente");
            setToast("🌐 Modo Nuvem ativado. PC indisponível.");
          } else {
            // Primeira falha: tentar reconectar em 2.5s
            setStatusLabel("Reconectando...");
            console.log(`[WS] Tentativa de reconexão ${wsConnectAttempts.current}...`);
            setTimeout(connectWebSocket, 2500);
          }
        };

        ws.current.onerror = (error) => {
          console.error("[WS] Erro WebSocket:", error);
          setWsConnected(false);
          if (!cloudMode) {
            setStatusLabel("Erro na conexão...");
          }
        };
      } catch (err) {
        console.error("[WS] Erro ao inicializar:", err);
        setCloudMode(true);
        setStatusLabel("🌐 Modo Nuvem (erro)");
        setToast("Fallback para Modo Nuvem.");
      }
    };

    connectWebSocket();
    return () => { 
      ws.current?.close();
      // Don't reconnect if unmounting
    };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 2600);
    return () => clearTimeout(timer);
  }, [toast]);

  // ✓ NOVO: MODO NUVEM - Fallback para API REST quando PC offline
  const enviarModoNuvem = async (textoEntrada: string) => {
    try {
      console.log("[CLOUD] Enviando via API REST (PC offline)");
      setToast("🌐 Enviando via Modo Nuvem...");
      
      // Get API URL from env or construct default
      let apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!apiUrl) {
        // Default: same host as frontend (SSR-SAFE)
        const isBrowser = typeof window !== 'undefined';
        if (isBrowser) {
          const protocol = window.location.protocol === "https:" ? "https:" : "http:";
          const host = window.location.host;  // includes port if non-standard
          apiUrl = `${protocol}//${host}/api/chat`;
        } else {
          // Fallback para SSR
          apiUrl = "http://127.0.0.1:3000/api/chat";
        }
      }
      
      if (process.env.NEXT_PUBLIC_DEBUG === 'true') {
        console.log(`[CLOUD] API URL: ${apiUrl}`);
      }
      
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: textoEntrada,
          user_id: "matheus_admin",
          mode: "cloud"
        })
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      const botResponse = data.response || data.text || "Erro ao processar";
      
      setHistorico(prev => [...prev, { role: "Quinta-Feira", content: botResponse }]);
      setToast("✓ Resposta recebida (Modo Nuvem)");
      setIsLoading(false);
    } catch (error) {
      console.error("[CLOUD] Erro na API:", error);
      setToast("❌ Modo Nuvem indisponível. Verifique a configuração.");
      setIsLoading(false);
    }
  };

  const enviarMensagemTexto = (textoEntrada: string = mensagem) => {
    if (textoEntrada.trim() === "") return;

    setHistorico(prev => [...prev, { role: "Matheus", content: textoEntrada }]);
    setHistorico(prev => [...prev, { role: "Quinta-Feira", content: "" }]);
    setIsLoading(true);

    // ✓ NOVO: Decidir entre PC (WebSocket) ou Nuvem (REST)
    if (wsConnected && ws.current && !cloudMode) {
      // VM conectada: usar WebSocket
      const payload = JSON.stringify({
        type: "chat",
        payload: textoEntrada,
        message: textoEntrada,
        user_id: "matheus_admin"
      });
      
      try {
        ws.current.send(payload);
      } catch (err) {
        console.error("[MSG] Erro ao enviar via WebSocket:", err);
        setCloudMode(true);
        enviarModoNuvem(textoEntrada);
      }
    } else {
      // PC offline: usar Modo Nuvem
      console.log("[MSG] Enviando via Modo Nuvem");
      enviarModoNuvem(textoEntrada);
    }
    
    if (textoEntrada === mensagem) setMensagem("");
  };

  const limparChat = () => {
    setHistorico([]);
    setToast("Histórico limpo.");
  };

  const onSubmitMensagem = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    enviarMensagemTexto();
  };

  const chips = [
    "Abrir YouTube e tocar lo-fi",
    "Aumentar volume para 60%",
    "Resumo das tarefas de hoje",
    "Pesquisar noticias de tecnologia"
  ];

  return (
    <div className="deck-bg relative flex min-h-screen w-full items-stretch justify-center px-4 py-6 text-white md:px-6">
      <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-60">
        <div className="hud-grid absolute inset-0" />
        <div className="absolute -left-28 -top-20 h-72 w-72 rounded-full bg-cyan-300/15 blur-3xl" />
        <div className="absolute -right-20 top-1/3 h-72 w-72 rounded-full bg-amber-300/10 blur-3xl" />
      </div>

      <div className="deck-card relative z-10 flex w-full max-w-6xl flex-col overflow-hidden rounded-[28px] border border-cyan-100/20">
        <header className="border-b border-cyan-100/15 px-5 py-4 md:px-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg border border-cyan-100/25 bg-cyan-200/10 px-2.5 py-1.5">
                <span className="text-xs font-bold tracking-[0.2em] text-cyan-100">QF//01</span>
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-wide text-cyan-50 md:text-2xl">Quinta-Feira</h1>
                <p className="text-xs text-cyan-50/65 md:text-sm">Interface de comando, voz e contexto em tempo real.</p>
              </div>
            </div>

            <div className={`rounded-full border px-4 py-1.5 text-xs font-medium tracking-wide flex items-center gap-2 ${
              wsConnected && !cloudMode 
                ? "border-cyan-300/50 bg-cyan-300/12 text-cyan-100" 
                : "border-amber-200/50 bg-amber-200/15 text-amber-100"
            }`}>
              {wsConnected && !cloudMode ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-cyan-300 animate-pulse" />
                  NÚCLEO ONLINE
                </>
              ) : (
                <>
                  <span className="h-2 w-2 rounded-full bg-amber-300 animate-pulse" />
                  {cloudMode ? "🌐 MODO NUVEM" : statusLabel.toUpperCase()}
                </>
              )}
            </div>
          </div>
        </header>

        <main className="grid flex-1 grid-cols-1 gap-4 p-4 md:grid-cols-[1fr_300px] md:p-6">
          <section className="flex min-h-[62vh] flex-col overflow-hidden rounded-2xl border border-cyan-100/15 bg-black/25">
            <div className="flex items-center justify-between border-b border-cyan-100/15 px-4 py-3 text-[11px] uppercase tracking-[0.14em] text-cyan-50/60">
              <span>Console</span>
              <button
                type="button"
                onClick={limparChat}
                className="rounded-full border border-cyan-100/20 px-3 py-1 transition hover:border-cyan-100/40 hover:bg-cyan-100/10"
              >
                Limpar
              </button>
            </div>

            <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-4 py-4">
              {historico.length === 0 && !isLoading ? (
                <div className="mx-auto mt-10 max-w-md rounded-2xl border border-cyan-100/15 bg-cyan-100/5 p-6 text-center">
                  <p className="text-lg font-semibold text-cyan-50">Canal aberto</p>
                  <p className="mt-2 text-sm text-cyan-50/65">Envie texto ou use voz. Respostas chegam em fluxo contínuo.</p>
                </div>
              ) : (
                historico.map((msg, idx) => (
                  <div key={`${msg.role}-${idx}`} className={`flex ${msg.role === "Matheus" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-lg ${msg.role === "Matheus" ? "rounded-br-sm border border-cyan-100/30 bg-cyan-200/90 text-slate-900" : "rounded-bl-sm border border-cyan-100/20 bg-slate-900/45 text-cyan-50"}`}>
                      {msg.role === "Quinta-Feira" ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                          {msg.content || "..."}
                        </ReactMarkdown>
                      ) : (
                        <p>{msg.content}</p>
                      )}
                    </div>
                  </div>
                ))
              )}

              {isLoading ? (
                <div className="flex justify-start">
                  <div className="rounded-xl border border-cyan-100/20 bg-slate-900/40 px-3 py-2">
                    <span className="inline-flex items-center gap-1">
                      <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-100/85" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-100/85 [animation-delay:120ms]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-100/85 [animation-delay:240ms]" />
                    </span>
                  </div>
                </div>
              ) : null}

              <div ref={chatFimRef} />
            </div>

            <div className="border-t border-cyan-100/15 p-3 md:p-4">
              <form onSubmit={onSubmitMensagem} className="flex gap-2">
                <input
                  value={mensagem}
                  onChange={(e) => setMensagem(e.target.value)}
                  placeholder={cloudMode ? "Comando de nuvem (sem ferramentas PC)..." : "Digite seu comando"}
                  className="w-full rounded-xl border border-cyan-100/20 bg-slate-900/40 px-4 py-3 text-sm text-cyan-50 placeholder:text-cyan-50/40 outline-none transition focus:border-cyan-200/70"
                  disabled={isLoading || (!wsConnected && !cloudMode)}
                />
                <button
                  type="submit"
                  disabled={isLoading || (!wsConnected && !cloudMode) || !mensagem.trim()}
                  className="rounded-xl border border-cyan-100/30 bg-cyan-200 px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {isLoading ? "..." : "Enviar"}
                </button>
              </form>
              {cloudMode && (
                <p className="mt-2 text-xs text-amber-200">
                  ⚠️  Modo Nuvem: sem acesso a Spotify, YouTube, Terminal ou automação local
                </p>
              )}
            </div>
          </section>

          <aside className="flex flex-col gap-4">
            <section className="rounded-2xl border border-cyan-100/15 bg-black/25 p-4">
              <h2 className="text-sm font-semibold text-cyan-50">Voz</h2>
              <p className="mt-1 text-xs text-cyan-50/60">
                {cloudMode 
                  ? "Voz disponível em Modo Nuvem"
                  : "Diga \"Quinta-Feira\" e depois o comando."
                }
              </p>
              <div className="mt-4">
                <VoiceControl 
                  onCommand={(command) => enviarMensagemTexto(command)} 
                  isDisabled={isLoading}  // ← Allow in cloud mode
                  onBargein={handleBargeinRequested}
                  onBrowserWarning={(msg) => setToast(msg)}
                />
              </div>
            </section>

            <section className="rounded-2xl border border-cyan-100/15 bg-black/25 p-4">
              <h2 className="text-sm font-semibold text-cyan-50">Ações rápidas</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                {chips.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => enviarMensagemTexto(chip)}
                    disabled={isLoading || (!wsConnected && !cloudMode)}
                    title={cloudMode ? "Disponível em Modo Nuvem" : ""}
                    className="rounded-full border border-cyan-100/20 bg-cyan-100/5 px-3 py-1.5 text-xs text-cyan-50/90 transition hover:bg-cyan-100/15 disabled:opacity-40"
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-cyan-100/15 bg-black/25 p-4 text-xs text-cyan-50/75">
              <p className="uppercase tracking-[0.14em] text-cyan-50/65">Atalhos</p>
              <p className="mt-2">Enter: enviar mensagem</p>
              <p>Diagnóstico: /diagnose</p>
              <p>Status: {statusLabel}</p>
            </section>
          </aside>
        </main>

        {toast ? (
          <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-cyan-100/25 bg-slate-900/70 px-4 py-2 text-xs text-cyan-50 backdrop-blur">
            {toast}
          </div>
        ) : null}
      </div>
    </div>
  );
}