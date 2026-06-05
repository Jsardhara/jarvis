"use client";

/**
 * useAgentEvents
 *
 * Subscribes to the Jarvis /ws WebSocket and handles ALL TraceEvent types:
 *   agent.start            → agent began processing
 *   agent.done             → agent completed successfully
 *   agent.error            → agent encountered an error
 *   confirmation.created   → a new approval/confirmation was requested
 *   confirmation.resolved  → a confirmation was approved or rejected
 *   inbox.event            → new inbox message arrived
 *   voice.state            → voice loop mode change
 *   dispatch               → orchestrator dispatch result
 *
 * Returns every event in a single unified stream plus convenience views
 * (agent events only, confirmations only, inbox events only).
 *
 * Auto-reconnects with exponential backoff (1s → 2s → 4s → … → 30s max).
 * Does NOT perform HTTP backfill — callers that need historical data should
 * fetch the relevant REST endpoint separately.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";

const JARVIS_WS = (
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765").replace(/^http/, "ws")
    : "ws://localhost:8765"
) + "/ws";

const MAX_EVENTS = 500;
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

// ─── Public types ─────────────────────────────────────────────────────────────

export type AgentEventType =
  | "agent.start"
  | "agent.done"
  | "agent.error"
  | "confirmation.created"
  | "confirmation.resolved"
  | "inbox.event"
  | "voice.state"
  | "dispatch";

export interface AgentEvent {
  id: string;            // unique key for React rendering
  type: AgentEventType;
  ts: string;
  request_id: string;
  agent: string;
  risk?: string;
  severity?: "info" | "warn" | "alert";
  title?: string;
  payload: Record<string, unknown>;
}

export interface ConfirmationView {
  id: string;
  agent: string;
  action: string;
  risk: string;
  summary: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  payload: Record<string, unknown>;
}

export interface AgentEventState {
  /** All events, oldest-first, capped at MAX_EVENTS. */
  events: AgentEvent[];
  /** Confirmation events extracted from the stream. */
  confirmations: ConfirmationView[];
  /** Whether the WebSocket is currently connected. */
  connected: boolean;
  /** Last connection error, if any. */
  error: Error | null;
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

type Action =
  | { type: "open" }
  | { type: "close"; error?: Error }
  | { type: "event"; event: AgentEvent }
  | { type: "confirmation_created"; conf: ConfirmationView }
  | { type: "confirmation_resolved"; id: string; status: "approved" | "rejected" };

function reducer(state: AgentEventState, action: Action): AgentEventState {
  switch (action.type) {
    case "open":
      return { ...state, connected: true, error: null };
    case "close":
      return { ...state, connected: false, error: action.error ?? null };
    case "event": {
      const events =
        state.events.length >= MAX_EVENTS
          ? [...state.events.slice(1), action.event]
          : [...state.events, action.event];
      return { ...state, events };
    }
    case "confirmation_created": {
      const confirmations = [...state.confirmations, action.conf];
      return { ...state, confirmations };
    }
    case "confirmation_resolved": {
      const confirmations = state.confirmations.map((c) =>
        c.id === action.id ? { ...c, status: action.status } : c,
      );
      return { ...state, confirmations };
    }
    default:
      return state;
  }
}

const INITIAL: AgentEventState = {
  events: [],
  confirmations: [],
  connected: false,
  error: null,
};

// ─── WS frame parsing ─────────────────────────────────────────────────────────

interface WsFrame {
  type?: string;
  ts?: string;
  request_id?: string;
  agent?: string;
  risk?: string;
  severity?: string;
  title?: string;
  payload?: Record<string, unknown>;
  event?: Record<string, unknown>;
  [key: string]: unknown;
}

function parseFrame(raw: WsFrame): { event: AgentEvent | null; conf: ConfirmationView | null; resolved: { id: string; status: "approved" | "rejected" } | null } {
  const type = raw.type ?? "unknown";
  const ts = raw.ts ?? new Date().toISOString();
  const request_id = raw.request_id ?? "";
  const agent = raw.agent ?? "";
  const payload = raw.payload ?? raw.event ?? {};

  const base: AgentEvent = {
    id: `${type}_${ts}_${Math.random().toString(36).slice(2, 8)}`,
    type: type as AgentEventType,
    ts,
    request_id,
    agent,
    risk: raw.risk,
    severity: raw.severity as AgentEvent["severity"],
    title: raw.title,
    payload,
  };

  let conf: ConfirmationView | null = null;
  let resolved: { id: string; status: "approved" | "rejected" } | null = null;

  if (type === "confirmation.created") {
    const confPayload = (payload.confirmation ?? payload) as Record<string, unknown>;
    conf = {
      id: String(confPayload.id ?? confPayload.confirmation_id ?? ""),
      agent: String(confPayload.agent ?? agent),
      action: String(confPayload.intent ?? confPayload.action ?? "unknown"),
      risk: String(confPayload.risk ?? "mutate"),
      summary: String(confPayload.summary ?? ""),
      status: "pending",
      created_at: String(confPayload.created_at ?? ts),
      payload: confPayload,
    };
  }

  if (type === "confirmation.resolved") {
    const resolvedPayload = (payload.confirmation ?? payload) as Record<string, unknown>;
    resolved = {
      id: String(resolvedPayload.id ?? resolvedPayload.confirmation_id ?? ""),
      status: String(resolvedPayload.status ?? "approved") as "approved" | "rejected",
    };
  }

  return { event: base, conf, resolved };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAgentEvents(): AgentEventState {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const mounted = useRef(true);

  const connect = useCallback(() => {
    if (!mounted.current) return;

    // If JARVIS_API_TOKEN is set, append it as query param (browsers can't set WS headers).
    const token = typeof window !== "undefined" ? window.localStorage.getItem("jarvis-token") : null;
    const wsUrl = token ? `${JARVIS_WS}?token=${encodeURIComponent(token)}` : JARVIS_WS;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mounted.current) return;
      attemptRef.current = 0;
      dispatch({ type: "open" });
    };

    ws.onmessage = (evt: MessageEvent<string>) => {
      if (!mounted.current) return;
      try {
        const frame = JSON.parse(evt.data) as WsFrame;
        const { event, conf, resolved: res } = parseFrame(frame);
        if (event) dispatch({ type: "event", event });
        if (conf) dispatch({ type: "confirmation_created", conf });
        if (res) dispatch({ type: "confirmation_resolved", id: res.id, status: res.status });
      } catch {
        // malformed frame — ignore
      }
    };

    ws.onclose = () => {
      if (!mounted.current) return;
      dispatch({ type: "close" });

      const attempt = attemptRef.current;
      const delay = Math.min(BACKOFF_BASE_MS * Math.pow(2, attempt), BACKOFF_MAX_MS);
      attemptRef.current = attempt + 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    mounted.current = true;
    connect();
    return () => {
      mounted.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return state;
}
