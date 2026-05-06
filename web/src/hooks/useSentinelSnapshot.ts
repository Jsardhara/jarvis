"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

export interface SentinelJob {
  name: string;
  status: string;
}

export interface SentinelHeartbeat {
  ts: string;
  job_count: number;
  jobs: Record<string, string>;
}

export interface SentinelInboxEvent {
  ts: string;
  agent: string;
  severity: string;
  summary: string;
  ref: Record<string, unknown>;
}

export interface SentinelSnapshot {
  last_heartbeat: string | null;
  jobs: SentinelJob[];
  heartbeats: SentinelHeartbeat[];
  events: SentinelInboxEvent[];
}

const POLL_MS = 5000;

const EMPTY: SentinelSnapshot = {
  last_heartbeat: null,
  jobs: [],
  heartbeats: [],
  events: [],
};

export function useSentinelSnapshot(opts?: {
  eventsLimit?: number;
  heartbeatLimit?: number;
}): {
  snapshot: SentinelSnapshot;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
} {
  const eventsLimit = opts?.eventsLimit ?? 80;
  const heartbeatLimit = opts?.heartbeatLimit ?? 60;
  const [snapshot, setSnapshot] = useState<SentinelSnapshot>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch(
        `/api/sentinel/snapshot?events_limit=${eventsLimit}&heartbeat_limit=${heartbeatLimit}`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as SentinelSnapshot;
      setSnapshot(body);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "fetch failed");
    } finally {
      setLoading(false);
    }
  }, [eventsLimit, heartbeatLimit]);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return { snapshot, loading, error, refresh };
}
