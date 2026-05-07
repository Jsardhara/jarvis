"use client";

/**
 * usePipelineStream
 *
 * Subscribes to the Jarvis /ws WebSocket and returns Atlas pipeline
 * TraceEvent objects, organised per lane.
 *
 * Two event sources are multiplexed on the same WS connection:
 *
 *   1. Jarvis-synthesized stage events
 *      { agent: "atlas", type: "agent.start"|"agent.done"|"agent.error",
 *        payload: { stage, ... } }
 *
 *   2. Atlas-emitted real events (Phase 3a)
 *      { type: "atlas.<message_type>", payload: { ... }, correlation_id? }
 *
 * Atlas event → swimlane lane mapping:
 *   atlas.pipeline_decision  → orchestrator (rendered in oracle lane)
 *   atlas.trade_approved     → guardian lane
 *   atlas.trade_rejected     → guardian lane
 *   atlas.trade_modified     → guardian lane
 *   atlas.order_placed       → trader lane
 *   atlas.order_filled       → trader lane
 *   atlas.position_opened    → trader lane
 *   atlas.position_closed    → trader lane
 *   atlas.market_signal      → oracle lane
 *   atlas.learning_insight   → sage lane
 *   atlas.strategy_proposed  → architect lane
 *   atlas.agent_status       → skipped (handled by AgentStatusRow)
 *
 * Events sharing the same correlation_id (signal_id from Atlas) are threaded
 * without dedup conflicts — they each receive distinct ids using the
 * message_type suffix.
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

// ─── Atlas event type → lane mapping ─────────────────────────────────────────

const ATLAS_EVENT_LANE: Record<string, PipelineLane | null> = {
  "atlas.pipeline_decision":  "oracle",     // orchestrator decision surfaced in oracle
  "atlas.market_signal":      "oracle",
  "atlas.strategy_proposed":  "architect",
  "atlas.trade_approved":     "guardian",
  "atlas.trade_rejected":     "guardian",
  "atlas.trade_modified":     "guardian",
  "atlas.order_placed":       "trader",
  "atlas.order_filled":       "trader",
  "atlas.position_opened":    "trader",
  "atlas.position_closed":    "trader",
  "atlas.learning_insight":   "sage",
  "atlas.agent_status":       null,         // handled by AgentStatusRow, skip
};

// ─── State types ──────────────────────────────────────────────────────────────

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
  correlation_id?: string;
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
    // Atlas-side fields
    signal_id?: string;
    direction?: string;
    action?: string;
    reason?: string;
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

// ─── WS message → TraceEvent (Jarvis-synthesized) ─────────────────────────────

function fromJarvisEvent(msg: WsMessage): TraceEvent | null {
  if (!msg.agent || msg.agent !== "atlas") return null;

  const payload = msg.payload ?? {};
  const stage = (payload.stage ?? "").toLowerCase() as PipelineLane;

  if (!PIPELINE_LANES.includes(stage)) return null;

  const id = msg.request_id
    ? `${msg.request_id}:${stage}`
    : `${stage}:${Date.now()}`;

  let state: PipelineState = "pending";
  if (msg.type === "agent.start") state = "running";
  else if (msg.type === "agent.done") {
    state = payload.needs_confirm ? "blocked" : "done";
  } else if (msg.type === "agent.error") state = "error";
  else if (payload.state) {
    const raw = payload.state;
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

// ─── WS message → TraceEvent (Atlas-emitted) ──────────────────────────────────

function fromAtlasEvent(msg: WsMessage): TraceEvent | null {
  const lane = ATLAS_EVENT_LANE[msg.type];
  if (lane === undefined) return null; // not an atlas.* event we handle here
  if (lane === null) return null;       // explicitly skipped (agent_status)

  const payload = msg.payload ?? {};

  // Build a stable id using correlation_id + message type suffix to allow
  // multiple atlas events on the same signal to coexist without dedup collisions.
  const correlationBase =
    msg.correlation_id ??
    payload.signal_id ??
    msg.request_id ??
    `${msg.type}:${Date.now()}`;

  // Strip "atlas." prefix for a compact suffix
  const typeSuffix = msg.type.replace(/^atlas\./, "");
  const id = `${correlationBase}:${typeSuffix}`;

  // Derive state from message type
  let state: PipelineState = "done";
  if (msg.type === "atlas.trade_rejected") state = "error";
  else if (msg.type === "atlas.trade_approved" || msg.type === "atlas.trade_modified") state = "done";
  else if (msg.type === "atlas.pipeline_decision") {
    const decision = (payload.action ?? payload.direction ?? "").toString().toLowerCase();
    if (decision === "block" || decision === "halt") state = "blocked";
    else state = "done";
  }

  // Surface intent from common payload fields
  const intent =
    (payload.intent as string | undefined) ??
    (payload.direction as string | undefined) ??
    (payload.action as string | undefined) ??
    (payload.reason as string | undefined);

  return {
    id,
    pipelineRun: (payload.pipeline_run as number | undefined) ?? 0,
    lane,
    state,
    startedAt: msg.ts ?? new Date().toISOString(),
    intent,
    errorMessage:
      msg.type === "atlas.trade_rejected"
        ? ((payload.reason as string | undefined) ?? "trade rejected")
        : undefined,
  };
}

// ─── Combined parser ──────────────────────────────────────────────────────────

function toTraceEvent(msg: WsMessage): TraceEvent | null {
  // Try Atlas-emitted events first (type starts with "atlas.")
  if (msg.type?.startsWith("atlas.")) {
    return fromAtlasEvent(msg);
  }
  // Fall through to Jarvis-synthesized events
  return fromJarvisEvent(msg);
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
