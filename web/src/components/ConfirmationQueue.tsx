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

  return (
    <aside className="mc-confirmations">
      <h2>pending confirmations</h2>
      <div className="conf-list">
        {(data ?? []).length === 0 && (
          <div className="muted">nothing waiting</div>
        )}
        {(data ?? []).slice().reverse().map((c) => (
          <div className="conf-card" key={c.id}>
            <div className="conf-head">
              <span className="conf-agent">{c.agent}</span>
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
        ))}
      </div>
    </aside>
  );
}
