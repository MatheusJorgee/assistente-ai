"use client";

import { useState, useEffect, useRef } from 'react';

export default function QuintaFeiraInterface() {
  const [status, setStatus] = useState("Desconectado");
  const [mensagem, setMensagem] = useState("");
  const [historico, setHistorico] = useState<{ role: string, text: string }[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [wakeModeAtivo, setWakeModeAtivo] = useState(false);
  const [diagnosticoVoz, setDiagnosticoVoz] = useState("");
  
  const ws = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatFimRef = useRef<HTMLDivElement | null>(null); // Ref para o auto-scroll
  const wakeRecognitionRef = useRef<any>(null);
  const wakeDesiredRef = useRef(false);
  const aguardandoFeiraRef = useRef(false);
  const aguardandoFeiraTimeoutRef = useRef<any>(null);
  const aguardandoComandoRef = useRef(false);
  const comandoBufferRef = useRef("");
  const comandoFlushTimeoutRef = useRef<any>(null);
  const comandoRapidoBufferRef = useRef("");
  const comandoRapidoFlushTimeoutRef = useRef<any>(null);
  const comandoRapidoRecognitionRef = useRef<any>(null);
  const pendingSilentAckRef = useRef(false);

  const isGoogleChrome = () => {
    const nav: any = window.navigator;
    const ua = nav.userAgent || "";
    const vendor = nav.vendor || "";
    const isBrave = !!nav.brave;

    return ua.includes("Chrome") && vendor.includes("Google") && !ua.includes("Edg") && !ua.includes("OPR") && !isBrave;
  };

  const validarNavegadorParaVoz = () => {
    if (!isGoogleChrome()) {
      setDiagnosticoVoz("Modo voz completo requer Google Chrome. No Brave pode ocorrer erro 'network'.");
      return false;
    }
    return true;
  };

  // Rola o chat para o fundo automaticamente quando há mensagens novas
  useEffect(() => {
    chatFimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historico]);

  useEffect(() => {
    const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocolo}//${window.location.host}/ws`; 
    
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setStatus("Conectado (Núcleo Online)");
      console.log(">>> Túnel WebSocket estabelecido.");
    };

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setHistorico(prev => [...prev, { role: "Quinta-Feira", text: data.text }]);

      if (pendingSilentAckRef.current) {
        tocarEstimuloConfirmacao();
        pendingSilentAckRef.current = false;
      } else if (data.audio) {
        tocarAudioBase64(data.audio);
      }
    };

    ws.current.onclose = () => {
      setStatus("Sinal Perdido (Desconectado)");
    };

    return () => {
      ws.current?.close();
    };
  }, []);

  const enviarMensagemTexto = (textoParaEnviar: string = mensagem) => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
      setDiagnosticoVoz("WebSocket offline: comando de voz não enviado.");
      return;
    }
    if (textoParaEnviar.trim() === "") return;

    setHistorico(prev => [...prev, { role: "Matheus", text: textoParaEnviar }]);

    const payload = JSON.stringify({
      type: "chat",
      payload: textoParaEnviar
    });

    pendingSilentAckRef.current = deveResponderSemFala(textoParaEnviar);
    
    ws.current.send(payload);
    if (textoParaEnviar === mensagem) setMensagem(""); 
  };

  const normalizarTexto = (texto: string) => {
    return texto
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-zA-Z0-9\s-]/g, " ")
      .replace(/\s+/g, " ")
      .toLowerCase()
      .trim();
  };

  const contemPalavraAtivacao = (texto: string) => {
    const t = normalizarTexto(texto);
    return /quinta[\s-]*(feira|fera)/.test(t) || t.includes("quintafeira") || t.includes("quintafera");
  };

  const contemQuinta = (texto: string) => {
    const t = normalizarTexto(texto);
    return /\bquinta\b/.test(t);
  };

  const contemFeira = (texto: string) => {
    const t = normalizarTexto(texto);
    return /\b(feira|fera)\b/.test(t);
  };

  const iniciarEscutaComando = () => {
    if (!validarNavegadorParaVoz()) return;

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    
    if (!SpeechRecognition) {
      alert("O seu navegador não suporta reconhecimento de voz. Tente usar o Google Chrome.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    if (comandoRapidoRecognitionRef.current) {
      try {
        comandoRapidoRecognitionRef.current.onend = null;
        comandoRapidoRecognitionRef.current.stop();
      } catch {}
      comandoRapidoRecognitionRef.current = null;
    }

    comandoRapidoBufferRef.current = "";
    if (comandoRapidoFlushTimeoutRef.current) {
      clearTimeout(comandoRapidoFlushTimeoutRef.current);
      comandoRapidoFlushTimeoutRef.current = null;
    }
    comandoRapidoRecognitionRef.current = recognition;

    recognition.onstart = () => {
      setIsListening(true);
      setDiagnosticoVoz("Microfone ativo. Pode falar...");
    };

    const flushComandoRapido = () => {
      const transcricaoBruta = comandoRapidoBufferRef.current.trim();
      comandoRapidoBufferRef.current = "";

      if (!transcricaoBruta) {
        setDiagnosticoVoz("Não consegui capturar a frase inteira. Tente novamente.");
        return;
      }

      const transcricao = transcricaoBruta
        .replace(/quinta\s*feira/gi, "")
        .replace(/quintafeira/gi, "")
        .trim();

      if (transcricao) {
        const comandoAjustado = ajustarComandoBilingue(transcricao);
        setDiagnosticoVoz(`Comando enviado: ${comandoAjustado}`);
        enviarMensagemTexto(comandoAjustado);
      }
    };

    recognition.onresult = (event: any) => {
      let houveFinal = false;
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const resultado = event.results[i];
        if (!resultado?.isFinal) continue;
        houveFinal = true;
        comandoRapidoBufferRef.current = `${comandoRapidoBufferRef.current} ${resultado[0].transcript || ""}`.trim();
      }

      if (houveFinal) {
        if (comandoRapidoFlushTimeoutRef.current) {
          clearTimeout(comandoRapidoFlushTimeoutRef.current);
        }
        // Aguarda uma pequena pausa para juntar frases quebradas pelo motor de voz.
        comandoRapidoFlushTimeoutRef.current = setTimeout(() => {
          comandoRapidoFlushTimeoutRef.current = null;
          try {
            recognition.stop();
          } catch {
            flushComandoRapido();
          }
        }, 1400);
      }
    };

    recognition.onerror = (event: any) => {
      if (event.error !== "no-speech") {
        console.error("Erro no microfone: ", event.error);
      }
      if (event.error !== "no-speech") {
        setDiagnosticoVoz(`Erro no microfone: ${event.error}`);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      if (comandoRapidoFlushTimeoutRef.current) {
        clearTimeout(comandoRapidoFlushTimeoutRef.current);
        comandoRapidoFlushTimeoutRef.current = null;
      }
      flushComandoRapido();
      comandoRapidoRecognitionRef.current = null;
      setIsListening(false);
    };

    recognition.start();
  };

  const pararModoDespertar = () => {
    wakeDesiredRef.current = false;
    aguardandoFeiraRef.current = false;
    aguardandoComandoRef.current = false;
    setWakeModeAtivo(false);
    setIsListening(false);
    if (aguardandoFeiraTimeoutRef.current) {
      clearTimeout(aguardandoFeiraTimeoutRef.current);
      aguardandoFeiraTimeoutRef.current = null;
    }
    if (comandoFlushTimeoutRef.current) {
      clearTimeout(comandoFlushTimeoutRef.current);
      comandoFlushTimeoutRef.current = null;
    }
    comandoBufferRef.current = "";
    if (wakeRecognitionRef.current) {
      try {
        wakeRecognitionRef.current.onend = null;
        wakeRecognitionRef.current.stop();
      } catch {}
      wakeRecognitionRef.current = null;
    }
  };

  const extrairComandoAposWake = (texto: string) => {
    const t = normalizarTexto(texto);
    return t
      .replace(/quintafeira/gi, "")
      .replace(/quintafera/gi, "")
      .replace(/quinta\s*fera/gi, "")
      .replace(/quinta[\s-]*feira/gi, "")
      .trim();
  };

  const flushComandoBuffer = () => {
    const comandoLimpo = extrairComandoAposWake(comandoBufferRef.current);
    comandoBufferRef.current = "";
    aguardandoComandoRef.current = false;
    setIsListening(false);

    if (!comandoLimpo) {
      setDiagnosticoVoz("Não entendi o comando após a ativação.");
      return;
    }

    const comandoAjustado = ajustarComandoBilingue(comandoLimpo);
    setDiagnosticoVoz(`Comando enviado: ${comandoAjustado}`);
    enviarMensagemTexto(comandoAjustado);
  };

  const deveResponderSemFala = (texto: string) => {
    const t = normalizarTexto(texto);
    // Comandos curtos de controle: feedback sonoro basta, sem TTS.
    return /\b(volume|baix[ae]|aument[ae]|paus[ae]|retom[ae]|play|pular|proxima|proximo|mute|mudo)\b/.test(t);
  };

  const tocarEstimuloConfirmacao = () => {
    try {
      const AudioCtx = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;

      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = "sine";
      osc.frequency.value = 660;
      gain.gain.value = 0.015;

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start();
      osc.stop(ctx.currentTime + 0.08);

      setTimeout(() => {
        try { ctx.close(); } catch {}
      }, 180);
    } catch {}
  };

  const corrigirTituloInglesComum = (texto: string) => {
    return texto
      .replace(/\bthe\s+perfect\s+(per|par|pear|paira)\b/gi, "the perfect pair")
      .replace(/\bde\s+perfect\s+(per|par|pear|paira)\b/gi, "the perfect pair")
      .replace(/\bperfeit\s+(per|par|pear|paira)\b/gi, "perfect pair");
  };

  const ajustarComandoBilingue = (texto: string) => {
    const base = texto.trim();
    if (!base) return base;

    // Preserva a estrutura do comando e corrige apenas trechos comuns de títulos em inglês.
    let saida = corrigirTituloInglesComum(base);

    // Heurística para pedidos de música com frase mista PT/EN.
    if (/^(toca|toque|play)\b/i.test(saida)) {
      saida = corrigirTituloInglesComum(saida);
    }

    return saida;
  };

  const iniciarModoDespertar = () => {
    if (!validarNavegadorParaVoz()) return;

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("O seu navegador não suporta reconhecimento de voz. Tente usar o Google Chrome.");
      return;
    }

    if (wakeRecognitionRef.current) {
      try {
        wakeRecognitionRef.current.onend = null;
        wakeRecognitionRef.current.stop();
      } catch {}
      wakeRecognitionRef.current = null;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    wakeDesiredRef.current = true;
    setWakeModeAtivo(true);
    setIsListening(false);
    wakeRecognitionRef.current = recognition;

    recognition.onresult = (event: any) => {
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const resultado = event.results[i];
        if (!resultado?.isFinal) continue;

        const texto = resultado[0].transcript || "";
        const textoNorm = normalizarTexto(texto);
        setDiagnosticoVoz(`Ouvido: ${textoNorm || "..."}`);

        if (aguardandoComandoRef.current) {
          comandoBufferRef.current = `${comandoBufferRef.current} ${texto}`.trim();
          if (comandoFlushTimeoutRef.current) {
            clearTimeout(comandoFlushTimeoutRef.current);
          }
          comandoFlushTimeoutRef.current = setTimeout(() => {
            comandoFlushTimeoutRef.current = null;
            flushComandoBuffer();
          }, 3200);
          setDiagnosticoVoz("Capturando comando...");
          continue;
        }

        if (aguardandoFeiraRef.current) {
          if (contemFeira(textoNorm)) {
            aguardandoFeiraRef.current = false;
            if (aguardandoFeiraTimeoutRef.current) {
              clearTimeout(aguardandoFeiraTimeoutRef.current);
              aguardandoFeiraTimeoutRef.current = null;
            }

            const comandoAposWake = extrairComandoAposWake(texto);
            if (comandoAposWake) {
              const comandoAjustado = ajustarComandoBilingue(comandoAposWake);
              setDiagnosticoVoz(`Comando inline enviado: ${comandoAjustado}`);
              enviarMensagemTexto(comandoAjustado);
            } else {
              aguardandoComandoRef.current = true;
              setIsListening(true);
              comandoBufferRef.current = "";
              setDiagnosticoVoz("Wake completa. Fale o comando agora.");
            }
          } else {
            aguardandoFeiraRef.current = false;
            if (aguardandoFeiraTimeoutRef.current) {
              clearTimeout(aguardandoFeiraTimeoutRef.current);
              aguardandoFeiraTimeoutRef.current = null;
            }
            setDiagnosticoVoz("Wake cancelada. Diga 'quinta' e depois 'feira'.");
          }
          continue;
        }

        if (contemPalavraAtivacao(textoNorm)) {
          const comandoInline = extrairComandoAposWake(texto);
          if (comandoInline) {
            const comandoAjustado = ajustarComandoBilingue(comandoInline);
            setDiagnosticoVoz(`Comando inline enviado: ${comandoAjustado}`);
            enviarMensagemTexto(comandoAjustado);
          } else {
            // Wake detectada sem comando na mesma frase: arma próxima fala.
            aguardandoComandoRef.current = true;
            setIsListening(true);
            comandoBufferRef.current = "";
            setDiagnosticoVoz("Ativada. Pode falar o comando agora.");
          }
          continue;
        }

        if (contemQuinta(textoNorm)) {
          aguardandoFeiraRef.current = true;
          if (aguardandoFeiraTimeoutRef.current) {
            clearTimeout(aguardandoFeiraTimeoutRef.current);
          }
          aguardandoFeiraTimeoutRef.current = setTimeout(() => {
            if (aguardandoFeiraRef.current) {
              aguardandoFeiraRef.current = false;
              setDiagnosticoVoz("Não ouvi 'feira' a tempo. Wake reiniciada.");
            }
          }, 2200);
          setDiagnosticoVoz("Ouvi 'quinta'. Diga 'feira' para ativar.");
        }
      }
    };

    recognition.onerror = (event: any) => {
      if (event.error === "no-speech") {
        // Evento comum em escuta contínua: mantém sentinela sem poluir o console.
        if (aguardandoComandoRef.current) {
          setDiagnosticoVoz("Aguardando comando após wake...");
        } else if (aguardandoFeiraRef.current) {
          setDiagnosticoVoz("Aguardando 'feira' para concluir wake...");
        } else {
          setDiagnosticoVoz("Aguardando palavra de ativação...");
        }
        return;
      }

      console.error(">>> [WAKE ERROR]:", event.error);
      setDiagnosticoVoz(`Erro de voz: ${event.error}`);

      if (event.error === "network") {
        wakeDesiredRef.current = false;
        aguardandoFeiraRef.current = false;
        aguardandoComandoRef.current = false;
        setWakeModeAtivo(false);
        setIsListening(false);
        setDiagnosticoVoz("Erro de voz 'network'. Abra a Quinta-Feira no Google Chrome para wake word estável.");
      }

      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        wakeDesiredRef.current = false;
        aguardandoFeiraRef.current = false;
        aguardandoComandoRef.current = false;
        setWakeModeAtivo(false);
        setIsListening(false);
      }
    };

    recognition.onend = () => {
      if (wakeDesiredRef.current) {
        setTimeout(() => iniciarModoDespertar(), 350);
      } else {
        setIsListening(false);
      }
    };

    recognition.start();
  };

  const alternarModoDespertar = () => {
    if (wakeModeAtivo) {
      pararModoDespertar();
    } else {
      iniciarModoDespertar();
    }
  };

  useEffect(() => {
    return () => {
      pararModoDespertar();
      if (comandoRapidoRecognitionRef.current) {
        try {
          comandoRapidoRecognitionRef.current.onend = null;
          comandoRapidoRecognitionRef.current.stop();
        } catch {}
      }
      if (comandoRapidoFlushTimeoutRef.current) {
        clearTimeout(comandoRapidoFlushTimeoutRef.current);
      }
    };
  }, []);

  const tocarAudioBase64 = (base64Audio: string) => {
    // Deteção Dinâmica de Arquitetura: WAV (Local) vs MP3 (ElevenLabs)
    const formato = base64Audio.startsWith("UklGR") ? "audio/wav" : "audio/mpeg";
    const audioSrc = `data:${formato};base64,${base64Audio}`;
    
    if (audioRef.current) {
      audioRef.current.src = audioSrc;
      audioRef.current.play().catch(e => console.error("Navegador bloqueou autoplay:", e));
    }
  };

  return (
    // 'h-screen' garante que a app não ultrapassa a altura do telemóvel
    <div className="flex flex-col h-screen max-h-screen bg-gray-950 text-white p-4 sm:p-8 font-sans">
      
      {/* CABEÇALHO */}
      <div className="flex flex-col items-center flex-shrink-0 mb-4">
        <h1 className="text-2xl sm:text-3xl font-bold text-cyan-400 tracking-wider">QUINTA-FEIRA</h1>
        <div className="flex items-center gap-2 mt-2 bg-gray-900 px-4 py-1.5 rounded-full border border-gray-800">
          <div className={`w-2.5 h-2.5 rounded-full shadow-sm ${status.includes("Conectado") ? "bg-green-500 shadow-green-500/50" : "bg-red-500 shadow-red-500/50"}`}></div>
          <span className="text-xs sm:text-sm font-medium text-gray-300">{status}</span>
        </div>
      </div>

      {/* ÁREA DE MENSAGENS (Scrollable) */}
      <div className="flex-1 overflow-y-auto w-full max-w-3xl mx-auto bg-gray-900/50 rounded-2xl p-4 shadow-inner border border-gray-800/50 flex flex-col gap-4 mb-4 custom-scrollbar">
        {historico.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 text-sm italic">
            Aguardando comandos, Engenheiro...
          </div>
        ) : (
          historico.map((msg, index) => (
            <div key={index} className={`flex ${msg.role === "Matheus" ? "justify-end" : "justify-start"}`}>
              <div 
                className={`max-w-[85%] sm:max-w-[75%] px-4 py-3 text-sm sm:text-base shadow-md ${
                  msg.role === "Matheus" 
                    ? "bg-cyan-700 text-cyan-50 rounded-2xl rounded-tr-sm" 
                    : "bg-gray-800 text-gray-200 rounded-2xl rounded-tl-sm border border-gray-700"
                }`}
              >
                <span className="block text-xs opacity-50 mb-1 font-bold tracking-wide uppercase">
                  {msg.role}
                </span>
                <span className="leading-relaxed">{msg.text}</span>
              </div>
            </div>
          ))
        )}
        {/* Âncora invisível para o scroll descer automaticamente */}
        <div ref={chatFimRef} />
      </div>

      {/* PAINEL DE CONTROLO (Botões e Input) */}
      <div className="w-full max-w-3xl mx-auto flex-shrink-0">
        <div className="flex gap-2 items-center bg-gray-900 p-2 rounded-xl border border-gray-800">
          
          {/* BOTÃO DO MICROFONE */}
          <button 
            onClick={iniciarEscutaComando}
            className={`p-3 sm:px-6 sm:py-3 rounded-lg font-bold transition-all flex items-center justify-center flex-shrink-0 ${
              isListening 
                ? "bg-red-600 animate-pulse shadow-[0_0_15px_rgba(220,38,38,0.5)] text-white" 
                : "bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700"
            }`}
            title="Falar"
          >
            <span className="text-xl">🎤</span>
            <span className="hidden sm:inline ml-2 text-sm">{isListening ? "A OUVIR..." : "FALAR"}</span>
          </button>

          <button
            onClick={alternarModoDespertar}
            className={`p-3 sm:px-4 sm:py-3 rounded-lg font-bold transition-colors text-xs sm:text-sm flex-shrink-0 ${
              wakeModeAtivo
                ? "bg-emerald-700 hover:bg-emerald-600 text-white"
                : "bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700"
            }`}
            title="Modo palavra de ativação"
          >
            {wakeModeAtivo ? "QUINTA-FEIRA ON" : "QUINTA-FEIRA OFF"}
          </button>

          {/* CAIXA DE TEXTO */}
          <input 
            type="text" 
            value={mensagem}
            onChange={(e) => setMensagem(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && enviarMensagemTexto()}
            placeholder="Digite um comando..."
            className="flex-1 w-full bg-transparent p-2 text-white focus:outline-none placeholder-gray-600 text-sm sm:text-base min-w-0"
          />
          
          {/* BOTÃO ENVIAR */}
          <button 
            onClick={() => enviarMensagemTexto()}
            className="p-3 sm:px-6 sm:py-3 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-bold transition-colors shadow-lg shadow-cyan-900/20 flex-shrink-0"
          >
            <span className="hidden sm:inline">ENVIAR</span>
            <span className="sm:hidden text-xl">➤</span>
          </button>
        </div>
        <div className="mt-2 text-xs text-gray-400 min-h-5">
          {diagnosticoVoz || "Diagnóstico de voz: pronto."}
        </div>
      </div>

      <audio ref={audioRef} className="hidden" />
    </div>
  );
}