"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

export interface LensSearchResult {
  url: string;
  title: string;
  snippet?: string;
  score?: number;
}

export interface LensQuickSearchResponse {
  query: string;
  results: LensSearchResult[];
  markdown: string;
  count: number;
}

export interface LensDeepResearchResponse {
  query: string;
  sources: { url: string; title: string }[];
  markdown: string;
  depth: number;
}

export type LensMode = "quick" | "deep";

export interface QueryRecord {
  id: string;
  query: string;
  mode: LensMode;
  ts: string;
  result: LensQuickSearchResponse | LensDeepResearchResponse;
}

const HISTORY_KEY = "lens.history.v1";
const HISTORY_MAX = 20;

function loadHistory(): QueryRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as QueryRecord[]) : [];
  } catch {
    return [];
  }
}

function persistHistory(items: QueryRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      HISTORY_KEY,
      JSON.stringify(items.slice(0, HISTORY_MAX)),
    );
  } catch {
    /* quota — drop */
  }
}

export function useLens(): {
  history: QueryRecord[];
  search: (query: string, mode: LensMode) => Promise<QueryRecord | null>;
  busy: boolean;
  error: string | null;
  clearHistory: () => void;
} {
  const [history, setHistory] = useState<QueryRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setHistory(loadHistory());
  }, []);

  const search = useCallback(
    async (query: string, mode: LensMode): Promise<QueryRecord | null> => {
      const q = query.trim();
      if (!q) return null;
      setBusy(true);
      setError(null);
      try {
        const action = mode === "deep" ? "deep_research" : "quick_search";
        const argKey = mode === "deep" ? "query" : "query";
        const res = await apiFetch("/api/agents/lens/dispatch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, args: { [argKey]: q } }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { result: unknown };
        const record: QueryRecord = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          query: q,
          mode,
          ts: new Date().toISOString(),
          result: body.result as QueryRecord["result"],
        };
        setHistory((prev) => {
          const next = [record, ...prev].slice(0, HISTORY_MAX);
          persistHistory(next);
          return next;
        });
        return record;
      } catch (err) {
        setError(err instanceof Error ? err.message : "search failed");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const clearHistory = useCallback(() => {
    setHistory([]);
    persistHistory([]);
  }, []);

  return { history, search, busy, error, clearHistory };
}

export function useWatchlist(): {
  items: string[];
  loading: boolean;
  error: string | null;
  add: (term: string) => Promise<void>;
  remove: (term: string) => Promise<void>;
  refresh: () => Promise<void>;
} {
  const [items, setItems] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch("/api/watchlist");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as { items?: string[] };
      setItems(Array.isArray(body.items) ? body.items : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const save = useCallback(async (next: string[]): Promise<void> => {
    const res = await apiFetch("/api/watchlist", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: next }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = (await res.json()) as { items?: string[] };
    setItems(Array.isArray(body.items) ? body.items : next);
  }, []);

  const add = useCallback(
    async (term: string): Promise<void> => {
      const t = term.trim();
      if (!t || items.includes(t)) return;
      await save([...items, t]);
    },
    [items, save],
  );

  const remove = useCallback(
    async (term: string): Promise<void> => {
      await save(items.filter((i) => i !== term));
    },
    [items, save],
  );

  return { items, loading, error, add, remove, refresh };
}
