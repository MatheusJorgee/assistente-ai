/**
 * useQuintaFeira: Custom Hook - Gerenciador WebSocket
 * ====================================================
 *
 * Responsabilidades:
 * - Gerenciar ciclo de vida do WebSocket
 * - Conectar/desconectar com reconexão automática (exponential backoff)
 * - Gerenciar histórico de mensagens
 * - Gerenciar status intermediário (thinking, processing, etc)
 * - Type-safe: Espelha DTOs do backend
 *
 * FILOSOFIA: Transport layer (não faz lógica de negócio)
 * - Apenas Orquestra comunicação com backend
 * - Callbacks/Context no componente pai fazem trabalho real
 *
 * CRÍTICO: Cleanup adequado para:
 * - Evitar vazamentos de memória
 * - Evitar múltiplas conexões em modo dev (React StrictMode)
 * - Fechar timers de reconexão
 */

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type {
  MessageEnvelope,
  MessageType,
  ChatMessage,
  ConnectionStatus,
  UserMessagePayload,
  OutgoingMessageEnvelope,
  IncomingMessageEnvelope,
  IntermediateStatus,
  ApprovalRequest,
  AgoraActivity,
  ApprovalRequestedPayload,
  ApprovalResolvedPayload,
  ToolCallPayload,
  RunCancelledPayload,
  TextDeltaPayload,
  HoloPayload,
} from '@/types';
import type { ActiveMedia } from '@/components/MediaPlayer';
import type { VisorContent } from '@/components/Visor';
import { parseHoloPayload } from '@/lib/holo';
import { obterToken, protocolosDoToken } from '@/lib/quintaAuth';
import { escolherFiller, ferramentaLenta, FRASES_ESPERA, podeFalarFiller } from '@/lib/filler';
import {
  aoDelta,
  aoFinal,
  aoReset,
  limparParaFala,
  novoEstadoStream,
  type EstadoStream,
} from '@/lib/streamSpeech';

// ===== VOZ NATURAL DA QUINTA-FEIRA =====
// A fala vem do backend (POST /tts → voz neural feminina pt-BR). Se o backend
// não conseguir sintetizar, caímos na voz do navegador (comportamento antigo).
let currentAudio: HTMLAudioElement | null = null;

// Fala em streaming (frase a frase): fila de frases com o áudio já sendo buscado (prefetch).
// `epocaFala` sobe a cada stopSpeaking(): tudo que estava em fila/andamento deixa de valer.
interface FraseNaFila { texto: string; audio: Promise<Blob | null>; filler?: boolean }
let filaFala: FraseNaFila[] = [];
let epocaFala = 0;
let epocaDrenando: number | null = null;

// ===== ORBE REATIVO (B4) =====
// O nível (RMS) do áudio que está tocando vira a variável CSS --voz (0..1), a ~30 fps e só enquanto
// toca. Sem re-render do React. Se o AudioContext não estiver rodando, NÃO liga o analisador:
// createMediaElementSource desviaria o som para um contexto suspenso e a voz ficaria muda.
let ctxAudio: AudioContext | null = null;
export function nivelDaVoz(rms: number): number {
  return Math.max(0, Math.min(1, rms * 4)); // fala normal tem RMS ~0,05–0,25
}
function medirNivel(audio: HTMLAudioElement): () => void {
  if (typeof window === 'undefined' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return () => {};
  try {
    ctxAudio = ctxAudio ?? new AudioContext();
    if (ctxAudio.state !== 'running') { void ctxAudio.resume(); return () => {}; }
    const fonte = ctxAudio.createMediaElementSource(audio);
    const an = ctxAudio.createAnalyser();
    an.fftSize = 256;
    fonte.connect(an);
    an.connect(ctxAudio.destination);
    const buf = new Uint8Array(an.fftSize);
    let raf = 0;
    let ultimo = 0;
    let suave = 0;
    const raiz = document.documentElement;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      if (t - ultimo < 33) return;
      ultimo = t;
      an.getByteTimeDomainData(buf);
      let soma = 0;
      for (let i = 0; i < buf.length; i++) { const d = (buf[i] - 128) / 128; soma += d * d; }
      suave = suave * 0.6 + nivelDaVoz(Math.sqrt(soma / buf.length)) * 0.4;
      raiz.style.setProperty('--voz', suave.toFixed(3));
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      raiz.style.setProperty('--voz', '0');
      try { fonte.disconnect(); an.disconnect(); } catch { /* já solto */ }
    };
  } catch {
    return () => {};
  }
}

// B11: latência até o 1º áudio da resposta (não conta as frases de espera), reportada ao backend.
let turnoMedido: { requestId: string; t0: number } | null = null;
const primeiroAudioListeners = new Set<(requestId: string, ms: number) => void>();
export function onPrimeiroAudio(fn: (requestId: string, ms: number) => void): () => void {
  primeiroAudioListeners.add(fn);
  return () => { primeiroAudioListeners.delete(fn); };
}
export function iniciarTurnoMedido(requestId: string): void {
  turnoMedido = { requestId, t0: performance.now() };
}

