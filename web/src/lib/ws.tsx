"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { TraceEvent } from "./api";

type WsStatus = "connecting" | "connected" | "disconnected";

type Listener = (msg: TraceEvent | { type: "dispatch"; request: string; result: unknown }) => void;

interface WsClient {
  status: WsStatus;
  subscribe: (fn: Listener) => () => void;
}

const WsContext = createContext<WsClient | null>(null);

export function WsProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const listenersRef = useRef<Set<Listener>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let alive = true;
    let retryMs = 1000;

    const connect = () => {
      if (!alive) return;
      const url = (() => {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const host = window.location.hostname;
        // Backend runs on 8765; in dev next is on 3000
        return `${proto}://${host}:8765/ws`;
      })();
      setStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!alive) return;
        retryMs = 1000;
        setStatus("connected");
      };
      ws.onclose = () => {
        if (!alive) return;
        setStatus("disconnected");
        wsRef.current = null;
        setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, 8000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          for (const fn of listenersRef.current) fn(msg);
        } catch {
          // ignore
        }
      };
    };

    connect();

    return () => {
      alive = false;
      wsRef.current?.close();
    };
  }, []);

  const value = useMemo<WsClient>(
    () => ({
      status,
      subscribe: (fn) => {
        listenersRef.current.add(fn);
        return () => {
          listenersRef.current.delete(fn);
        };
      },
    }),
    [status]
  );

  return <WsContext.Provider value={value}>{children}</WsContext.Provider>;
}

export function useWs(): WsClient {
  const ctx = useContext(WsContext);
  if (!ctx) throw new Error("useWs must be used within WsProvider");
  return ctx;
}

/** Convenience: subscribe to a typed slice of events. */
export function useTraceEvents(handler: (e: TraceEvent) => void) {
  const ws = useWs();
  useEffect(() => {
    return ws.subscribe((msg) => {
      if (msg && typeof msg === "object" && "type" in msg && msg.type !== "dispatch") {
        handler(msg as TraceEvent);
      }
    });
  }, [ws, handler]);
}
