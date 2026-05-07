"use client";

/**
 * useAtlasMode
 *
 * Fetches the Atlas agent mode from /api/agents and returns whether
 * Atlas is in "mock" mode. Used by MockModeBanner and any other consumer
 * that needs to gate on live vs mock.
 *
 * Polling interval: 60s — mode only changes on server restart, so
 * frequent polling is unnecessary.
 */

import { useEffect, useReducer } from "react";

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const POLL_INTERVAL_MS = 60_000;

export interface AtlasModeState {
  mode: "live" | "mock" | null;
  isLoading: boolean;
  error: string | null;
}

type Action =
  | { type: "loading" }
  | { type: "success"; mode: "live" | "mock" }
  | { type: "error"; message: string };

function reducer(state: AtlasModeState, action: Action): AtlasModeState {
  switch (action.type) {
    case "loading":
      return { ...state, isLoading: true, error: null };
    case "success":
      return { mode: action.mode, isLoading: false, error: null };
    case "error":
      return { ...state, isLoading: false, error: action.message };
    default:
      return state;
  }
}

interface AgentRecord {
  name: string;
  mode?: string;
}

interface AgentsResponse {
  agents: AgentRecord[];
}

async function fetchAtlasMode(): Promise<"live" | "mock"> {
  const res = await fetch(`${JARVIS_API}/api/agents`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const data = (await res.json()) as AgentsResponse;
  const atlas = data.agents.find((a) => a.name === "atlas");
  // If atlas mode is explicitly "mock", surface it; otherwise treat as live
  return atlas?.mode === "mock" ? "mock" : "live";
}

export function useAtlasMode(): AtlasModeState {
  const [state, dispatch] = useReducer(reducer, {
    mode: null,
    isLoading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      dispatch({ type: "loading" });
      try {
        const mode = await fetchAtlasMode();
        if (!cancelled) dispatch({ type: "success", mode });
      } catch (err: unknown) {
        if (!cancelled)
          dispatch({
            type: "error",
            message: err instanceof Error ? err.message : "fetch failed",
          });
      }
    };

    void load();

    const timer = setInterval(() => {
      void load();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return state;
}
