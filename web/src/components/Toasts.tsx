"use client";

import { useCallback, useEffect, useState } from "react";
import { useTraceEvents } from "@/lib/ws";

type Toast = { id: string; text: string; agent: string };

export function Toasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const handler = useCallback((e: { type: string; agent?: string | null; payload?: Record<string, unknown> }) => {
    if (e.type !== "confirmation.created") return;
    const conf = (e.payload?.confirmation ?? {}) as { id?: string; intent?: string; summary?: string };
    const id = conf.id ?? crypto.randomUUID();
    const text = conf.summary || conf.intent || "needs confirmation";
    setToasts((arr) => [...arr, { id, text, agent: e.agent ?? "?" }]);
    setTimeout(() => setToasts((arr) => arr.filter((t) => t.id !== id)), 6000);
  }, []);
  useTraceEvents(handler);

  useEffect(() => () => setToasts([]), []);

  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <div key={t.id} className="toast">
          <div className="muted" style={{ fontSize: "0.7rem", textTransform: "uppercase" }}>
            {t.agent} · needs confirm
          </div>
          {t.text}
        </div>
      ))}
    </div>
  );
}