// B5: o que REALMENTE tocou neste turno. Ao ser interrompida, o hook avisa o backend para o
// histórico registrar só isso (com "[interrompido]") em vez da resposta inteira.
let frasesTocadas: string[] = [];
let falaDeResposta = false; // só a fala em streaming da resposta conta (não avisos/notícias)
const interrompidaListeners = new Set<(falado: string) => void>();
export function onFalaInterrompida(fn: (falado: string) => void): () => void {
  interrompidaListeners.add(fn);
  return () => { interrompidaListeners.delete(fn); };
}

// Narração pode ser desligada pelo usuário (persistido entre sessões)
let narrationEnabled = true;
if (typeof window !== 'undefined') {
  narrationEnabled = window.localStorage.getItem('qf_narration') !== 'off';
}

// Observadores de "ela está falando" — o orbe pulsa e o microfone é pausado
// enquanto a narração toca (qualquer narração: chat, avisos, notícias).
const speakingListeners = new Set<(speaking: boolean) => void>();
let isSpeakingNow = false;

function notifySpeaking(speaking: boolean): void {
  if (isSpeakingNow === speaking) return;
  isSpeakingNow = speaking;
  speakingListeners.forEach((fn) => fn(speaking));
}

export function onSpeakingChange(fn: (speaking: boolean) => void): () => void {
  speakingListeners.add(fn);
  return () => { speakingListeners.delete(fn); };
}

export function isNarrationEnabled(): boolean {
  return narrationEnabled;
}

export function setNarrationEnabled(enabled: boolean): void {
  narrationEnabled = enabled;
  if (!enabled) stopSpeaking();
  try { window.localStorage.setItem('qf_narration', enabled ? 'on' : 'off'); } catch { /* storage indisponível */ }
}

export function stopSpeaking(): void {
  // Cortou no meio de uma resposta (algo tocando ou ainda na fila)? Avisa o que de fato foi falado.
  if (falaDeResposta && isSpeakingNow && (currentAudio || filaFala.length > 0)) {
    const falado = frasesTocadas.join(' ');
    interrompidaListeners.forEach((fn) => fn(falado));
  }
  frasesTocadas = [];
  falaDeResposta = false;
  epocaFala += 1; // invalida a fila e qualquer drenagem em andamento
  filaFala = [];
  if (currentAudio) {
    try { currentAudio.pause(); } catch { /* já parado */ }
    currentAudio = null;
  }
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  notifySpeaking(false);
}

function speakBrowser(texto: string): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window) || !texto) return resolve();
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = 'pt-BR';
    u.rate = 1.05;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

/** Espera ela ficar em silêncio (nada tocando, fila vazia, nenhum turno em andamento). Um aviso
 * proativo NUNCA pode cortar a fala dela no meio. Devolve false se desistiu (aviso velho demais). */
async function aguardarSilencio(ocupado: () => boolean, cancelado: () => boolean, maxMs = 120000): Promise<boolean> {
  const inicio = Date.now();
  while (isSpeakingNow || currentAudio || filaFala.length > 0 || ocupado()) {
    if (cancelado() || Date.now() - inicio > maxMs) return false;
    await new Promise((r) => setTimeout(r, 500));
  }
  return true;
}

async function speak(texto: string, httpBase: string): Promise<void> {
  if (!texto || typeof window === 'undefined' || !narrationEnabled) return;
  stopSpeaking();
  notifySpeaking(true);
  try {
    const r = await fetch(`${httpBase}/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: texto }),
    });
    if (!r.ok) throw new Error(`tts ${r.status}`);
    const blob = await r.blob();
    if (!blob.size) throw new Error('tts vazio');
    const url = URL.createObjectURL(blob);
    await new Promise<void>((resolve, reject) => {
      const audio = new Audio(url);
      currentAudio = audio;
      audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
      audio.onerror = () => { URL.revokeObjectURL(url); reject(new Error('playback')); };
      audio.play().catch(reject);
    });
  } catch {
    // Backend sem voz (offline/erro): voz do navegador é melhor que silêncio
    if (narrationEnabled) await speakBrowser(texto);
  } finally {
    notifySpeaking(false);
  }
}

// ===== FALA EM STREAMING =====
// A resposta chega em pedaços. Cada FRASE completa vai para o TTS na hora, e o áudio da próxima
// já é buscado enquanto a atual toca: a voz começa na 1ª frase, sem esperar o texto inteiro.

async function buscarTts(texto: string, httpBase: string): Promise<Blob | null> {
  try {
    const r = await fetch(`${httpBase}/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: texto }),
    });
    if (!r.ok) return null;
    const blob = await r.blob();
    return blob.size ? blob : null;
  } catch {
    return null; // sem TTS no backend: cai na voz do navegador
  }
}

