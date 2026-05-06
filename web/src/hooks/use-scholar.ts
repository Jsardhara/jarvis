"use client";

/**
 * Scholar workspace hooks — typed against the backend API contract.
 *
 * All fetches go through `apiFetch`, which routes via the Next.js proxy
 * (relative `/api/scholar/*` URLs) and attaches the dashboard bearer
 * token. The `[...path]` catch-all proxy at
 * `web/src/app/api/scholar/[...path]/route.ts` forwards anything that
 * doesn't have a dedicated route file to FastAPI on :8765 with the
 * trusted backend token swapped in.
 */

import { useState, useCallback, useEffect, useRef } from "react";

import { apiFetch } from "@/lib/api-client";

// ─── Domain types ─────────────────────────────────────────────────────────────

// Backend shape from /api/scholar/due and /api/scholar/rate
export interface DueCard {
  /** Card primary key — field is `id` on the wire */
  id: string;
  /** Alias kept for callers that used the old field name */
  card_id?: string;
  doc_id: string;
  front: string;
  back: string;
  /** Field name on the wire is `tags` */
  tags: string[];
  /** Alias kept for callers */
  concept_tags?: string[];
  ease_factor: number;
  interval: number;
  repetitions: number;
  /** ISO date string — e.g. "2026-04-29" */
  due_date: string;
  created_at: string;
}

// /api/scholar/rate returns the same full card dict after SM-2 update
export type RateCardResult = DueCard;

// Shape returned by /api/scholar/docs
export interface ScholarDoc {
  id: string;
  title: string;
  filename: string;
  page_count: number;
  content_text?: string;
  created_at: string;
}

export interface DocSummary {
  summary: string;
  key_concepts: string[];
}

export interface SolveResult {
  id: string;
  steps: string[];
  final_answer: string;
  concepts_used: string[];
}

export interface RateProblemResult {
  problem_id: string;
  correct: boolean;
  weak_topics_after: string[];
}

export interface WeakTopic {
  concept: string;
  miss_count: number;
  last_seen: string;
  sample_problem_ids: string[];
}

export interface WeakTopicsResult {
  weak_topics: WeakTopic[];
}

export interface ExamProblem {
  id: string;
  /** Backend field name is `prompt` */
  prompt: string;
  /** Alias for components that use `problem` */
  problem?: string;
  solution?: string;
  expected_concepts?: string[];
}

export interface ExamSession {
  session_id: string;
  started_iso: string;
  ends_iso: string;
  problems: ExamProblem[];
}

export interface SeedResult {
  seed_name: string;
  doc_id: string;
  /** Number of cards imported */
  cards_imported: number;
  cards: { id: string; front: string; back: string; tags: string[] }[];
}

/** Alias kept for backwards compat */
export type { SeedResult as LegacySeedResult };

// ─── Fetch helper ─────────────────────────────────────────────────────────────

async function scholarFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, {
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(text || `HTTP ${res.status}`);
  }
  const body: unknown = await res.json();
  // Backend wraps every response as { data, error }. Unwrap.
  if (
    body !== null &&
    typeof body === "object" &&
    "data" in body &&
    "error" in body
  ) {
    const env = body as { data: T; error: string | null };
    if (env.error) throw new Error(env.error);
    return env.data;
  }
  return body as T;
}

// ─── Fetch state ──────────────────────────────────────────────────────────────

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function useFetch<T>(
  path: string | null,
): FetchState<T> & { refetch: () => void } {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    loading: path !== null,
    error: null,
  });
  const [rev, setRev] = useState(0);
  const refetch = useCallback(() => setRev((n) => n + 1), []);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    scholarFetch<T>(path)
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setState({
            data: null,
            loading: false,
            error: err instanceof Error ? err.message : "Unknown error",
          });
      });
    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, rev]);

  return { ...state, refetch };
}

// ─── Mutation state ───────────────────────────────────────────────────────────

