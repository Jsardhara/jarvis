"use client";

/**
 * useAtlasNetwork
 *
 * Subscribes to the Jarvis /ws WebSocket and maintains:
 *   - A 60-second rolling buffer of in-flight messages (InFlightMessage[])
 *   - Per-agent status from atlas.agent_status events (AgentStates)
 *
 * Message kind mapping (atlas.<type> → MessageKind):
 *   signal     — atlas.market_signal
 *   decision   — atlas.pipeline_decision, atlas.trade_*
 *   order      — atlas.order_*, atlas.position_*
 *   insight    — atlas.learning_insight, atlas.strategy_proposed
 *   status     — atlas.agent_status
 *   other      — everything else with atlas. prefix
 *
 * Pause flag: when true, no new entries are pushed (existing fade-out continues).
 * Kind filter: set narrows which kinds appear in the returned inFlight list.
 */

import { useState, useEffect, useRef, useCallback } from "react";

// ─── Constants ────────────────────────────────────────────────────────────────

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const JARVIS_WS = JARVIS_API.replace(/^http/, "ws") + "/ws";

const RECONNECT_DELAY_MS = 3_500;
const BUFFER_TTL_MS = 60_000;
const DECAY_INTERVAL_MS = 2_000;

// ─── Public types ─────────────────────────────────────────────────────────────

export type AgentName =
  | "oracle"
  | "architect"
  | "guardian"
  | "trader"
  | "sage"
  | "orchestrator"
  | "kraken"
  | "postgres";

export type MessageKind =
  | "signal"
  | "decision"
  | "order"
  | "insight"
  | "status"
  | "other";

export type AgentRunState = "running" | "stale" | "error" | "unknown";

export interface InFlightMessage {
  id: string;
  source: AgentName;
  target: AgentName;
  kind: MessageKind;
  ts: number; // epoch ms
}

export type AgentStates = Record<string, AgentRunState>;

export type KindFilter = Set<MessageKind>;

export interface AtlasNetworkState {
  inFlight: InFlightMessage[];
  agentStates: AgentStates;
  paused: boolean;
  kindFilter: KindFilter;
  setPaused: (paused: boolean) => void;
  setKindFilter: (filter: KindFilter) => void;
}

// ─── WS message shape ─────────────────────────────────────────────────────────

interface WsMessage {
  type?: string;
  payload?: Record<string, unknown>;
  ts?: string;
  correlation_id?: string;
}

// ─── Kind mapping ─────────────────────────────────────────────────────────────

export function resolveKind(type: string): MessageKind {
  if (type === "atlas.market_signal") return "signal";
  if (
    type === "atlas.pipeline_decision" ||
    type === "atlas.trade_approved" ||
    type === "atlas.trade_rejected" ||
    type === "atlas.trade_modified"
  )
    return "decision";
  if (
    type === "atlas.order_placed" ||
    type === "atlas.order_filled" ||
    type === "atlas.order_cancelled" ||
    type === "atlas.position_opened" ||
    type === "atlas.position_closed"
  )
    return "order";
  if (
    type === "atlas.learning_insight" ||
    type === "atlas.strategy_proposed"
  )
    return "insight";
  if (type === "atlas.agent_status") return "status";
  return "other";
}

// ─── Source/target derivation ─────────────────────────────────────────────────

export function resolveSourceTarget(
  type: string,
  payload: Record<string, unknown>
): { source: AgentName; target: AgentName } | null {
  // Explicit payload fields take priority
  const src = (payload.source_agent as string | undefined)?.toLowerCase();
  const tgt = (payload.target_agent as string | undefined)?.toLowerCase();

  if (src && tgt) {
    return {
      source: src as AgentName,
      target: tgt as AgentName,
    };
  }

  // Derive from message type
  switch (type) {
    case "atlas.market_signal":
      return { source: "oracle", target: "orchestrator" };
    case "atlas.pipeline_decision":
      return { source: "orchestrator", target: "architect" };
    case "atlas.strategy_proposed":
      return { source: "architect", target: "orchestrator" };
    case "atlas.trade_approved":
    case "atlas.trade_rejected":
    case "atlas.trade_modified":
      return { source: "guardian", target: "trader" };
    case "atlas.order_placed":
    case "atlas.order_filled":
    case "atlas.order_cancelled":
      return { source: "trader", target: "kraken" };
    case "atlas.position_opened":
    case "atlas.position_closed":
      return { source: "trader", target: "sage" };
    case "atlas.learning_insight":
      return { source: "sage", target: "orchestrator" };
    case "atlas.agent_status":
      return null; // status events don't transit an edge
    default:
      return null;
  }
}

// ─── Agent status parsing ─────────────────────────────────────────────────────

export function parseRunState(payload: Record<string, unknown>): AgentRunState {
  if (payload.error) return "error";
  const s = ((payload.status as string | undefined) ?? "").toLowerCase();
  if (s === "running" || s === "active" || s === "ok") return "running";
  if (s === "paused" || s === "stale" || s === "warn") return "stale";
  if (s === "error" || s === "failed") return "error";
  return "running"; // benign default
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAtlasNetwork(): AtlasNetworkState {
  const [inFlight, setInFlight] = useState<InFlightMessage[]>([]);
  const [agentStates, setAgentStates] = useState<AgentStates>({});
  const [paused, setPaused] = useState(false);
  const [kindFilter, setKindFilter] = useState<KindFilter>(
    new Set<MessageKind>(["signal", "decision", "order", "insight", "status", "other"])
  );

  const pausedRef = useRef(paused);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // Keep pausedRef in sync so WS handler can read it without stale closure
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // ── Decay timer: remove entries older than 60s ────────────────────────────

  useEffect(() => {
    const timer = setInterval(() => {
      if (!mountedRef.current) return;
      const cutoff = Date.now() - BUFFER_TTL_MS;
      setInFlight((prev) => prev.filter((m) => m.ts >= cutoff));
    }, DECAY_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  // ── WS connection ─────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const ws = new WebSocket(JARVIS_WS);
    wsRef.current = ws;

    ws.onmessage = (evt: MessageEvent<string>) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(evt.data) as WsMessage;
        const type = msg.type ?? "";

        if (!type.startsWith("atlas.")) return;

        const payload = msg.payload ?? {};

        // Handle agent_status events — update agentStates map
        if (type === "atlas.agent_status") {
          const agentName =
            ((payload.agent_name as string | undefined) ??
              (payload.agent as string | undefined) ??
              ""
            ).toLowerCase();
          if (agentName) {
            const runState = parseRunState(payload);
            setAgentStates((prev) => ({ ...prev, [agentName]: runState }));
          }
          return;
        }

        // Skip new entries when paused
        if (pausedRef.current) return;

        const endpoints = resolveSourceTarget(type, payload);
        if (!endpoints) return;

        const kind = resolveKind(type);
        const id =
          (msg.correlation_id as string | undefined) ??
          `${type}:${Date.now()}:${Math.random().toString(36).slice(2, 7)}`;

        const entry: InFlightMessage = {
          id,
          source: endpoints.source,
          target: endpoints.target,
          kind,
          ts: msg.ts ? new Date(msg.ts).getTime() : Date.now(),
        };

        setInFlight((prev) => [...prev, entry]);
      } catch {
        // Malformed message — ignore
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      reconnectRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // Apply kind filter before returning
  const filteredInFlight = inFlight.filter((m) => kindFilter.has(m.kind));

  return {
    inFlight: filteredInFlight,
    agentStates,
    paused,
    kindFilter,
    setPaused,
    setKindFilter,
  };
}
