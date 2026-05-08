"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

const JARVIS_API =
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765");

interface Confirmation {
  id: string;
  agent: string;
  intent?: string;
  summary?: string;
  args?: Record<string, unknown>;
  status: "pending" | "approved" | "rejected";
  ts?: string;
}

async function fetchPending(): Promise<Confirmation[]> {
  try {
    const r = await apiFetch(
      `${JARVIS_API}/api/confirmations?status=pending`
    );
    if (!r.ok) return [];
    const json = (await r.json()) as {
      confirmations?: Confirmation[];
      items?: Confirmation[];
    };
    return json.confirmations ?? json.items ?? [];
  } catch {
    return [];
  }
}

async function resolve(id: string, kind: "approve" | "reject"): Promise<void> {
  try {
    await apiFetch(`${JARVIS_API}/api/confirmations/${id}/${kind}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
    });
  } catch {
    // best effort — UI will refresh on next poll/event
  }
}

export function ConfirmationDeck() {
  const [items, setItems] = useState<Confirmation[]>([]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const next = await fetchPending();
      if (!cancelled) setItems(next);
    };
    tick();
    const interval = setInterval(tick, 5_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const lifted = items.length > 0;

  return (
    <section
      aria-label="Confirmation deck"
      className="ops-panel flex flex-col gap-2 px-3 py-2"
      style={{
        background: lifted
          ? "var(--ops-bg-elevated)"
          : "var(--ops-bg-panel)",
        boxShadow: lifted ? "0 8px 28px rgba(242, 160, 61, 0.12)" : "none",
        transition: "box-shadow 220ms ease, background 220ms ease",
      }}
    >
      <header className="flex items-center justify-between text-[11px] uppercase tracking-wide text-[var(--ops-fg-mute)]">
        <span className="font-mono">CONFIRM</span>
        <span className="font-mono text-[var(--ops-fg-dim)]">
          {items.length}
        </span>
      </header>

      {items.length === 0 && (
        <p className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
          no pending approvals
        </p>
      )}

      <AnimatePresence>
        {items.map((c) => (
          <motion.div
            key={c.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
            className="border border-[var(--ops-line-faint)] p-2"
          >
            <div className="mb-1 flex items-center justify-between text-[10px] font-mono uppercase">
              <span className="text-[var(--ops-amber)]">{c.agent}</span>
              <span className="text-[var(--ops-fg-faint)]">
                {c.intent ?? ""}
              </span>
            </div>
            <p className="mb-2 font-mono text-[11px] text-[var(--ops-fg)]">
              {c.summary ?? "(no summary)"}
            </p>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() =>
                  resolve(c.id, "approve").then(() =>
                    setItems((prev) => prev.filter((x) => x.id !== c.id))
                  )
                }
                className="flex-1 border border-[var(--ops-ok)] bg-[var(--ops-bg-panel)] py-1 font-mono text-[10px] uppercase text-[var(--ops-ok)] hover:bg-[var(--ops-bg-deep)]"
              >
                approve
              </button>
              <button
                type="button"
                onClick={() =>
                  resolve(c.id, "reject").then(() =>
                    setItems((prev) => prev.filter((x) => x.id !== c.id))
                  )
                }
                className="border border-[var(--ops-line-faint)] px-2 py-1 font-mono text-[10px] uppercase text-[var(--ops-fg-dim)] hover:text-[var(--ops-fg)]"
              >
                reject
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </section>
  );
}
