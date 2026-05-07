"use client";

import { useState, useCallback } from "react";

import { apiFetch as authedFetch } from "@/lib/api-client";

// ─── Domain types ─────────────────────────────────────────────────────────────

export interface ScholarDocument {
  id: string;
  filename: string;
  page_count: number;
  flashcard_count: number;
  due_count: number;
  created_at: string;
}

export interface DocumentSummary {
  tldr: string;
  key_concepts: string[];
  important_points: string[];
}

export interface Flashcard {
  id: string;
  front: string;
  back: string;
  due_at: string | null;
  interval_days: number;
}

export type Rating = "again" | "hard" | "good" | "easy";

// ─── Fetch helpers ────────────────────────────────────────────────────────────

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await authedFetch(url, { cache: "no-store", ...init });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ─── Simple SWR-style hook factory ───────────────────────────────────────────

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function useFetch<T>(
  url: string | null,
): FetchState<T> & { refetch: () => void } {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    loading: url !== null,
    error: null,
  });
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((n) => n + 1), []);

  // We use a ref-style effect via key to avoid stale closures.
  // Re-runs whenever url or tick changes.
  const [lastUrl, setLastUrl] = useState<string | null>(null);
  const [lastTick, setLastTick] = useState(-1);

  if ((url !== lastUrl || tick !== lastTick) && url !== null) {
    setLastUrl(url);
    setLastTick(tick);
    setState((s) => ({ ...s, loading: true, error: null }));
    apiFetch<T>(url)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((err: unknown) =>
        setState({
          data: null,
          loading: false,
          error: err instanceof Error ? err.message : "Unknown error",
        }),
      );
  }

  if (url === null && state.data !== null) {
    setState({ data: null, loading: false, error: null });
  }

  return { ...state, refetch };
}

// ─── Public hooks ─────────────────────────────────────────────────────────────

export function useDocuments() {
  return useFetch<ScholarDocument[]>("/api/scholar/documents");
}

export function useDocument(id: string | null) {
  return useFetch<ScholarDocument>(id ? `/api/scholar/documents/${id}` : null);
}

export function useSummary(id: string | null) {
  return useFetch<DocumentSummary>(
    id ? `/api/scholar/documents/${id}/summary` : null,
  );
}

export function useFlashcards(id: string | null) {
  return useFetch<Flashcard[]>(
    id ? `/api/scholar/documents/${id}/flashcards` : null,
  );
}

export function useDueCards() {
  return useFetch<Flashcard[]>("/api/scholar/due");
}

// ─── Mutation hooks ───────────────────────────────────────────────────────────

interface MutationState {
  loading: boolean;
  error: string | null;
}

export function useRateCard() {
  const [state, setState] = useState<MutationState>({
    loading: false,
    error: null,
  });

  const rate = useCallback(async (cardId: string, rating: Rating) => {
    setState({ loading: true, error: null });
    try {
      await apiFetch(`/api/scholar/flashcards/${cardId}/rate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating }),
      });
      setState({ loading: false, error: null });
    } catch (err: unknown) {
      setState({
        loading: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, []);

  return { ...state, rate };
}

export function useGenerateFlashcards(docId: string | null) {
  const [state, setState] = useState<MutationState>({
    loading: false,
    error: null,
  });

  const generate = useCallback(async () => {
    if (!docId) return;
    setState({ loading: true, error: null });
    try {
      await apiFetch(`/api/scholar/documents/${docId}/flashcards`, {
        method: "POST",
      });
      setState({ loading: false, error: null });
    } catch (err: unknown) {
      setState({
        loading: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, [docId]);

  return { ...state, generate };
}

export function useUploadDocument() {
  const [state, setState] = useState<MutationState & { progress: number }>({
    loading: false,
    error: null,
    progress: 0,
  });

  const upload = useCallback(async (file: File): Promise<ScholarDocument | null> => {
    setState({ loading: true, error: null, progress: 0 });
    try {
      const fd = new FormData();
      fd.append("file", file);

      // Use XMLHttpRequest for progress tracking
      return await new Promise<ScholarDocument | null>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/scholar/documents");

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            setState((s) => ({ ...s, progress: Math.round((e.loaded / e.total) * 100) }));
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            setState({ loading: false, error: null, progress: 100 });
            resolve(JSON.parse(xhr.responseText) as ScholarDocument);
          } else {
            setState({ loading: false, error: `Upload failed: ${xhr.status}`, progress: 0 });
            reject(new Error(`Upload failed: ${xhr.status}`));
          }
        };

        xhr.onerror = () => {
          setState({ loading: false, error: "Network error", progress: 0 });
          reject(new Error("Network error"));
        };

        xhr.send(fd);
      });
    } catch (err: unknown) {
      setState({
        loading: false,
        error: err instanceof Error ? err.message : "Unknown error",
        progress: 0,
      });
      return null;
    }
  }, []);

  return { ...state, upload };
}
