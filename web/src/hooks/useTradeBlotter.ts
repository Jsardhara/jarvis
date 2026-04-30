"use client";

/**
 * useTradeBlotter
 *
 * Provides live trade blotter state by combining:
 *   1. Initial fetch of /api/atlas/trades?limit=200&offset=0 + /api/atlas/trades/stats
 *   2. WebSocket push updates via Jarvis /ws for atlas trade-lifecycle events
 *   3. A 5-minute safety reconcile with REST
 *
 * Pure logic (computeStats, applyWsEventToTrades) lives in tradeBlotterLogic.ts.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import {
  computeStats,
  applyWsEventToTrades,
} from "./tradeBlotterLogic";
import type { TradeWsMessage } from "./tradeBlotterLogic";

// ─── Types ────────────────────────────────────────────────────────────────────

export type TradeStatus = "placed" | "open" | "closed" | "cancelled";

export interface Trade {
  trade_id: string;
  signal_id?: string;
  pair: string;
  side: "buy" | "sell";
  direction?: "LONG" | "SHORT";
  size: number;
  leverage?: number;
  entry_price?: number;
  exit_price?: number;
  pnl_usd?: number;
  pnl_pct?: number;
  status: TradeStatus;
  is_paper: boolean;
  stop_loss?: number;
  take_profit?: number;
  close_reason?: string;
  requested_size?: number;
  filled_size?: number;
  fees?: number;
  guardian_approved?: boolean;
  agent_notes?: string;
  opened_at?: string;
  closed_at?: string;
  created_at: string;
}

export interface TradeStats {
  open_count: number;
  today_pnl_usd: number;
  win_rate: number;
  total_trades: number;
  best_trade_usd: number;
}

export interface TradeBlotterState {
  trades: Trade[];
  stats: TradeStats;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

// Re-export pure logic for test consumption
export { computeStats, applyWsEventToTrades };

// ─── Constants ────────────────────────────────────────────────────────────────

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const JARVIS_WS = JARVIS_API.replace(/^http/, "ws") + "/ws";

const RECONCILE_INTERVAL_MS = 5 * 60_000;
const FETCH_TIMEOUT_MS = 8_000;
const RECONNECT_DELAY_MS = 3_500;

const EMPTY_STATS: TradeStats = {
  open_count: 0,
  today_pnl_usd: 0,
  win_rate: 0,
  total_trades: 0,
  best_trade_usd: 0,
};

// ─── HTTP fetch helpers ───────────────────────────────────────────────────────

async function fetchTrades(): Promise<Trade[]> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${JARVIS_API}/api/atlas/trades?limit=200&offset=0`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as { trades?: Trade[] } | Trade[];
    return Array.isArray(data) ? data : (data.trades ?? []);
  } catch (err) {
    clearTimeout(timeout);
    throw err;
  }
}

async function fetchStats(): Promise<TradeStats> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${JARVIS_API}/api/atlas/trades/stats`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as TradeStats;
  } catch (err) {
    clearTimeout(timeout);
    throw err;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useTradeBlotter(): TradeBlotterState {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<TradeStats>(EMPTY_STATS);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const mountedRef = useRef(true);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tradesRef = useRef<Trade[]>([]);

  useEffect(() => {
    tradesRef.current = trades;
  }, [trades]);

  const load = useCallback(async () => {
    try {
      const [fetchedTrades, fetchedStats] = await Promise.allSettled([
        fetchTrades(),
        fetchStats(),
      ]);

      if (!mountedRef.current) return;

      const resolvedTrades =
        fetchedTrades.status === "fulfilled" ? fetchedTrades.value : tradesRef.current;

      const resolvedStats =
        fetchedStats.status === "fulfilled"
          ? fetchedStats.value
          : computeStats(resolvedTrades);

      setTrades(resolvedTrades);
      setStats(resolvedStats);
      setIsLoading(false);
      setError(
        fetchedTrades.status === "rejected"
          ? fetchedTrades.reason instanceof Error
            ? fetchedTrades.reason
            : new Error("fetch failed")
          : null
      );
    } catch (err) {
      if (!mountedRef.current) return;
      setIsLoading(false);
      setError(err instanceof Error ? err : new Error("fetch failed"));
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    const ws = new WebSocket(JARVIS_WS);
    wsRef.current = ws;

    ws.onmessage = (evt: MessageEvent<string>) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(evt.data) as TradeWsMessage;
        const updated = applyWsEventToTrades(tradesRef.current, msg);
        if (updated) {
          tradesRef.current = updated;
          setTrades(updated);
          setStats(computeStats(updated));
        }
      } catch {
        // Malformed message — ignore
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      reconnectRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => { ws.close(); };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void load();
    connect();
    const reconcileTimer = setInterval(() => { void load(); }, RECONCILE_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(reconcileTimer);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [load, connect]);

  return { trades, stats, isLoading, error, refresh: load };
}
