"use client";

/**
 * useAtlasSnapshot
 *
 * Provides near-real-time Atlas portfolio/position state by combining:
 *   1. An initial fetch of /api/atlas/snapshot on mount (cold-start data)
 *   2. Real-time push updates via Jarvis /ws for atlas.* events
 *   3. A 5-minute safety reconcile against /api/atlas/snapshot
 *
 * Atlas WS events handled:
 *   atlas.position_opened / atlas.position_closed → mutate positions list
 *   atlas.order_placed / atlas.order_filled      → update lastOrder indicator
 *   atlas.market_signal                          → ignored here (consumed by pipeline stream)
 *
 * Returns degraded=true when the last HTTP fetch failed or the snapshot
 * itself reported degraded. WS errors do not flip degraded — they are
 * transient; the reconcile will catch any persistent divergence.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type { AtlasSnapshot } from "@/lib/types";

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const JARVIS_WS = JARVIS_API.replace(/^http/, "ws") + "/ws";

/** Safety reconcile interval — 5 minutes. */
const RECONCILE_INTERVAL_MS = 5 * 60_000;

const FETCH_TIMEOUT_MS = 8_000;

const RECONNECT_DELAY_MS = 3_500;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AtlasSnapshotState {
  snapshot: AtlasSnapshot | null;
  degraded: boolean;
  isLoading: boolean;
  error: Error | null;
}

// ─── Position shape (minimal — actual structure is unknown[]) ─────────────────

interface PositionRecord {
  id?: string;
  symbol?: string;
  [key: string]: unknown;
}

// ─── WS event payloads ────────────────────────────────────────────────────────

interface WsMessage {
  type?: string;
  payload?: Record<string, unknown>;
  ts?: string;
}

// ─── Snapshot fetch ───────────────────────────────────────────────────────────

async function fetchSnapshot(): Promise<AtlasSnapshot> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${JARVIS_API}/api/atlas/snapshot`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as AtlasSnapshot;
  } catch (err) {
    clearTimeout(timeout);
    throw err;
  }
}

// ─── WS event → snapshot mutation ────────────────────────────────────────────

function applyWsEvent(
  snapshot: AtlasSnapshot,
  msg: WsMessage
): AtlasSnapshot | null {
  const type = msg.type ?? "";
  const payload = msg.payload ?? {};

  switch (type) {
    case "atlas.position_opened": {
      const pos = payload as PositionRecord;
      const existing = snapshot.positions as PositionRecord[];
      // Avoid duplicate if already present by id/symbol
      const alreadyHas = existing.some(
        (p) => p.id !== undefined && p.id === pos.id
      );
      if (alreadyHas) return null;
      return { ...snapshot, positions: [...existing, pos] };
    }

    case "atlas.position_closed": {
      const pos = payload as PositionRecord;
      const existing = snapshot.positions as PositionRecord[];
      const filtered = existing.filter((p) => {
        if (pos.id !== undefined && p.id !== undefined) return p.id !== pos.id;
        if (pos.symbol !== undefined && p.symbol !== undefined)
          return p.symbol !== pos.symbol;
        return true; // can't match — keep
      });
      if (filtered.length === existing.length) return null; // nothing changed
      return { ...snapshot, positions: filtered };
    }

    case "atlas.order_placed":
    case "atlas.order_filled": {
      // Reflect last order in pnl.last_order sub-key for display
      const pnlPrev = (snapshot.pnl ?? {}) as Record<string, unknown>;
      return {
        ...snapshot,
        pnl: {
          ...pnlPrev,
          last_order: { type, ...payload, ts: msg.ts ?? new Date().toISOString() },
        },
        ts: msg.ts ?? snapshot.ts,
      };
    }

    default:
      return null; // event not relevant to snapshot state
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAtlasSnapshot(): AtlasSnapshotState {
  const [state, setState] = useState<AtlasSnapshotState>({
    snapshot: null,
    degraded: false,
    isLoading: true,
    error: null,
  });

  const mountedRef = useRef(true);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const snapshotRef = useRef<AtlasSnapshot | null>(null);

  // Keep snapshotRef in sync so WS handler always sees latest state
  useEffect(() => {
    snapshotRef.current = state.snapshot;
  }, [state.snapshot]);

  // ── HTTP fetch (initial + reconcile) ─────────────────────────────────────

  const loadSnapshot = useCallback(async () => {
    try {
      const data = await fetchSnapshot();
      if (!mountedRef.current) return;
      setState({
        snapshot: data,
        degraded: data.degraded,
        isLoading: false,
        error: null,
      });
    } catch (err) {
      if (!mountedRef.current) return;
      setState((prev) => ({
        ...prev,
        degraded: true,
        isLoading: false,
        error: err instanceof Error ? err : new Error("fetch failed"),
      }));
    }
  }, []);

  // ── WS subscription ───────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const ws = new WebSocket(JARVIS_WS);
    wsRef.current = ws;

    ws.onmessage = (evt: MessageEvent<string>) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(evt.data) as WsMessage;
        const current = snapshotRef.current;
        if (!current) return; // no base to patch yet

        const updated = applyWsEvent(current, msg);
        if (updated) {
          snapshotRef.current = updated;
          setState((prev) => ({ ...prev, snapshot: updated }));
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

    // Cold-start: fetch immediately
    void loadSnapshot();

    // Subscribe to WS for push updates
    connect();

    // Safety reconcile every 5 min
    const reconcileTimer = setInterval(() => {
      void loadSnapshot();
    }, RECONCILE_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(reconcileTimer);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [loadSnapshot, connect]);

  return state;
}
