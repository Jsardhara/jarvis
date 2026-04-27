"use client";

import { useCallback } from "react";
import useSWR from "swr";
import {
  approveConfirmation,
  listConfirmations,
  rejectConfirmation,
  type Confirmation,
} from "@/lib/api";
import { useTraceEvents } from "@/lib/ws";
import { TierBadge, type Tier } from "./TierBadge";

function tierFromConfirmation(c: Confirmation): Tier {
  const raw = (c.args as Record<string, unknown>)?.tier;
  if (typeof raw === "number" && raw >= 1 && raw <= 5) return raw as Tier;
  return 5;
}

export function ConfirmationQueue() {
  const { data, mutate } = useSWR<Confirmation[]>(
    "confirmations:pending",
    () => listConfirmations("pending"),
    { refreshInterval: 5000 }
  );

  const handleEvent = useCallback(
    (e: { type: string }) => {
      if (e.type === "confirmation.created" || e.type === "confirmation.resolved") {
        void mutate();
      }
    },
    [mutate]
  );
  useTraceEvents(handleEvent);

  const onApprove = async (id: string) => {
    await approveConfirmation(id);
    await mutate();
  };
  const onReject = async (id: string) => {
    await rejectConfirmation(id);
    await mutate();
  };

  const items = data ?? [];
  const hasItems = items.length > 0;

  return (
    <aside className={`mc-confirmations${hasItems ? " has-items" : ""}`}>
      <h2>pending confirmations</h2>
      <div className="conf-list">
        {items.length === 0 && (
          <div className="muted">nothing waiting</div>
        )}
        {items.slice().reverse().map((c) => {
          const tier = tierFromConfirmation(c);
          return (
            <div className="conf-card" key={c.id} data-tier={tier}>
              <div className="conf-head">
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <TierBadge tier={tier} />
                  <span className="conf-agent">{c.agent}</span>
                </div>
                <span className="muted">{new Date(c.ts).toLocaleTimeString()}</span>
              </div>
              <div className="conf-summary">
                {c.intent}
                {c.summary ? ` — ${c.summary}` : ""}
              </div>
              <div className="conf-actions">
                <button className="approve" onClick={() => void onApprove(c.id)}>
                  approve
                </button>
                <button className="reject" onClick={() => void onReject(c.id)}>
                  reject
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