async function drenarFala(): Promise<void> {
  const minhaEpoca = epocaFala;
  epocaDrenando = minhaEpoca;
  notifySpeaking(true);
  try {
    while (filaFala.length && minhaEpoca === epocaFala) {
      const item = filaFala.shift()!;
      const blob = await item.audio;
      if (minhaEpoca !== epocaFala) break;
      if (blob) {
        const url = URL.createObjectURL(blob);
        try {
          await new Promise<void>((resolve, reject) => {
            const audio = new Audio(url);
            currentAudio = audio;
            if (turnoMedido && !item.filler) {
              const ms = Math.round(performance.now() - turnoMedido.t0);
              const id = turnoMedido.requestId;
              turnoMedido = null;
              primeiroAudioListeners.forEach((fn) => fn(id, ms));
            }
            audio.onended = () => { if (minhaEpoca === epocaFala && !item.filler) frasesTocadas.push(item.texto); resolve(); };
            const soltarNivel = medirNivel(audio);
            const fim = () => soltarNivel();
            audio.addEventListener('ended', fim);
            audio.addEventListener('pause', fim);
            audio.onpause = () => resolve(); // stopSpeaking() pausa: não deixa a promessa pendurada
            audio.onerror = () => reject(new Error('playback'));
            audio.play().catch(reject);
          });
        } catch {
          if (narrationEnabled && minhaEpoca === epocaFala) await speakBrowser(item.texto);
        } finally {
          URL.revokeObjectURL(url);
        }
      } else if (narrationEnabled) {
        await speakBrowser(item.texto);
      }
    }
  } finally {
    if (epocaDrenando === minhaEpoca) epocaDrenando = null;
    if (minhaEpoca === epocaFala) notifySpeaking(false); // interrompida: o stopSpeaking() já avisou
  }
}

// ===== FRASES DE ESPERA (A3) =====
const fillersProntos = new Map<string, Promise<Blob | null>>();
let ultimoFiller: string | null = null;
let fillerUsadoNoTurno = false;

/** Busca (uma vez) o áudio das frases de espera; a partir daí tocam sem esperar o TTS. */
export function prepararFillers(httpBase: string): void {
  if (typeof window === 'undefined') return;
  FRASES_ESPERA.forEach((f) => {
    const antigo = fillersProntos.get(f);
    if (!antigo) fillersProntos.set(f, buscarTts(f, httpBase).then((b) => { if (!b) fillersProntos.delete(f); return b; }));
  });
}

export function novoTurnoDeFala(): void {
  fillerUsadoNoTurno = false;
}

/** Ferramenta lenta começou e ela ainda não falou nada: cobre o silêncio com uma frase curta. */
export function falarFiller(ferramenta: string, httpBase: string): void {
  if (!ferramentaLenta(ferramenta)) return;
  if (!podeFalarFiller({
    falando: isSpeakingNow, filaVazia: filaFala.length === 0,
    jaUsouNoTurno: fillerUsadoNoTurno, narracao: narrationEnabled,
  }) || typeof window === 'undefined') return;
  fillerUsadoNoTurno = true;
  const texto = escolherFiller(ultimoFiller);
  ultimoFiller = texto;
  filaFala.push({ texto, audio: fillersProntos.get(texto) ?? buscarTts(texto, httpBase), filler: true });
  if (epocaDrenando !== epocaFala) void drenarFala();
}

/** Põe uma frase na fila de fala (o áudio começa a ser buscado imediatamente). */
export function enfileirarFala(frase: string, httpBase: string): void {
  const texto = limparParaFala(frase);
  if (!texto || typeof window === 'undefined' || !narrationEnabled) return;
  if (epocaDrenando !== epocaFala && filaFala.length === 0) frasesTocadas = []; // resposta nova
  falaDeResposta = true;
  filaFala.push({ texto, audio: buscarTts(texto, httpBase) });
  if (epocaDrenando !== epocaFala) void drenarFala();
}

interface UseQuintaFeira {
  isConnected: boolean;
  connectionStatus: ConnectionStatus;
  messages: ChatMessage[];
  intermediateStatus: IntermediateStatus | null;
  lastAiResponse: string | null;
  error: string | null;
  isLoading: boolean;
  activeMedia: ActiveMedia | null;
  clearMedia: () => void;
  activeVisor: VisorContent | null;
  clearVisor: () => void;
  activeHolo: HoloPayload | null;
  clearHolo: () => void;
  narrationIndex: number | null;
  proactiveAlert: string | null;
  approvals: ApprovalRequest[];
  respondApproval: (approvalId: string, permitido: boolean) => void;
  activity: AgoraActivity | null;
  streamingText: string | null;
  stopRun: () => void;
  sendMessage: (text: string, mode?: 'streaming' | 'deliberative' | 'interactive') => Promise<void>;
  ambientSpeech: (text: string) => Promise<boolean>;
  loadNews: () => Promise<void>;
  ping: () => Promise<void>;
  disconnect: () => void;
}

interface Config {
  wsUrl?: string;
  autoReconnect?: boolean;
  maxReconnectAttempts?: number;
  baseReconnectDelay?: number; // ms
  maxReconnectDelay?: number; // ms
}

/**
 * Hook principal para comunicação com Brain via WebSocket
 *
 * Uso:
 * const { isConnected, messages, sendMessage } = useQuintaFeira();
 *
 * Exemplo:
 * await sendMessage('Qual é seu nome?', 'streaming');
 */
