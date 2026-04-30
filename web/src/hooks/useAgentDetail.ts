"use client";

/**
 * useAgentDetail
 *
 * Provides per-agent detail state by combining:
 *   1. Initial REST fetch from /api/atlas/agents/{id}
 *   2. Live WS push updates filtered to source_agent === agentId
 *      — each matching event is prepended to recent_activity (capped at 50)
 *   3. A 5-minute safety reconcile against the REST endpoint
 *
 * Mirrors the useAtlasSnapshot lifecycle pattern.
 */

import { useState, useEffect, useRef, useCallback } from "react";

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const JARVIS_WS = JARVIS_API.replace(/^http/, "ws") + "/ws";

const RECONCILE_INTERVAL_MS = 5 * 60_000;
const FETCH_TIMEOUT_MS = 8_000;
const RECONNECT_DELAY_MS = 3_500;
const MAX_ACTIVITY = 50;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface RecentActivity {
  event_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface AgentDetail {
  id: string;
  display_name: string;
  model: string;
  state: string;
  last_heartbeat: string | null;
  recent_activity: RecentActivity[];
}

export interface AgentDetailState {
  detail: AgentDetail | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

// ─── WS message shape ─────────────────────────────────────────────────────────

interface WsMessage {
  type?: string;
  source_agent?: string;
  payload?: Record<string, unknown>;
  ts?: string;
}

// ─── REST fetch ───────────────────────────────────────────────────────────────

async function fetchAgentDetail(agentId: string): Promise<AgentDetail> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${JARVIS_API}/api/atlas/agents/${agentId}`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as AgentDetail;
  } catch (err) {
    clearTimeout(timeout);
    throw err;
  }
}

// ─── WS event → activity prepend ──────────────────────────────────────────────

function applyWsActivity(
  detail: AgentDetail,
  msg: WsMessage
): AgentDetail | null {
  if (!msg.source_agent || msg.source_agent !== detail.id) return null;
  if (!msg.type) return null;

  const newEvent: RecentActivity = {
    event_type: msg.type,
    payload: msg.payload ?? {},
    occurred_at: msg.ts ?? new Date().toISOString(),
  };

  const updated = [newEvent, ...detail.recent_activity].slice(0, MAX_ACTIVITY);

  return { ...detail, recent_activity: updated };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAgentDetail(agentId: string): AgentDetailState {
  const [state, setState] = useState<Omit<AgentDetailState, "refresh">>({
    detail: null,
    isLoading: true,
    error: null,
  });

  const mountedRef = useRef(true);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const detailRef = useRef<AgentDetail | null>(null);

  // Keep detailRef in sync so WS handler sees latest state
  useEffect(() => {
    detailRef.current = state.detail;
  }, [state.detail]);

  // ── REST fetch ────────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    try {
      const data = await fetchAgentDetail(agentId);
      if (!mountedRef.current) return;
      detailRef.current = data;
      setState({ detail: data, isLoading: false, error: null });
    } catch (err) {
      if (!mountedRef.current) return;
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err : new Error("fetch failed"),
      }));
    }
  }, [agentId]);

  // ── WS subscription ───────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const ws = new WebSocket(JARVIS_WS);
    wsRef.current = ws;

    ws.onmessage = (evt: MessageEvent<string>) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(evt.data) as WsMessage;
        const current = detailRef.current;
        if (!current) return;

        const updated = applyWsActivity(current, msg);
        if (updated) {
          detailRef.current = updated;
          setState((prev) => ({ ...prev, detail: updated }));
        }
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

  // ── Mount / unmount ───────────────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;

    void load();
    connect();

    const reconcileTimer = setInterval(() => {
      void load();
    }, RECONCILE_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(reconcileTimer);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [load, connect]);

  return { ...state, refresh: () => { void load(); } };
}

// ─── Exported pure helpers (for tests) ────────────────────────────────────────

export { applyWsActivity };
