"use client";

import useSWR from "swr";
import { fetcher, type InboxEvent, type Task } from "@/lib/api";

export default function BriefingPage() {
  const { data: inbox } = useSWR<{ events: InboxEvent[] }>("/api/inbox?limit=20", fetcher, {
    refreshInterval: 30_000,
  });
  const { data: tasks } = useSWR<{ tasks: Task[] }>("/api/tasks", fetcher, {
    refreshInterval: 60_000,
  });

  const open = (tasks?.tasks ?? []).filter((t) => t.status === "open");
  const recent = (inbox?.events ?? []).slice(-8).reverse();
  const alerts = recent.filter((e) => e.severity === "alert");

  return (
    <>
      <h1>Morning briefing</h1>
      <div className="grid">
        <section className="card">
          <h2>Alerts</h2>
          {alerts.length === 0 ? (
            <p className="muted">All clear.</p>
          ) : (
            alerts.map((e) => (
              <div key={e.ts} className="row">
                <span className="severity severity-alert" />
                <span className="mono muted">{e.agent}</span>
                <span>{e.summary}</span>
              </div>
            ))
          )}
        </section>

        <section className="card">
          <h2>Open tasks</h2>
          {open.length === 0 ? (
            <p className="muted">Inbox zero.</p>
          ) : (
            open.slice(0, 8).map((t) => (
              <div key={t.id} className="row">
                <span>{t.title}</span>
                {t.due && <span className="muted">{new Date(t.due).toLocaleDateString()}</span>}
              </div>
            ))
          )}
        </section>

        <section className="card">
          <h2>Recent activity</h2>
          {recent.length === 0 ? (
            <p className="muted">Daemon hasn’t logged anything yet. Run sentinel.</p>
          ) : (
            recent.map((e) => (
              <div key={e.ts} className="row">
                <span className={`severity severity-${e.severity}`} />
                <span className="mono muted">{e.agent}</span>
                <span>{e.summary}</span>
              </div>
            ))
          )}
        </section>
      </div>
    </>
  );
}