export function useQuintaFeira({
  wsUrl = 'ws://127.0.0.1:8000/ws/quinta',
  autoReconnect = true,
  maxReconnectAttempts = 5,
  baseReconnectDelay = 1000,
  maxReconnectDelay = 30000,
}: Config = {}): UseQuintaFeira {
  // ===== ESTADOS =====
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [intermediateStatus, setIntermediateStatus] = useState<IntermediateStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const turnoAtivoRef = useRef(false);
  useEffect(() => { turnoAtivoRef.current = isLoading; }, [isLoading]);
  const [lastAiResponse, setLastAiResponse] = useState<string | null>(null);
  const [activeMedia, setActiveMedia] = useState<ActiveMedia | null>(null);
  const [activeVisor, setActiveVisor] = useState<VisorContent | null>(null);
  // Holograma (globo + painéis). SEPARADO do visor: o efeito de narração de notícias depende de
  // activeVisor e abrir um holograma não pode cancelar a fala.
  const [activeHolo, setActiveHolo] = useState<HoloPayload | null>(null);
  const [narrationIndex, setNarrationIndex] = useState<number | null>(null);
  const [proactiveAlert, setProactiveAlert] = useState<string | null>(null);
  // Ações críticas esperando a sua aprovação (o backend espera e NEGA se expirar)
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  // Ferramenta em uso agora ("pesquisando na web…"): alimenta a faixa "Agora"
  const [activity, setActivity] = useState<AgoraActivity | null>(null);
  // Resposta chegando em pedaços (streaming): aparece no chat enquanto o modelo ainda escreve
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const streamRef = useRef<EstadoStream>(novoEstadoStream());

  const clearMedia = useCallback(() => setActiveMedia(null), []);
  const clearVisor = useCallback(() => setActiveVisor(null), []);
  const clearHolo = useCallback(() => setActiveHolo(null), []);

  // ===== REFS (não causam re-render) =====
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isConnectingRef = useRef(false); // Previne múltiplas tentativas simultâneas
  const messageQueueRef = useRef<OutgoingMessageEnvelope[]>([]);
  const cleanupRef = useRef(false); // Flag para cleanup no unmount

  // ===== EXPONENTIAL BACKOFF =====
  /**
   * Calcula delay com exponential backoff:
   * delay = min(baseDelay * (2 ^ attemptNumber), maxDelay)
   *
   * Exemplo (base=1000, max=30000):
   * - Tentativa 0: 1000ms
   * - Tentativa 1: 2000ms
   * - Tentativa 2: 4000ms
   * - Tentativa 3: 8000ms
   * - Tentativa 4: 16000ms
   * - Tentativa 5+: 30000ms (máximo)
   */
  const getReconnectDelay = useCallback((attempt: number): number => {
    const exponentialDelay = baseReconnectDelay * Math.pow(2, attempt);
    return Math.min(exponentialDelay, maxReconnectDelay);
  }, [baseReconnectDelay, maxReconnectDelay]);

  // ===== GERAR UUID PARA REQUEST_ID =====
  const generateUUID = useCallback((): string => {
    return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  // ===== CRIAR MESSAGE ENVELOPE =====
  const createMessageEnvelope = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- payload de protocolo de forma variável; validado onde é usado
    <T extends Record<string, any>>(type: MessageType, payload: T): MessageEnvelope<T> => ({
      type,
      payload,
      timestamp: new Date().toISOString(),
      request_id: generateUUID(),
    }),
    [generateUUID]
  );

  // ===== CONECTAR WEBSOCKET =====
  const connectRef = useRef<() => void>(() => undefined);
  const connect = useCallback(() => {
    if (cleanupRef.current) {
      console.log('[WS] Cleanup está em progresso, abortando conexão');
      return;
    }

    if (isConnectingRef.current) {
      console.log('[WS] Já conectando, ignorando tentativa duplicada');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WS] WebSocket já está OPEN');
      return;
    }

    try {
      isConnectingRef.current = true;
      setConnectionStatus('connecting');
      console.log(`[WS] Conectando em: ${wsUrl}`);

      // Token de sessão no subprotocolo (não na URL): o backend, em modo 'exigir', fecha quem não o trouxer.
      const ws = new WebSocket(wsUrl, protocolosDoToken());

      // ===== ON OPEN =====
      // B5: cortada no meio da fala -> o backend registra só o que foi dito
      const soltarInterrompida = onFalaInterrompida((falado) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify(createMessageEnvelope('spoken_report', { falado })));
        }
      });
      const soltarPrimeiroAudio = onPrimeiroAudio((requestId, ms) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify(createMessageEnvelope('voice_trace', { request_id: requestId, primeiro_audio_ms: ms })));
        }
      });
      ws.addEventListener('close', () => { soltarInterrompida(); soltarPrimeiroAudio(); });

      ws.onopen = () => {
        console.log('[WS] ✓ Conectado ao backend');
        wsRef.current = ws;
        prepararFillers(wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, ''));
        isConnectingRef.current = false;
        setIsConnected(true);
        setConnectionStatus('connected');
        setError(null);
        reconnectCountRef.current = 0;

        // Enviar mensagens enfileiradas
        while (messageQueueRef.current.length > 0 && ws.readyState === WebSocket.OPEN) {
          const queued = messageQueueRef.current.shift();
          if (queued) {
            ws.send(JSON.stringify(queued));
            console.log('[WS] Mensagem enfileirada enviada');
          }
        }
      };

      // ===== ON MESSAGE =====
      ws.onmessage = (event: MessageEvent) => {
        try {
          const envelope = JSON.parse(event.data) as IncomingMessageEnvelope;
          console.log('[WS] Mensagem recebida:', envelope.type);

          // Despachar por tipo de mensagem
          switch (envelope.type) {
            case 'intermediate_status': {
              // Status intermediário durante processamento
              const status = envelope as MessageEnvelope<IntermediateStatus>;
              setIntermediateStatus(status.payload);
              console.log(`[WS] Status: ${status.payload.step} (${(status.payload.progress * 100).toFixed(0)}%)`);
              break;
            }

            case 'brain_response': {
              // Resposta final do Brain
              // eslint-disable-next-line @typescript-eslint/no-explicit-any -- payload de protocolo de forma variável; validado onde é usado
              const response = envelope as any;
              const texto: string = response.payload.text || '';
              const msg: ChatMessage = {
                id: `assistant_${Date.now()}`,
                role: 'assistant',
                content: texto,
                timestamp: Date.now(),
                tools_used: response.payload.tools_used,
                execution_time_ms: response.payload.execution_time_ms,
              };
              setMessages(prev => [...prev, msg]);
              setIntermediateStatus(null);
              setActivity(null);
              setIsLoading(false);

              // Fala a resposta em voz alta com a VOZ DELA (TTS neural do backend).
              // Limita a 300 chars pra não virar monólogo.
              // Fala só o que AINDA não foi falado durante o streaming (frase a frase); se o texto
              // final diferiu do que foi falado, recomeça. Sem streaming, fala tudo.
              if (texto) {
                const httpBase = wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '');
                const { pararAntes, frases } = aoFinal(streamRef.current, texto);
                if (pararAntes) stopSpeaking();
                frases.forEach((f) => enfileirarFala(f, httpBase));
              }
              streamRef.current = novoEstadoStream();
              setStreamingText(null);

              // Visor visual: abre conteúdo na página junto com a resposta
              const visor = response.payload?.visor;
              if (visor && typeof visor === 'object') {
                setActiveVisor(visor as VisorContent);
              }

              console.log('[WS] Resposta recebida:', msg.content.substring(0, 50) + '...');
              break;
            }

            case 'error': {
              // Erro do backend
              const errorEnv = envelope as MessageEnvelope<{ error_code: string; message: string }>;
              const errorMsg = errorEnv.payload.message;
              setError(errorMsg);
              setIsLoading(false);
              setIntermediateStatus(null);
              setActivity(null);
              streamRef.current = novoEstadoStream();
              setStreamingText(null);
              console.error('[WS] Erro recebido:', errorMsg);
              break;
            }

            case 'pong': {
              // Resposta a ping (keep-alive)
              console.log('[WS] Pong recebido (keep-alive OK)');
              break;
            }

            case 'approval_requested': {
              // A Quinta quer fazer algo CRÍTICO (enviar WhatsApp, terminal, apagar arquivo...)
              // e está ESPERANDO a sua decisão. Sem resposta no prazo, o backend nega.
              const p = (envelope as MessageEnvelope<ApprovalRequestedPayload>).payload ?? {};
              if (!p.approval_id) break;
              const pedido: ApprovalRequest = {
                approval_id: String(p.approval_id),
                ferramenta: String(p.ferramenta ?? ''),
                risco: p.risco ?? 'critica',
                resumo: String(p.resumo ?? ''),
                origem: String(p.origem ?? ''),
                expira_em_s: Number(p.expira_em_s ?? 60),
                recebido_em: Date.now(),
                contaminado: Boolean(p.contaminado),
                fontes: Array.isArray(p.fontes) ? p.fontes.map(String) : [],

              };
              setApprovals(prev =>
                prev.some(a => a.approval_id === pedido.approval_id) ? prev : [...prev, pedido],
              );
              // Chama a atenção sem ler o conteúdo em voz alta (pode ser longo/privado)
              const httpBase = wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '');
              void speak('Preciso da sua aprovação na tela.', httpBase);
              break;
            }

            case 'approval_resolved': {
              // Respondido em outra aba, ou expirou: fecha o cartão
              const id = String((envelope as MessageEnvelope<ApprovalResolvedPayload>).payload?.approval_id ?? '');
              setApprovals(prev => prev.filter(a => a.approval_id !== id));
              break;
            }

            case 'text_delta': {
              // Pedaço da resposta: aparece no chat na hora, e cada frase que fecha vai pra voz.
              const delta = String((envelope as MessageEnvelope<TextDeltaPayload>).payload?.text ?? '');
              if (!delta) break;
              const httpBase = wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '');
              aoDelta(streamRef.current, delta).forEach((f) => enfileirarFala(f, httpBase));
              setStreamingText(streamRef.current.buf);
              break;
            }

            case 'text_reset': {
              // O que foi mostrado era só um preâmbulo antes de uma ferramenta (ou o streaming
              // recomeçou): limpa o balão. A fala já enfileirada segue ("deixa eu ver…").
              aoReset(streamRef.current);
              setStreamingText(null);
              break;
            }

            case 'holo_show': {
              // Payload de terceiros (OSM/Wikipedia): revalida; se for inválido, ignora sem quebrar.
              const holo = parseHoloPayload((envelope as unknown as MessageEnvelope).payload);
              if (holo) setActiveHolo(holo);
              break;
            }

            case 'holo_hide': {
              setActiveHolo(null);
              break;
            }

            case 'tool_call_start': {
              // A Quinta começou a usar uma ferramenta: a faixa "Agora" mostra o quê.
              const p = (envelope as MessageEnvelope<ToolCallPayload>).payload ?? {};
              falarFiller(String(p.tool ?? ''), wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, ''));
              setActivity({
                tool: String(p.tool ?? ''),
                label: String(p.label ?? 'trabalhando'),
                since: Date.now(),
              });
              break;
            }

            case 'tool_call_result': {
              // Terminou a ferramenta; entre uma e outra ela volta a "pensar" (isLoading).
              const tool = String((envelope as MessageEnvelope<ToolCallPayload>).payload?.tool ?? '');
              setActivity(prev => (prev && prev.tool === tool ? null : prev));
              break;
            }

            case 'run_cancelled': {
              // O backend confirmou o PARAR: limpa o estado de "trabalhando" e avisa no chat.
              const descartadas = Number((envelope as MessageEnvelope<RunCancelledPayload>).payload?.descartadas ?? 0);
              setIsLoading(false);
              setIntermediateStatus(null);
              setActivity(null);
              stopSpeaking();
              streamRef.current = novoEstadoStream();
              setStreamingText(null);
              setMessages(prev => [
                ...prev,
                {
                  id: `assistant_${Date.now()}`,
                  role: 'assistant',
                  content: descartadas > 0
                    ? `Parei. Descartei também ${descartadas} ${descartadas === 1 ? 'mensagem que estava' : 'mensagens que estavam'} na fila.`
                    : 'Parei.',
                  timestamp: Date.now(),
                },
              ]);
              break;
            }

            case 'runtime_event': {
              // Gateway pode entregar `event_type`/`data` no root OU dentro de `payload`.
              // eslint-disable-next-line @typescript-eslint/no-explicit-any -- payload de protocolo de forma variável; validado onde é usado
              const anyEnv = envelope as any;
              const event_type: string =
                anyEnv.event_type ?? anyEnv.payload?.event_type ?? '';
              // eslint-disable-next-line @typescript-eslint/no-explicit-any -- payload de protocolo de forma variável; validado onde é usado
              const data: Record<string, any> =
                anyEnv.data ?? anyEnv.payload?.data ?? anyEnv.payload ?? {};

              if (event_type === 'manual_command_completed') {
                setLastAiResponse(data.response ?? null);
              } else if (event_type === 'action_failed') {
                setLastAiResponse(data.reason ?? null);
              } else if (event_type === 'media_playback_requested') {
                // Backend delega reprodução para o cliente.
                setActiveMedia({
                  provider: data.provider ?? 'youtube',
                  video_id: data.video_id,
                  video_url: data.video_url,
                  search_query: data.search_query,
                  audio_base64: data.audio_base64,
                  autoplay: data.autoplay !== false,
                  title: data.title ?? data.search_query,
                });
              } else if (event_type === 'media_playback_stopped') {
                setActiveMedia(null);
              }
              break;
            }

            default: {
              console.warn('[WS] Tipo de mensagem desconhecido:', envelope.type);
            }
          }
        } catch (err) {
          console.error('[WS] Erro ao parsear mensagem:', err);
          setError('Erro ao processar resposta do servidor');
        }
      };

      // ===== ON ERROR =====
      ws.onerror = () => {
        console.warn(`[WS] Falha ao conectar em: ${wsUrl} — aguardando reconexão`);
        isConnectingRef.current = false;
        setConnectionStatus('error');
        setError('Erro na conexão WebSocket');
      };

      // ===== ON CLOSE =====
      ws.onclose = () => {
        console.log('[WS] Desconectado do backend');
        // Cartões de aprovação ficam obsoletos: o backend reenvia os pedidos ainda abertos ao reconectar
        setApprovals([]);
        setActivity(null);
        streamRef.current = novoEstadoStream();
        setStreamingText(null);
        wsRef.current = null;
        isConnectingRef.current = false;
        setIsConnected(false);
        setConnectionStatus('disconnected');

        if (!cleanupRef.current && autoReconnect && reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          const delay = getReconnectDelay(reconnectCountRef.current - 1);
          console.log(
            `[WS] Reconectando em ${delay}ms (tentativa ${reconnectCountRef.current}/${maxReconnectAttempts})`
          );

          // Agendaar reconexão
          reconnectTimerRef.current = setTimeout(() => {
            if (!cleanupRef.current) {
              // o backend pode ter reiniciado (token novo): busca de novo antes de reconectar
              void obterToken(true).then(() => { if (!cleanupRef.current) connectRef.current(); });
            }
          }, delay);
        } else if (reconnectCountRef.current >= maxReconnectAttempts) {
          console.error(`[WS] Falha após ${maxReconnectAttempts} tentativas`);
          setError('Não foi possível conectar ao backend');
        }
      };
    } catch (err) {
      console.error('[WS] Erro ao conectar:', err);
      isConnectingRef.current = false;
      setConnectionStatus('error');
      setError('Erro ao conectar ao WebSocket');
    }
  }, [wsUrl, autoReconnect, maxReconnectAttempts, getReconnectDelay]);
  useEffect(() => { connectRef.current = connect; }, [connect]);

  // ===== DESCONECTAR =====
  const disconnect = useCallback(() => {
    console.log('[WS] Desconectando manualmente...');

    // Lipar timers
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    // Fechar WebSocket
    if (wsRef.current) {
      wsRef.current.close(1000, 'Desconexão manual');
      wsRef.current = null;
    }

    isConnectingRef.current = false;
    setIsConnected(false);
    setConnectionStatus('disconnected');
  }, []);

  // ===== ENVIAR MENSAGEM =====
  const sendMessage = useCallback(
    async (text: string, mode: 'streaming' | 'deliberative' | 'interactive' = 'streaming'): Promise<void> => {
      if (!text.trim()) {
        console.warn('[WS] Texto vazio, ignorando');
        return;
      }

      novoTurnoDeFala();

      // Adicionar ao histórico (lado do usuário)
      const userMsg: ChatMessage = {
        id: `user_${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, userMsg]);

      // Criar Message Envelope
      const payload: UserMessagePayload = {
        text,
        mode,
      };
      const envelope = createMessageEnvelope('user_message', payload);
      iniciarTurnoMedido(envelope.request_id);

      // Enviar (ou enfileirar se desconectado)
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify(envelope));
          setIsLoading(true);
          streamRef.current = novoEstadoStream(); // nova resposta: texto e orçamento de fala zerados
          setStreamingText(null);
          console.log('[WS] Mensagem enviada:', text.substring(0, 50) + '...');
        } catch (err) {
          console.error('[WS] Erro ao enviar:', err);
          setError('Erro ao enviar mensagem');
          // Remover mensagem do histórico se falhar
          setMessages(prev => prev.filter(m => m.id !== userMsg.id));
        }
      } else {
        console.log('[WS] WebSocket não está conectado, enfileirando...');
        messageQueueRef.current.push(envelope);
        setError('Desconectado. Mensagem será enviada ao reconectar.');
      }
    },
    [createMessageEnvelope]
  );

  // ===== ESCUTA AMBIENTE: "isso foi comigo?" =====
  // Manda a fala captada pro backend decidir (como uma pessoa) se foi dirigida
  // a ela. Só vira conversa/voz SE o backend disser que sim — senão, silêncio.
  const ambientSpeech = useCallback(async (text: string): Promise<boolean> => {
    const t = (text || '').trim();
    if (!t) return false;
    const httpBase = wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '');
    try {
      const r = await fetch(`${httpBase}/ambient`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: t }),
      });
      const d = await r.json();
      if (!d?.responder || !d?.text) return false;

      // Era com ela: registra o turno e responde com a voz dela
      const userMsg: ChatMessage = {
        id: `amb_user_${Date.now()}`, role: 'user', content: t, timestamp: Date.now(),
      };
      const aiMsg: ChatMessage = {
        id: `amb_ai_${Date.now()}`, role: 'assistant', content: d.text, timestamp: Date.now(),
      };
      setMessages(prev => [...prev, userMsg, aiMsg]);
      if (isNarrationEnabled()) void speak(String(d.text).slice(0, 300), httpBase);
      if (d.visor && typeof d.visor === 'object') setActiveVisor(d.visor as VisorContent);
      return true;
    } catch {
      return false; // backend fora / sem rede: ignora silenciosamente
    }
  }, [wsUrl]);

  // ===== RESPONDER A UM PEDIDO DE APROVAÇÃO =====
  // Some o cartão na hora; o backend destrava a ferramenta (ou nega) ao receber.
  const respondApproval = useCallback(
    (approvalId: string, permitido: boolean): void => {
      setApprovals(prev => prev.filter(a => a.approval_id !== approvalId));
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        const envelope = createMessageEnvelope('approval_response', {
          approval_id: approvalId,
          permitido,
        });
        wsRef.current.send(JSON.stringify(envelope));
      } else {
        console.warn('[WS] Sem conexão para responder à aprovação; o backend vai negar por tempo.');
      }
    },
    [createMessageEnvelope],
  );

  // ===== PARAR (Esc / botão) =====
  // Manda o backend cancelar a execução atual e descartar a fila. Corta a voz na hora;
  // o resto do estado limpa quando o backend confirma com `run_cancelled`.
  const stopRun = useCallback((): void => {
    stopSpeaking();
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(createMessageEnvelope('stop', {})));
    } else {
      // Sem conexão não há o que cancelar no servidor: só destrava a tela.
      setIsLoading(false);
      setActivity(null);
    }
  }, [createMessageEnvelope]);

  // ===== PING (Keep-Alive) =====
  const ping = useCallback(async (): Promise<void> => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn('[WS] WebSocket não está conectado');
      return;
    }

    const envelope = createMessageEnvelope('ping', {});
    wsRef.current.send(JSON.stringify(envelope));
    console.log('[WS] Ping enviado');
  }, [createMessageEnvelope]);

  // ===== EFEITO: AVISOS PROATIVOS (polling + narração) =====
  // O monitor do backend enfileira avisos (bateria, CPU, clima, pausa). Buscamos
  // a cada 45s; ela fala em voz alta e mostramos um toast breve.
  useEffect(() => {
    const httpBase = wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '');
    let stop = false;

    const poll = async () => {
      try {
        const r = await fetch(`${httpBase}/proactive`);
        const d = await r.json();
        if (stop || !d?.alerts?.length) return;
        for (const a of d.alerts) {
          const texto = a?.texto || '';
          if (!texto) continue;
          // Espera ela terminar de falar/responder: aviso não interrompe conversa em andamento.
          if (!(await aguardarSilencio(() => turnoAtivoRef.current, () => stop))) continue;
          setProactiveAlert(texto);
          // Narra em sequência com a voz dela (um aviso por vez)
          await speak(texto, httpBase);
        }
        window.setTimeout(() => { if (!stop) setProactiveAlert(null); }, 10000);
      } catch {
        /* sem rede / backend fora: ignora */
      }
    };

    const id = window.setInterval(poll, 45000);
    return () => { stop = true; window.clearInterval(id); };
  }, [wsUrl]);

  // ===== EFEITO: NARRAR NOTÍCIAS EM SINCRONIA COM O CARD =====
  // A voz DELA (TTS neural do backend) fala cada manchete e o card troca no fim
  // de cada fala, garantindo que a notícia falada SEMPRE corresponde à exibida.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!activeVisor || activeVisor.tipo !== 'noticia') { setNarrationIndex(null); return; }

    const items = activeVisor.items && activeVisor.items.length
      ? activeVisor.items
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- payload de protocolo de forma variável; validado onde é usado
      : [activeVisor as any];
    if (!items.length) return;

    const httpBase = wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '');
    let cancelled = false;
    stopSpeaking();

    const hora = new Date().getHours();
    const saud = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';

    const falar = async (texto: string, idx: number | null) => {
      if (cancelled || !texto) return;
      if (idx !== null) setNarrationIndex(idx);
      await speak(texto, httpBase);
    };

    (async () => {
      await falar(`${saud}, Matheus. Aqui está o que importa hoje.`, 0);
      for (let i = 0; i < items.length && !cancelled; i++) {
        // Fala a versão DELA (entendeu e resumiu); cai pro título se não houver.
        await falar(items[i].fala || items[i].titulo || '', i);
      }
      // Opinião/leitura final dela sobre o conjunto (mostra a 1ª notícia ao comentar)
      if (activeVisor.comentario) {
        await falar(activeVisor.comentario, 0);
      }
      if (!cancelled) setNarrationIndex(null); // libera auto-rotação ao terminar
    })();

    return () => {
      cancelled = true;
      stopSpeaking();
      setNarrationIndex(null);
    };
  }, [activeVisor, wsUrl]);

  // ===== BUSCAR NOTÍCIAS (boot + sob demanda pelo botão do deck) =====
  const loadNews = useCallback(async (): Promise<void> => {
    const httpBase = wsUrl.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '');
    try {
      const r = await fetch(`${httpBase}/news?limit=8`);
      const d = await r.json();
      if (d?.items?.length) {
        setActiveVisor({ tipo: 'noticia', items: d.items, comentario: d.comentario });
      }
    } catch { /* sem notícias agora, sem problema */ }
  }, [wsUrl]);

  // ===== EFEITO: BUSCAR NOTÍCIAS NA INICIALIZAÇÃO (carrossel ao ligar) =====
  useEffect(() => {
    void loadNews();
  }, [loadNews]);

  // ===== EFEITO: CONECTAR AO MONTAR =====
  useEffect(() => {
    cleanupRef.current = false;
    void obterToken(true).then(() => { if (!cleanupRef.current) connect(); });

    // ===== CLEANUP NO UNMOUNT =====
    return () => {
      console.log('[WS] Cleanup: desmontando componente');
      cleanupRef.current = true;

      // Cancelar reconexões pendentes
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      // Fechar WebSocket
      if (wsRef.current) {
        wsRef.current.close(1000, 'Componente desmontado');
        wsRef.current = null;
      }

      isConnectingRef.current = false;
    };
  }, []); // Dependências VAZIAS - roda apenas uma vez

  return {
    isConnected,
    connectionStatus,
    messages,
    intermediateStatus,
    lastAiResponse,
    error,
    isLoading,
    activeMedia,
    clearMedia,
    activeVisor,
    clearVisor,
    activeHolo,
    clearHolo,
    narrationIndex,
    proactiveAlert,
    approvals,
    respondApproval,
    activity,
    streamingText,
    stopRun,
    sendMessage,
    ambientSpeech,
    loadNews,
    ping,
    disconnect,
  };
}

