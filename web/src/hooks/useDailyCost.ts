"use client";

/**
 * useDailyCost
 *
 * Fetches the last N days of daily cost rollups from the Jarvis API.
 * The Python endpoint is GET /api/cost/rollup?date_str=YYYY-MM-DD.
 *
 * The backend returns:
 *   { date, total_usd, by_agent: { tempo: 0.4, ... }, by_model: {...}, call_count }
 *
 * We translate this into DailyRollup[] with perAgent: AgentCost[] for the
 * CostChart component, which expects the spec shape from types.ts.
 *
 * NOTE: A3 ships /api/cost/rollup with query param `date_str` (not `date`).
 * The spec mentions `?days=14` — the backend doesn't implement that yet.
 * We client-side fan-out 14 individual date queries instead (matching spec §6.2).
 */

import { useEffect, useReducer } from "react";
import type { AgentCost, CostAgent, DailyRollup } from "@/lib/types";

const JARVIS_API =
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765");

const KNOWN_AGENTS: CostAgent[] = [
  "atlas",
  "forge",
  "lens",
  "scholar",
  "tempo",
  "jarvis",
  "sentinel",
];

// ─── Raw response from /api/cost/rollup ───────────────────────────────────────

interface RawRollup {
  date: string;
  total_usd: number;
  by_agent: Record<string, number>;
  by_model: Record<string, number>;
  call_count: number;
}

function rawToDaily(raw: RawRollup): DailyRollup {
  // Build perAgent from by_agent. Only include KNOWN_AGENTS.
  // Unknown agents are bucketed into "jarvis" as orchestrator overhead.
  const buckets: Record<CostAgent, { cost: number; calls: number }> = {
    atlas: { cost: 0, calls: 0 },
    forge: { cost: 0, calls: 0 },
    lens: { cost: 0, calls: 0 },
    scholar: { cost: 0, calls: 0 },
    tempo: { cost: 0, calls: 0 },
    jarvis: { cost: 0, calls: 0 },
    sentinel: { cost: 0, calls: 0 },
  };

  for (const [agent, cost] of Object.entries(raw.by_agent)) {
    const key = KNOWN_AGENTS.includes(agent as CostAgent)
      ? (agent as CostAgent)
      : "jarvis";
    buckets[key].cost += cost;
    buckets[key].calls += 1; // approximate — backend doesn't give per-agent call counts
  }

  const perAgent: AgentCost[] = KNOWN_AGENTS.map((a) => ({
    agent: a,
    costUsd: buckets[a].cost,
    calls: buckets[a].calls,
    inputTokens: 0,  // not available at rollup level
    outputTokens: 0, // not available at rollup level
  })).filter((a) => a.costUsd > 0);

  return {
    date: raw.date,
    totalUsd: raw.total_usd,
    perAgent,
  };
}

// ─── ISO date helpers ─────────────────────────────────────────────────────────

function isoDate(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

// ─── State ────────────────────────────────────────────────────────────────────

interface CostState {
  data: DailyRollup[];
  loading: boolean;
  error: string | null;
}

type Action =
  | { type: "loading" }
  | { type: "success"; data: DailyRollup[] }
  | { type: "error"; message: string };

function reducer(state: CostState, action: Action): CostState {
  switch (action.type) {
    case "loading":
      return { ...state, loading: true, error: null };
    case "success":
      return { data: action.data, loading: false, error: null };
    case "error":
      return { ...state, loading: false, error: action.message };
    default:
      return state;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useDailyCost(days = 14): CostState {
  const [state, dispatch] = useReducer(reducer, {
    data: [],
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: "loading" });

    async function fetchAll() {
      try {
        // Build date list: most-recent to oldest, then reverse for chronological display
        const dateList = Array.from({ length: days }, (_, i) => isoDate(days - 1 - i));

        const results = await Promise.all(
          dateList.map(async (date) => {
            try {
              const res = await fetch(
                `${JARVIS_API}/api/cost/rollup?date_str=${date}`
              );
              if (!res.ok) {
                // Return empty rollup for this day
                return {
                  date,
                  total_usd: 0,
                  by_agent: {},
                  by_model: {},
                  call_count: 0,
                } satisfies RawRollup;
              }
              return (await res.json()) as RawRollup;
            } catch {
              return {
                date,
                total_usd: 0,
                by_agent: {},
                by_model: {},
                call_count: 0,
              } satisfies RawRollup;
            }
          })
        );

        if (cancelled) return;
        dispatch({ type: "success", data: results.map(rawToDaily) });
      } catch (err: unknown) {
        if (cancelled) return;
        dispatch({
          type: "error",
          message: err instanceof Error ? err.message : "Failed to fetch cost data",
        });
      }
    }

    void fetchAll();
    return () => {
      cancelled = true;
    };
  }, [days]);

  return state;
}
