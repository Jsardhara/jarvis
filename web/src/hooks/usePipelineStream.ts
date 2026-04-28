"use client";

/**
 * usePipelineStream
 *
 * Subscribes to the Jarvis /ws WebSocket and returns Atlas pipeline
 * TraceEvent objects, organised per lane.
 *
 * Filtering rules:
 *   - event.agent === "atlas"
 *   - event.payload.stage ∈ {oracle, architect, guardian, trader, sage}
 *     OR event.type ∈ {agent.start, agent.done, agent.error} for the atlas agent
 *
 * WS message shape (from jarvis/web/api.py _make_event_sink):
 *   { type, request_id, agent, payload: { stage?, ... }, ts }
 *
 * The hook owns the WS connection and reconnects on disconnect.
 * Max 80 events per lane — older events are dropped from the left (LRU).
 */

import { useCallback, useEffect, useReducer, useRef } from "react";
import type { PipelineLane, PipelineState, TraceEvent } from "@/lib/types";

const JARVIS_API = (
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765"
).replace(/^http/, "ws");

const WS_URL = `${JARVIS_API}/ws`;

const PIPELINE_LANES: PipelineLane[] = [
  "oracle",
  "architect",
  "guardian",
  "trader",
  "sage",
];

const MAX_EVENTS_PER_LANE = 80;

export type ConnectionState = "connecting" | "live" | "lost";

export interface PipelineStreamState {
  events: TraceEvent[];
  connectionState: ConnectionState;
  /** Monotonically increasing run number parsed from events */
  currentRun: number;
}

// ─── Raw WS message from the Python API ──────────────────────────────────────

interface WsMessage {
  type: string;
  request_id?: string;
  agent?: string;
  payload?: {
    stage?: string;
    state?: string;
    duration_ms?: number;
    tier?: number;
    intent?: string;
    needs_confirm?: boolean;
    violations?: string[];
    error?: string;
    pipeline_run?: number;
  };
  ts?: string;
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

type Action =
  | { type: "ws_open" }
  | { type: "ws_close" }
  | { type: "ws_message"; event: TraceEvent }
  | { type: "ws_update_event"; id: string; patch: Partial<TraceEvent> };

function laneOf(events: TraceEvent[], lane: PipelineLane): TraceEvent[] {
  return events.filter((e) => e.lane === lane);
}

function capLane(
  events: TraceEvent[],
  lane: PipelineLane,
  max: number
): TraceEvent[] {
  const inLane = laneOf(events, lane);
  if (inLane.length <= max) return events;
  // Drop oldest entries from this lane
  const toDrop = inLane.length - max;
  let dropped = 0;
  return events.filter((e) => {
    if (e.lane !== lane) return true;
    if (dropped < toDrop) {
      dropped++;
      return false;
    }
    return true;
  });
}

function reducer(
  state: PipelineStreamState,
  action: Action
): PipelineStreamState {
  switch (action.type) {
    case "ws_open":
      return { ...state, connectionState: "live" };
    case "ws_close":
      return { ...state, connectionState: "lost" };
    case "ws_message": {
      const ev = action.event;
      // Check if we already have an event with this id (update in place)
      const existing = state.events.find((e) => e.id === ev.id);
      if (existing) {
        const updated = state.events.map((e) =>
          e.id === ev.id ? { ...e, ...ev } : e
        );
        return {
          ...state,
          events: updated,
          currentRun: Math.max(state.currentRun, ev.pipelineRun),
        };
      }
      // New event — append and cap the lane
      let next = [...state.events, ev];
      next = capLane(next, ev.lane, MAX_EVENTS_PER_LANE);
      return {
        ...state,
        events: next,
        currentRun: Math.max(state.currentRun, ev.pipelineRun),
      };
    }
    case "ws_update_event": {
      const updated = state.events.map((e) =>
        e.id === action.id ? { ...e, ...action.patch } : e
      );
      return { ...state, events: updated };
    }
    default:
      return state;
  }
}

const INITIAL_STATE: PipelineStreamState = {
  events: [],
  connectionState: "connecting",
  currentRun: 0,
};

// ─── WS message → TraceEvent ──────────────────────────────────────────────────

function toTraceEvent(msg: WsMessage): TraceEvent | null {
  if (!msg.agent || msg.agent !== "atlas") return null;

  const payload = msg.payload ?? {};
  const stage = (payload.stage ?? "").toLowerCase() as PipelineLane;

  // Only accept known pipeline stages
  if (!PIPELINE_LANES.includes(stage)) {
    // For agent.start / agent.done / agent.error without a stage, skip
    return null;
  }

  const id = msg.request_id
    ? `${msg.request_id}:${stage}`
    : `${stage}:${Date.now()}`;

  let state: PipelineState = "pending";
  if (msg.type === "agent.start") state = "running";
  else if (msg.type === "agent.done") {
    state = payload.needs_confirm ? "blocked" : "done";
  } else if (msg.type === "agent.error") state = "error";
  else if (payload.state) {
    const raw = payload.state as string;
    if (["pending", "running", "done", "blocked", "error"].includes(raw)) {
      state = raw as PipelineState;
    }
  }

  const run = payload.pipeline_run ?? 0;

  return {
    id,
    pipelineRun: run,
    lane: stage,
    state,
    startedAt: msg.ts ?? new Date().toISOString(),
    durationMs: payload.duration_ms,
    tier: payload.tier as TraceEvent["tier"],
    intent: payload.intent,
    needsConfirm: payload.needs_confirm,
    violations: payload.violations,
    errorMessage: payload.error,
  };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

const RECONNECT_DELAY_MS = 3_000;

export function usePipelineStream(): PipelineStreamState {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  const connect = useCallback(() => {
    if (!mounted.current) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mounted.current) return;
      dispatch({ type: "ws_open" });
    };

    ws.onmessage = (evt: MessageEvent<string>) => {
      if (!mounted.current) return;
      try {
        const msg = JSON.parse(evt.data) as WsMessage;
        const traceEvent = toTraceEvent(msg);
        if (traceEvent) {
          dispatch({ type: "ws_message", event: traceEvent });
        }
      } catch {
        // Malformed message — ignore
      }
    };

    ws.onclose = () => {
      if (!mounted.current) return;
      dispatch({ type: "ws_close" });
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
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
