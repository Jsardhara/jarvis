"use client";

import useSWR from "swr";
import { fetcher, type InboxEvent } from "@/lib/api";

export default function InboxPage() {
  const { data } = useSWR<{ events: InboxEvent[] }>("/api/inbox?limit=200", fetcher, {
    refreshInterval: 15_000,
  });
  const events = (data?.events ?? []).slice().reverse();

  return (
    <>
      <h1>Inbox queue</h1>
      <p className="muted">Daemon-flagged events. Refreshes every 15s.</p>
      <div className="card">
        {events.length === 0 ? (
          <p className="muted">No events yet.</p>
        ) : (
          events.map((e) => (
            <div key={e.ts + e.agent} className="row">
              <span className={`severity severity-${e.severity}`} />
              <span className="mono muted">{new Date(e.ts).toLocaleTimeString()}</span>
              <span className="mono muted">{e.agent}</span>
              <span>{e.summary}</span>
            </div>
          ))
        )}
      </div>
    </>
  );
}
