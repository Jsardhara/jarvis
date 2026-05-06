"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

export interface ForgeSpec {
  slug: string;
  title: string;
  news_url?: string;
  news_source?: string;
  spec_md?: string;
}

export interface ForgeDailyRun {
  ts: string;
  date: string;
  status: "success" | "failed" | "skipped_budget" | "blocked" | string;
  error?: string;
  spec?: ForgeSpec;
  pr_url?: string;
}

export interface ForgeSnapshot {
  daily_runs: ForgeDailyRun[];
  next_daily_iso: string;
  status_counts: Record<string, number>;
}

const POLL_MS = 15_000;

const EMPTY: ForgeSnapshot = {
  daily_runs: [],
  next_daily_iso: "",
  status_counts: {},
};

export function useForgeSnapshot(): {
  snapshot: ForgeSnapshot;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
} {
  const [snapshot, setSnapshot] = useState<ForgeSnapshot>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch("/api/forge/snapshot?limit=30");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as ForgeSnapshot;
      setSnapshot(body);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return { snapshot, loading, error, refresh };
}
