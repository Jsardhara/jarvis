"use client";

/**
 * useInboxStream
 *
 * Subscribes to the Jarvis /ws WebSocket and filters frames where
 * type === "inbox.event". Returns the latest 200 events (LRU cap).
 *
 * Auto-reconnects on disconnect with exponential backoff:
 *   1s → 2s → 4s → 8s → 16s → 30s (max)
 *
 * The hook does NOT perform an initial HTTP backfill — callers that
 * need historical data should fetch /api/inbox separately and merge
 * with the events returned here, deduplicating by id.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";

const JARVIS_API = (
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765"
).replace(/^http/, "ws");

const WS_URL = `${JARVIS_API}/ws`;

const MAX_EVENTS = 200;

const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

// ─── Public types ─────────────────────────────────────────────────────────────

export interface InboxEvent {
  id?: string;
  ts?: string;
  agent?: string;
  summary?: string;
  /** Raw payload forwarded from the WS frame */
  payload: Record<string, unknown>;
}

export interface InboxStreamState {
  events: InboxEvent[];
  connected: boolean;
  error: Error | null;
}

// ─── WS frame shape ───────────────────────────────────────────────────────────

interface WsFrame {
  type: string;
  event?: Record<string, unknown>;
  [key: string]: unknown;
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

type Action =
  | { type: "open" }
  | { type: "close"; error?: Error }
  | { type: "event"; event: InboxEvent };

function capEvents(events: InboxEvent[], max: number): InboxEvent[] {
  if (events.length <= max) return events;
  return events.slice(events.length - max);
}

function reducer(state: InboxStreamState, action: Action): InboxStreamState {
  switch (action.type) {
    case "open":
      return { ...state, connected: true, error: null };
    case "close":
      return { ...state, connected: false, error: action.error ?? null };
    case "event":
      return {
        ...state,
        events: capEvents([...state.events, action.event], MAX_EVENTS),
      };
    default:
      return state;
  }
}

const INITIAL_STATE: InboxStreamState = {
  events: [],
  connected: false,
  error: null,
};

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useInboxStream(): InboxStreamState {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const mounted = useRef(true);

  const connect = useCallback(() => {
    if (!mounted.current) return;

    const ws = new WebSocket(WS_URL);
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

        // Handle inbox events
        if (frame.type === "inbox.event") {
          const raw = frame.event ?? {};
          const inboxEvent: InboxEvent = {
            id: typeof raw["id"] === "string" ? raw["id"] : undefined,
            ts: typeof raw["ts"] === "string" ? raw["ts"] : undefined,
            agent: typeof raw["agent"] === "string" ? raw["agent"] : undefined,
            summary:
              typeof raw["summary"] === "string" ? raw["summary"] : undefined,
            payload: raw,
          };
          dispatch({ type: "event", event: inboxEvent });
          return;
        }

        // Handle agent lifecycle + confirmation events (broadcast as synthetic inbox events)
        const agentEventTypes = [
          "agent.start",
          "agent.done",
          "agent.error",
          "confirmation.created",
          "confirmation.resolved",
        ];
        if (agentEventTypes.includes(frame.type)) {
          const payload: Record<string, unknown> = { ...(frame.event ?? frame) };
          const summary =
            typeof payload["summary"] === "string"
              ? payload["summary"]
              : typeof payload["error"] === "string"
                ? payload["error"]
                : frame.type;
          const inboxEvent: InboxEvent = {
            id: typeof payload["id"] === "string" ? payload["id"] : undefined,
            ts: typeof payload["ts"] === "string" ? payload["ts"] : undefined,
            agent: typeof payload["agent"] === "string" ? payload["agent"] : undefined,
            summary,
            payload,
          };
          dispatch({ type: "event", event: inboxEvent });
        }
      } catch {
        // Malformed frame — ignore
      }
    };

    ws.onclose = () => {
      if (!mounted.current) return;
      dispatch({ type: "close" });

      const attempt = attemptRef.current;
      const delay = Math.min(
        BACKOFF_BASE_MS * Math.pow(2, attempt),
        BACKOFF_MAX_MS
      );
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
