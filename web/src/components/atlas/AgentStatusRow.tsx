"use client";

/**
 * AgentStatusRow
 *
 * Displays per-agent health indicators for the 5 Atlas sub-agents:
 * Oracle, Architect, Guardian, Trader, Sage.
 *
 * Status is sourced from `atlas.agent_status` events arriving over Jarvis /ws.
 * Each dot shows one of three states:
 *   green  (ok)   — last heartbeat < STALE_THRESHOLD_MS ago
 *   amber  (warn) — heartbeat present but stale (> STALE_THRESHOLD_MS)
 *   red    (crit) — error reported or never heard from
 *
 * The component subscribes to the same WS URL used by usePipelineStream,
 * filtered to type === "atlas.agent_status".
 */

import { useEffect, useReducer, useRef, useCallback } from "react";
import { Dot } from "@/components/ops/Dot";

// ─── Constants ────────────────────────────────────────────────────────────────

const ATLAS_SUB_AGENTS = [
  "oracle",
  "architect",
  "guardian",
  "trader",
  "sage",
] as const;

type AtlasSubAgent = (typeof ATLAS_SUB_AGENTS)[number];

const STALE_THRESHOLD_MS = 90_000; // 90 s — agent heartbeat should be < 60 s

const JARVIS_WS = (
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765"
).replace(/^http/, "ws") + "/ws";

const RECONNECT_DELAY_MS = 4_000;

// ─── Types ────────────────────────────────────────────────────────────────────

type AgentHealth = "ok" | "warn" | "error" | "unknown";

interface AgentEntry {
  status: AgentHealth;
  lastSeenMs: number | null; // epoch ms of last heartbeat
}

type AgentStatusMap = Record<AtlasSubAgent, AgentEntry>;

// ─── WS message shape for atlas.agent_status ─────────────────────────────────

interface AgentStatusPayload {
  agent_name?: string;
  agent?: string;
  status?: string;
  error?: string;
}

interface WsMessage {
  type?: string;
  payload?: AgentStatusPayload;
  ts?: string;
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

const INITIAL_STATUS: AgentStatusMap = Object.fromEntries(
  ATLAS_SUB_AGENTS.map((a) => [a, { status: "unknown" as AgentHealth, lastSeenMs: null }])
) as AgentStatusMap;

type Action =
  | { type: "heartbeat"; agent: AtlasSubAgent; health: AgentHealth; ts: number }
  | { type: "tick"; nowMs: number };

function reducer(state: AgentStatusMap, action: Action): AgentStatusMap {
  switch (action.type) {
    case "heartbeat":
      return {
        ...state,
        [action.agent]: {
          status: action.health,
          lastSeenMs: action.ts,
        },
      };
    case "tick": {
      // Re-evaluate staleness for all agents that have been heard from
      const updated: Partial<AgentStatusMap> = {};
      for (const agent of ATLAS_SUB_AGENTS) {
        const entry = state[agent];
        if (entry.lastSeenMs !== null && entry.status !== "error") {
          const age = action.nowMs - entry.lastSeenMs;
          const health: AgentHealth = age > STALE_THRESHOLD_MS ? "warn" : "ok";
          if (health !== entry.status) {
            updated[agent] = { ...entry, status: health };
          }
        }
      }
      return Object.keys(updated).length > 0 ? { ...state, ...updated } : state;
    }
    default:
      return state;
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function parseAgentName(payload: AgentStatusPayload): AtlasSubAgent | null {
  const raw = (payload.agent_name ?? payload.agent ?? "").toLowerCase();
  if ((ATLAS_SUB_AGENTS as readonly string[]).includes(raw)) {
    return raw as AtlasSubAgent;
  }
  return null;
}

function parseHealth(payload: AgentStatusPayload): AgentHealth {
  const s = (payload.status ?? "").toLowerCase();
  if (payload.error) return "error";
  if (s === "running" || s === "active" || s === "ok") return "ok";
  if (s === "paused" || s === "stale" || s === "warn") return "warn";
  if (s === "error" || s === "failed") return "error";
  return "ok"; // default for any unknown "running" heartbeat
}

function dotKind(health: AgentHealth): "ok" | "warn" | "crit" | "idle" {
  switch (health) {
    case "ok": return "ok";
    case "warn": return "warn";
    case "error": return "crit";
    default: return "idle";
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentStatusRow() {
  const [status, dispatch] = useReducer(reducer, INITIAL_STATUS);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const ws = new WebSocket(JARVIS_WS);
    wsRef.current = ws;

    ws.onmessage = (evt: MessageEvent<string>) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(evt.data) as WsMessage;
        if (msg.type !== "atlas.agent_status") return;

        const payload = msg.payload ?? {};
        const agent = parseAgentName(payload);
        if (!agent) return;

        const health = parseHealth(payload);
        const ts = msg.ts ? new Date(msg.ts).getTime() : Date.now();
        dispatch({ type: "heartbeat", agent, health, ts });
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

    // Tick every 30 s to re-evaluate staleness
    const tickTimer = setInterval(() => {
      if (mountedRef.current) {
        dispatch({ type: "tick", nowMs: Date.now() });
      }
    }, 30_000);

    return () => {
      mountedRef.current = false;
      clearInterval(tickTimer);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "6px 12px",
        background: "var(--ops-bg-deep)",
        border: "1px solid var(--ops-line)",
        fontFamily: "var(--ops-mono)",
        fontSize: 10,
        letterSpacing: "0.08em",
        color: "var(--ops-fg-dim)",
      }}
    >
      <span style={{ color: "var(--ops-fg-mute)", fontSize: 9, letterSpacing: "0.1em" }}>
        ATLAS AGENTS
      </span>

      {ATLAS_SUB_AGENTS.map((agent) => {
        const entry = status[agent];
        const kind = dotKind(entry.status);
        const label = agent.toUpperCase();
        const title =
          entry.lastSeenMs !== null
            ? `${label}: last seen ${Math.round((Date.now() - entry.lastSeenMs) / 1000)}s ago`
            : `${label}: no heartbeat received`;

        return (
          <span
            key={agent}
            title={title}
            style={{ display: "flex", alignItems: "center", gap: 5 }}
          >
            <Dot kind={kind} pulse={kind === "ok"} />
            <span style={{ color: kind === "ok" ? "var(--ops-fg)" : kind === "warn" ? "var(--ops-amber)" : "var(--ops-crit)" }}>
              {label}
            </span>
          </span>
        );
      })}
    </div>
  );
}