interface MutState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function useMutation<TIn, TOut>(
  buildPath: (input: TIn) => string,
  method: string = "POST",
): MutState<TOut> & { mutate: (input: TIn, body?: unknown) => Promise<TOut | null> } {
  const [state, setState] = useState<MutState<TOut>>({
    data: null,
    loading: false,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const mutate = useCallback(
    async (input: TIn, body?: unknown): Promise<TOut | null> => {
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      setState({ data: null, loading: true, error: null });
      try {
        const data = await scholarFetch<TOut>(buildPath(input), {
          method,
          headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
          body: body !== undefined ? JSON.stringify(body) : undefined,
          signal: abortRef.current.signal,
        });
        setState({ data, loading: false, error: null });
        return data;
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return null;
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState({ data: null, loading: false, error: msg });
        return null;
      }
    },
    // buildPath is stable per call site (defined inline), so no dep needed here
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  return { ...state, mutate };
}

// ─── Public hooks ─────────────────────────────────────────────────────────────

export function useDueCards(course?: string) {
  const q = course ? `?course=${encodeURIComponent(course)}` : "";
  return useFetch<DueCard[]>(`/api/scholar/due${q}`);
}

export function useWeakTopics(topN: number = 8, course?: string) {
  const q = course ? `&course=${encodeURIComponent(course)}` : "";
  return useFetch<WeakTopicsResult>(`/api/scholar/weak?top_n=${topN}${q}`);
}

export function useScholarDocs() {
  return useFetch<ScholarDoc[]>("/api/scholar/docs");
}

// ─── Mutation hooks ───────────────────────────────────────────────────────────

export function useRateDueCard() {
  const [state, setState] = useState<MutState<RateCardResult>>({
    data: null,
    loading: false,
    error: null,
  });

  const rate = useCallback(
    async (cardId: string, rating: 0 | 1 | 2 | 3 | 4 | 5): Promise<RateCardResult | null> => {
      setState({ data: null, loading: true, error: null });
      try {
        const data = await scholarFetch<RateCardResult>("/api/scholar/rate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ card_id: cardId, rating }),
        });
        setState({ data, loading: false, error: null });
        return data;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState({ data: null, loading: false, error: msg });
        return null;
      }
    },
    [],
  );

  return { ...state, rate };
}

export function useSolveProblem() {
  const [state, setState] = useState<MutState<SolveResult>>({
    data: null,
    loading: false,
    error: null,
  });

  const solve = useCallback(
    async (problem: string, course?: string): Promise<SolveResult | null> => {
      setState({ data: null, loading: true, error: null });
      try {
        const data = await scholarFetch<SolveResult>("/api/scholar/solve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ problem, course }),
        });
        setState({ data, loading: false, error: null });
        return data;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState({ data: null, loading: false, error: msg });
        return null;
      }
    },
    [],
  );

  return { ...state, solve };
}

export function useRateProblem() {
  const [state, setState] = useState<MutState<RateProblemResult>>({
    data: null,
    loading: false,
    error: null,
  });

  const rateProblem = useCallback(
    async (problemId: string, correct: boolean): Promise<RateProblemResult | null> => {
      setState({ data: null, loading: true, error: null });
      try {
        const data = await scholarFetch<RateProblemResult>(
          "/api/scholar/rate-problem",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ problem_id: problemId, correct }),
          },
        );
        setState({ data, loading: false, error: null });
        return data;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState({ data: null, loading: false, error: msg });
        return null;
      }
    },
    [],
  );

  return { ...state, rateProblem };
}

export function useStartExam() {
  const [state, setState] = useState<MutState<ExamSession>>({
    data: null,
    loading: false,
    error: null,
  });

  const startExam = useCallback(
    async (
      course: string,
      durationMin: number,
      problemCount: number,
    ): Promise<ExamSession | null> => {
      setState({ data: null, loading: true, error: null });
      try {
        const data = await scholarFetch<ExamSession>("/api/scholar/exam", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            course,
            duration_min: durationMin,
            problem_count: problemCount,
          }),
        });
        setState({ data, loading: false, error: null });
        return data;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState({ data: null, loading: false, error: msg });
        return null;
      }
    },
    [],
  );

  return { ...state, startExam };
}

export function useImportSeed() {
  return useMutation<{ seedName: string; course?: string }, SeedResult>(
    ({ seedName, course }) => {
      const q = course ? `?course=${encodeURIComponent(course)}` : "";
      return `/api/scholar/seed/${seedName}${q}`;
    },
  );
}

export { scholarFetch };
