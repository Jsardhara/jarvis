"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

export interface TempoEvent {
  id: string;
  summary: string;
  start: string;
  end: string;
  attendees?: string[];
  location?: string;
  description?: string;
}

export interface TempoMailItem {
  id: string;
  from: string;
  subject: string;
  reason?: string;
  body_preview?: string;
}

export interface TempoTriageResult {
  action_required: TempoMailItem[];
  info_only: TempoMailItem[];
  noise: TempoMailItem[];
  counts: { action_required: number; info_only: number; noise: number };
}

export interface TempoTask {
  id: string;
  title: string;
  due: string | null;
  tags: string[];
  status: string;
  created: string;
  updated: string;
}

const POLL_MS = 30_000;

async function dispatch<T = unknown>(action: string, args: Record<string, unknown> = {}): Promise<T> {
  const res = await apiFetch("/api/agents/tempo/dispatch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, args }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as { result: T };
  return body.result;
}

export function useTempoToday(): { events: TempoEvent[]; loading: boolean; error: string | null; refresh: () => Promise<void> } {
  const [events, setEvents] = useState<TempoEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await dispatch<{ events: TempoEvent[] }>("today");
      setEvents(Array.isArray(result.events) ? result.events : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "calendar fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return { events, loading, error, refresh };
}

export function useTempoTriage(): {
  data: TempoTriageResult | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
} {
  const [data, setData] = useState<TempoTriageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      // triage_status reads cached classifications without re-running the LLM —
      // ideal for a periodic dashboard refresh.
      const status = await dispatch<{
        counts: { action_required: number; info_only: number; noise: number };
        top_action_required: { id: string; reason?: string }[];
      }>("triage_status");
      setData({
        action_required: (status.top_action_required ?? []).map((r) => ({
          id: r.id,
          subject: "(cached)",
          from: "",
          reason: r.reason ?? "",
        })),
        info_only: [],
        noise: [],
        counts: status.counts,
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "triage fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const runFreshTriage = useCallback(async () => {
    try {
      setLoading(true);
      const fresh = await dispatch<TempoTriageResult>("triage_smart", { max_results: 25 });
      setData(fresh);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "triage_smart failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return { data, loading, error, refresh: runFreshTriage };
}

export function useTempoTasks(): {
  tasks: TempoTask[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  add: (title: string) => Promise<void>;
  complete: (taskId: string) => Promise<void>;
} {
  const [tasks, setTasks] = useState<TempoTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await dispatch<{ tasks: TempoTask[] }>("list_open");
      setTasks(Array.isArray(result.tasks) ? result.tasks : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "task fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const add = useCallback(
    async (title: string) => {
      const t = title.trim();
      if (!t) return;
      await dispatch("add", { title: t });
      await refresh();
    },
    [refresh],
  );

  const complete = useCallback(
    async (taskId: string) => {
      await dispatch("complete", { task_id: taskId });
      await refresh();
    },
    [refresh],
  );

  return { tasks, loading, error, refresh, add, complete };
}
