"use client";

import { useState, useEffect, useRef } from "react";
import type { AtlasSnapshot } from "@/lib/types";

const POLL_INTERVAL_MS = 30_000;
const FETCH_TIMEOUT_MS = 8_000;

export interface AtlasSnapshotState {
  snapshot: AtlasSnapshot | null;
  degraded: boolean;
  isLoading: boolean;
  error: Error | null;
}

/**
 * Polls /api/atlas/snapshot every 30 s.
 *
 * Returns degraded=true when:
 * - The response payload contains degraded: true
 * - The fetch fails (network error, timeout)
 * - The server returns a non-OK status
 *
 * Renders nothing if ATLAS is healthy — caller decides presentation.
 */
export function useAtlasSnapshot(): AtlasSnapshotState {
  const [state, setState] = useState<AtlasSnapshotState>({
    snapshot: null,
    degraded: false,
    isLoading: true,
    error: null,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const fetchSnapshot = async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    try {
      const res = await fetch("/api/atlas/snapshot", {
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!res.ok) {
        if (mountedRef.current) {
          setState((prev) => ({
            ...prev,
            degraded: true,
            isLoading: false,
            error: new Error(`HTTP ${res.status}`),
          }));
        }
        return;
      }

      const data: AtlasSnapshot = await res.json() as AtlasSnapshot;

      if (mountedRef.current) {
        setState({
          snapshot: data,
          degraded: data.degraded,
          isLoading: false,
          error: null,
        });
      }
    } catch (err) {
      clearTimeout(timeout);
      if (mountedRef.current) {
        setState((prev) => ({
          ...prev,
          degraded: true,
          isLoading: false,
          error: err instanceof Error ? err : new Error("fetch failed"),
        }));
      }
    }
  };

  useEffect(() => {
    mountedRef.current = true;

    void fetchSnapshot();

    intervalRef.current = setInterval(() => {
      void fetchSnapshot();
    }, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}
