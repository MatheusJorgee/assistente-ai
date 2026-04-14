"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type RuntimeEnvelope = {
  type: string;
  event?: {
    type?: string;
    source?: string;
    timestamp?: string;
    event_id?: string;
    payload?: Record<string, unknown>;
  };
  [key: string]: unknown;
};

type TerminalLog = {
  id: string;
  timestamp: string;
  kind: string;
  source: string;
  text: string;
};

const MAX_LOGS = 50;
const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 15000;

type FilterMode = "all" | "actions" | "audit";

function toSafeString(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function mapEventToLine(message: RuntimeEnvelope): TerminalLog | null {
  if (message.type !== "runtime_event" || !message.event) {
    return null;
  }

  const eventType = message.event.type || "unknown";

  const payload = message.event.payload ?? {};
  const source = message.event.source || "runtime";
  const timestamp = message.event.timestamp || new Date().toISOString();
  const id = message.event.event_id || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  let text = "";
  if (eventType === "autonomous_decision") {
    text = `decision=${toSafeString((payload as Record<string, unknown>).decision ?? payload)}`;
  } else if (eventType === "manual_command_completed") {
    text = `manual_command=${toSafeString((payload as Record<string, unknown>).command)} response=${toSafeString((payload as Record<string, unknown>).response)}`;
  } else if (eventType === "manual_command_failed") {
    text = `manual_command=${toSafeString((payload as Record<string, unknown>).command)} error=${toSafeString((payload as Record<string, unknown>).error)}`;
  } else if (eventType === "action_completed" || eventType === "action_failed") {
    text = toSafeString(payload);
  } else {
    const toolName = toSafeString((payload as Record<string, unknown>).tool_name ?? "unknown_tool");
    const success = toSafeString((payload as Record<string, unknown>).success ?? "?");
    const duration = toSafeString((payload as Record<string, unknown>).duration_ms ?? "?");
    const msg = toSafeString((payload as Record<string, unknown>).message ?? "");
    text = `tool=${toolName} success=${success} duration_ms=${duration}${msg ? ` message=${msg}` : ""}`;
  }

  return {
    id,
    timestamp,
    kind: eventType,
    source,
    text,
  };
}

function isActionKind(kind: string): boolean {
  return kind === "autonomous_decision" || kind === "action_completed" || kind === "action_failed" || kind.startsWith("manual_command");
}

export default function TerminalPage() {
  const [status, setStatus] = useState<"connecting" | "reconnecting" | "online" | "offline">("connecting");
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [logs, setLogs] = useState<TerminalLog[]>([]);
  const [commandText, setCommandText] = useState("");
  const [eventsPerMinute, setEventsPerMinute] = useState(0);
  const [autonomousPaused, setAutonomousPaused] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const eventTimesRef = useRef<number[]>([]);
  const isUnmountingRef = useRef(false);

  const wsUrl = useMemo(() => {
    const fromEnv = process.env.NEXT_PUBLIC_RUNTIME_WS_URL?.trim();
    if (fromEnv) {
      return fromEnv.startsWith("ws://") || fromEnv.startsWith("wss://")
        ? fromEnv
        : `ws://${fromEnv}`;
    }
    return "ws://localhost:8000/runtime/events/ws";
  }, []);

  const filteredLogs = useMemo(() => {
    if (filterMode === "all") return logs;
    if (filterMode === "audit") return logs.filter((log) => log.kind === "audit_event");
    return logs.filter((log) => isActionKind(log.kind));
  }, [logs, filterMode]);

  useEffect(() => {
    isUnmountingRef.current = false;

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const scheduleReconnect = () => {
      if (isUnmountingRef.current) return;

      attemptRef.current += 1;
      const capped = Math.min(BACKOFF_BASE_MS * 2 ** attemptRef.current, BACKOFF_MAX_MS);
      const delay = Math.floor(Math.random() * capped);

      setStatus("reconnecting");
      clearReconnectTimer();
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, delay);
    };

    const connect = () => {
      if (isUnmountingRef.current) return;
      setStatus(attemptRef.current > 0 ? "reconnecting" : "connecting");

      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        if (isUnmountingRef.current) return;
        attemptRef.current = 0;
        setStatus("online");
        socket.send("ping");
      };

      socket.onmessage = (evt) => {
        if (isUnmountingRef.current) return;
        try {
          const parsed = JSON.parse(evt.data) as RuntimeEnvelope;

          if (parsed.type === "connection") {
            setAutonomousPaused(Boolean(parsed.autonomous_paused));
            return;
          }

          if (parsed.type === "autonomous_control_ack") {
            setAutonomousPaused(Boolean(parsed.paused));
            return;
          }

          if (parsed.type === "command_result") {
            const nowIso = new Date().toISOString();
            const log: TerminalLog = {
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              timestamp: nowIso,
              kind: "manual_command_completed",
              source: "frontend_terminal",
              text: `manual_command=${toSafeString(parsed.command)} response=${toSafeString(parsed.response)}`,
            };
            setLogs((prev) => [...prev, log].slice(-MAX_LOGS));
            return;
          }

          const line = mapEventToLine(parsed);
          if (!line) return;

          eventTimesRef.current.push(Date.now());
          setLogs((prev) => {
            const next = [...prev, line];
            return next.slice(-MAX_LOGS);
          });
        } catch {
          // Mantém terminal resiliente mesmo com payload inválido.
        }
      };

      socket.onerror = () => {
        if (isUnmountingRef.current) return;
        socket.close();
      };

      socket.onclose = () => {
        if (isUnmountingRef.current) return;
        setStatus("offline");
        scheduleReconnect();
      };
    };

    connect();

    const throughputTimer = setInterval(() => {
      const cutoff = Date.now() - 60_000;
      eventTimesRef.current = eventTimesRef.current.filter((t) => t >= cutoff);
      setEventsPerMinute(eventTimesRef.current.length);
    }, 1000);

    return () => {
      isUnmountingRef.current = true;
      clearReconnectTimer();
      clearInterval(throughputTimer);
      setStatus("offline");
      if (wsRef.current) {
        wsRef.current.close(1000, "component_unmount");
        wsRef.current = null;
      }
    };
  }, [wsUrl]);

  const sendManualCommand = () => {
    const command = commandText.trim();
    if (!command || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    wsRef.current.send(
      JSON.stringify({
        type: "manual_command",
        command,
      })
    );

    const localLine: TerminalLog = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      kind: "manual_command_requested",
      source: "operator",
      text: `manual_command=${command}`,
    };
    setLogs((prev) => [...prev, localLine].slice(-MAX_LOGS));
    setCommandText("");
  };

  const toggleAutonomous = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    wsRef.current.send(
      JSON.stringify({
        type: "autonomous_control",
        paused: !autonomousPaused,
      })
    );
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-4 flex flex-col gap-3 border-b border-emerald-400/30 pb-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-emerald-300">Quinta-Feira Observability</p>
            <h1 className="font-mono text-2xl font-bold text-emerald-200">Terminal Seguro</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setFilterMode("all")}
              className={`rounded border px-2 py-1 font-mono text-xs ${filterMode === "all" ? "border-emerald-400 text-emerald-300" : "border-slate-700 text-slate-300"}`}
            >
              Mostrar Tudo
            </button>
            <button
              onClick={() => setFilterMode("actions")}
              className={`rounded border px-2 py-1 font-mono text-xs ${filterMode === "actions" ? "border-emerald-400 text-emerald-300" : "border-slate-700 text-slate-300"}`}
            >
              Apenas Ações
            </button>
            <button
              onClick={() => setFilterMode("audit")}
              className={`rounded border px-2 py-1 font-mono text-xs ${filterMode === "audit" ? "border-emerald-400 text-emerald-300" : "border-slate-700 text-slate-300"}`}
            >
              Apenas Auditoria
            </button>
            <button
              onClick={toggleAutonomous}
              className={`rounded border px-2 py-1 font-mono text-xs ${autonomousPaused ? "border-amber-400 text-amber-300" : "border-cyan-400 text-cyan-300"}`}
            >
              {autonomousPaused ? "Retomar Loop Autônomo" : "Pausar Loop Autônomo"}
            </button>
            <span className="rounded border border-slate-700 px-2 py-1 font-mono text-xs text-slate-300">
              throughput: {eventsPerMinute} evt/min
            </span>
            <span
              className={`font-mono text-xs uppercase tracking-wider ${
                status === "online"
                  ? "text-emerald-300"
                  : status === "connecting" || status === "reconnecting"
                    ? "text-amber-300"
                    : "text-rose-300"
              }`}
            >
              {status}
            </span>
          </div>
        </header>

        <div className="rounded-xl border border-emerald-400/25 bg-black/70 p-4 shadow-[0_0_40px_rgba(16,185,129,0.15)]">
          <p className="mb-3 font-mono text-xs text-slate-400">
            Logs em memória volátil (RAM). Nada é persistido no navegador.
          </p>

          <div className="h-[62vh] overflow-y-auto rounded-md border border-slate-800 bg-slate-950 p-3 font-mono text-sm leading-6">
            {filteredLogs.length === 0 ? (
              <p className="text-slate-500">Aguardando eventos autonomous_decision e audit_event...</p>
            ) : (
              filteredLogs.map((line) => (
                <div key={line.id} className="border-b border-slate-900 py-1 last:border-b-0">
                  <span className="text-slate-500">[{new Date(line.timestamp).toLocaleTimeString()}]</span>{" "}
                  <span className={line.kind === "audit_event" ? "text-cyan-300" : "text-emerald-300"}>{line.kind}</span>{" "}
                  <span className="text-violet-300">({line.source})</span>{" "}
                  <span className="text-slate-200">{line.text}</span>
                </div>
              ))
            )}
          </div>

          <div className="mt-3 flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950 p-2">
            <span className="font-mono text-sm text-emerald-300">&gt;_</span>
            <input
              type="text"
              value={commandText}
              onChange={(e) => setCommandText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  sendManualCommand();
                }
              }}
              autoComplete="off"
              spellCheck={false}
              className="flex-1 bg-transparent font-mono text-sm text-slate-100 outline-none placeholder:text-slate-500"
              placeholder="Digite uma instrução direta: ex. Liste os processos pesados"
            />
            <button
              onClick={sendManualCommand}
              className="rounded border border-emerald-400/70 px-3 py-1 font-mono text-xs text-emerald-300"
            >
              Enviar
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
