"use client";

import { useState, useEffect, useRef, useCallback } from 'react';

interface ConversationMessage {
  role: 'user' | 'assistant';
  text: string;
  timestamp: number;
}

// Estado global de reprodução de áudio (para barge-in)
let currentAudioPlayback: HTMLAudioElement | null = null;
let isAudioPlaying = false;

export default function QuintaFeiraInterface() {
  const [status, setStatus] = useState("Desconectado");
  const [mensagem, setMensagem] = useState("");
  const [historico, setHistorico] = useState<ConversationMessage[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [diagnosticoVoz, setDiagnosticoVoz] = useState("");
  
  const ws = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatFimRef = useRef<HTMLDivElement | null>(null);
  const wakeRecognitionRef = useRef<any>(null);
  const recognitionRef = useRef<any>(null);
  const interruptRef = useRef(false);

  // ====== INICIALIZAÇÃO WEBSOCKET ======
  
  useEffect(() => {
    const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocolo}//${window.location.host}/ws`;
    
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setStatus("Conectado (Núcleo Online)");
      console.log("✓ Túnel WebSocket estabelecido");
    };

    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Adicionar resposta ao histórico
        setHistorico(prev => [...prev, {
          role: 'assistant',
          text: data.text,
          timestamp: Date.now()
        }]);

        // Reproduzir áudio se disponível (com barge-in)
        if (data.audio) {
          reproduzirAudioComBargeIn(data.audio);
        } else {
          reproduzirEstimuloConfirmacao();
        }
        
        setIsProcessing(false);
        
      } catch (e) {
        console.error("Erro ao parsear resposta:", e);
        setIsProcessing(false);
      }
    };

    ws.current.onerror = () => {
      setStatus("Erro na Conexão");
    };

    ws.current.onclose = () => {
      setStatus("Sinal Perdido (Desconectado)");
    };

    return () => {
      ws.current?.close();
    };
  }, []);

  // ====== AUTO-SCROLL ======
  
  useEffect(() => {
    chatFimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historico]);

  // ====== BARGE-IN: Interrupção de Áudio ======
  
  const interromperAudio = useCallback(() => {
    """
    Cancela reprodução de áudio atual (barge-in).
    Called quando o usuário começa a falar durante a resposta da IA.
    """
    if (currentAudioPlayback) {
      currentAudioPlayback.pause();
      currentAudioPlayback.currentTime = 0;
      currentAudioPlayback = null;
    }
    isAudioPlaying = false;
    interruptRef.current = true;
  }, []);

  const reproduzirAudioComBargeIn = (audioBase64: string) => {
    """
    Reproduz áudio com suporte a barge-in.
    Se o usuário começar a falar, o áudio é cancelado instantaneamente.
    """
    try {
      // Parar áudio anterior
      if (currentAudioPlayback) {
        currentAudioPlayback.pause();
        currentAudioPlayback = null;
      }

      // Criar novo elemento de áudio
      const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
      audio.onplay = () => {
        isAudioPlaying = true;
        interruptRef.current = false;
      };
      audio.onended = () => {
        isAudioPlaying = false;
        currentAudioPlayback = null;
      };
      audio.onerror = () => {
        console.error("Erro ao reproduzir áudio");
        isAudioPlaying = false;
      };

      currentAudioPlayback = audio;
      audio.play().catch(err => {
        console.error("Falha ao iniciar reprodução:", err);
        isAudioPlaying = false;
      });
      
    } catch (e) {
      console.error("Erro ao criar áudio:", e);
    }
  };

  const reproduzirEstimuloConfirmacao = () => {
    """
    Pequeno beep de confirmação quando não há áudio.
    """
    try {
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      oscillator.frequency.value = 800;
      oscillator.type = 'sine';
      
      gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);
      
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.1);
    } catch (e) {
      console.error("Erro ao reproduzir estímulo:", e);
    }
  };

  // ====== RECONHECIMENTO DE VOZ (Web Speech API) ======
  
  const inicializarReconhecimento = () => {
    """
    Inicializa Web Speech API com suporte a barge-in.
    Quando detectar fala, interrompe áudio em andamento.
    """
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setDiagnosticoVoz("Navegador não suporta Web Speech API");
      return null;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'pt-BR';

    let transcript = '';

    recognition.onstart = () => {
      setIsListening(true);
      transcript = '';
      // *** BARGE-IN: Quando começa a escutar, interromper áudio da IA ***
      interromperAudio();
    };

    recognition.onresult = (event: any) => {
      transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setMensagem(transcript);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.onerror = (event: any) => {
      if (event.error === 'network') {
        setDiagnosticoVoz("Erro de rede no reconhecimento de voz");
      } else {
        setDiagnosticoVoz(`Erro: ${event.error}`);
      }
    };

    return recognition;
  };

  // ====== ENVIO DE MENSAGENS ======
  
  const enviarMensagem = async (textoMensagem: string = mensagem) => {
    """
    Envia mensagem via WebSocket e inicia processamento.
    """
    if (!textoMensagem.trim() || !ws.current || ws.current.readyState !== WebSocket.OPEN) {
      return;
    }

    // Interromper áudio em progresso
    interromperAudio();

    // Adicionar ao histórico
    setHistorico(prev => [...prev, {
      role: 'user',
      text: textoMensagem,
      timestamp: Date.now()
    }]);

    setMensagem("");
    setIsProcessing(true);

    try {
      ws.current.send(JSON.stringify({
        type: 'chat',
        payload: textoMensagem
      }));
    } catch (e) {
      console.error("Erro ao enviar:", e);
      setIsProcessing(false);
    }
  };

  // ====== HOTKEY: CMD+K para ativar microfone ======
  
  useEffect(() => {
    if (!recognitionRef.current) {
      recognitionRef.current = inicializarReconhecimento();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + K: ativar microfone
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (recognitionRef.current) {
          recognitionRef.current.start();
        }
      }
      // Enter: enviar
      if (e.key === 'Enter' && !e.shiftKey && !isProcessing) {
        e.preventDefault();
        enviarMensagem();
      }
      // Esc: interromper áudio
      if (e.key === 'Escape') {
        interromperAudio();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mensagem, isProcessing]);

  // ====== RENDER ======
  
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      backgroundColor: '#0a0e27',
      color: '#e0e0e0',
      fontFamily: 'monospace'
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 20px',
        borderBottom: '1px solid #333',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <h1 style={{ margin: '0 0 4px 0', fontSize: '16px' }}>QUINTA-FEIRA v2</h1>
          <p style={{ margin: 0, fontSize: '12px', color: '#888' }}>
            Status: <span style={{ color: status.includes('Online') ? '#0f0' : '#f88' }}>
              {status}
            </span>
          </p>
        </div>
        <div style={{ fontSize: '12px', color: '#888' }}>
          {isProcessing && '⏳ Processando...'}
          {isAudioPlaying && !isProcessing && '🔊 Áudio em andamento'}
          {isListening && '🎤 Ouvindo...'}
        </div>
      </div>

      {/* Histórico */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px'
      }}>
        {historico.length === 0 && (
          <div style={{ color: '#666', textAlign: 'center', marginTop: '20px' }}>
            [Histórico vazio]<br/>
            Cmd+K: Ativar Microfone | Enter: Enviar | Esc: Parar Áudio
          </div>
        )}
        
        {historico.map((msg, idx) => (
          <div key={idx} style={{
            padding: '8px 12px',
            backgroundColor: msg.role === 'user' ? '#1a3a2a' : '#2a1a3a',
            borderLeft: `3px solid ${msg.role === 'user' ? '#0f0' : '#f0f'}`,
            borderRadius: '4px'
          }}>
            <p style={{ margin: '0 0 4px 0', fontSize: '11px', color: msg.role === 'user' ? '#0f0' : '#f0f' }}>
              {msg.role === 'user' ? '[USUÁRIO]' : '[QUINTA-FEIRA]'}
            </p>
            <p style={{ margin: 0, fontSize: '13px', whiteSpace: 'pre-wrap' }}>
              {msg.text}
            </p>
          </div>
        ))}
        
        <div ref={chatFimRef} />
      </div>

      {/* Input */}
      <div style={{
        borderTop: '1px solid #333',
        padding: '12px 16px',
        display: 'flex',
        gap: '8px'
      }}>
        <input
          type="text"
          value={mensagem}
          onChange={(e) => setMensagem(e.target.value)}
          placeholder="Digite ou Cmd+K para gravar..."
          disabled={isProcessing}
          style={{
            flex: 1,
            backgroundColor: '#111',
            color: '#0f0',
            border: '1px solid #333',
            padding: '8px 12px',
            borderRadius: '4px',
            fontFamily: 'monospace',
            fontSize: '13px'
          }}
        />
        <button
          onClick={() => enviarMensagem()}
          disabled={isProcessing || !mensagem.trim()}
          style={{
            padding: '8px 16px',
            backgroundColor: '#0f0',
            color: '#000',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: '12px'
          }}
        >
          ENVIAR
        </button>
        <button
          onClick={interromperAudio}
          style={{
            padding: '8px 16px',
            backgroundColor: '#f08',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '12px'
          }}
        >
          PARAR
        </button>
      </div>

      {/* Diagnóstico */}
      {diagnosticoVoz && (
        <div style={{
          padding: '8px 12px',
          backgroundColor: '#3a2a1a',
          color: '#fa8',
          fontSize: '11px',
          borderTop: '1px solid #333'
        }}>
          ⚠ {diagnosticoVoz}
        </div>
      )}
    </div>
  );
}
