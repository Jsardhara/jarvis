"use client";

/**
 * useAgentMemory
 *
 * Fetches agent KV memory from /api/atlas/agents/{id}/memory.
 * Refreshes every 30 s — memory updates are slow.
 *
 * Returns { memory, isLoading, error, refresh }.
 */

import { useState, useEffect, useRef, useCallback } from "react";

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const REFRESH_INTERVAL_MS = 30_000;
const FETCH_TIMEOUT_MS = 8_000;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface MemoryEntry {
  value: unknown;
  updated_at: string;
}

export interface AgentMemoryState {
  memory: Record<string, MemoryEntry>;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

// ─── REST fetch ───────────────────────────────────────────────────────────────

async function fetchMemory(agentId: string): Promise<Record<string, MemoryEntry>> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${JARVIS_API}/api/atlas/agents/${agentId}/memory`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as Record<string, MemoryEntry>;
  } catch (err) {
    clearTimeout(timeout);
    throw err;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAgentMemory(agentId: string): AgentMemoryState {
  const [state, setState] = useState<Omit<AgentMemoryState, "refresh">>({
    memory: {},
    isLoading: true,
    error: null,
  });

  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const data = await fetchMemory(agentId);
      if (!mountedRef.current) return;
      setState({ memory: data, isLoading: false, error: null });
    } catch (err) {
      if (!mountedRef.current) return;
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err : new Error("fetch failed"),
      }));
    }
  }, [agentId]);

  useEffect(() => {
    mountedRef.current = true;

    void load();

    const timer = setInterval(() => {
      void load();
    }, REFRESH_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [load]);

  return { ...state, refresh: () => { void load(); } };
}

// ─── Exported constants (for tests) ───────────────────────────────────────────

export { REFRESH_INTERVAL_MS };
