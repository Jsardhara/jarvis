"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

interface TaskRow {
  id: string;
  title: string;
  tag?: string;
  due?: string;
  status?: string;
}

interface Confirmation {
  id: string;
  action: string;
  agent: string;
  ts: string;
}

const JARVIS_API =
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765";

const TAG_COLOR: Record<string, string> = {
  CODE: "var(--ops-agent-forge)",
  MAIL: "var(--ops-agent-tempo)",
  TRADE: "var(--ops-agent-atlas)",
  STUDY: "var(--ops-agent-scholar)",
  RESEARCH: "var(--ops-agent-lens)",
  ALERT: "var(--ops-crit)",
};

function colorFor(tag?: string) {
  if (!tag) return "var(--hud-cyan)";
  return TAG_COLOR[tag.toUpperCase()] ?? "var(--hud-cyan)";
}

/**
 * HUD right rail — tasks + pending confirmations.
 */
export function RightSidebar() {
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [confirms, setConfirms] = useState<Confirmation[]>([]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await apiFetch(`${JARVIS_API}/api/tasks?limit=8`);
        if (r.ok && !cancelled) {
          const j = (await r.json()) as { data?: TaskRow[] };
          setTasks(j.data ?? []);
        }
      } catch {
        /* offline tolerated */
      }
      try {
        const r2 = await apiFetch(
          `${JARVIS_API}/api/confirmations?status=pending&limit=4`,
        );
        if (r2.ok && !cancelled) {
          const j = (await r2.json()) as { data?: Confirmation[] };
          setConfirms(j.data ?? []);
        }
      } catch {
        /* offline tolerated */
      }
    };
    void tick();
    const id = setInterval(tick, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <aside
      aria-label="Tasks and confirmations"
      className="flex h-full w-full flex-col gap-3"
    >
      {/* Pending confirmations */}
      <section className="hud-panel hud-corners flex flex-col gap-1.5 px-3 py-2.5">
        <header className="hud-label flex items-center justify-between">
          <span>{"// CONFIRM"}</span>
          <span
            className="font-mono text-[9px]"
            style={{
              color: confirms.length > 0 ? "var(--ops-crit)" : "var(--ops-fg-faint)",
            }}
          >
            {confirms.length} pending
          </span>
        </header>
        {confirms.length === 0 && (
          <div className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
            queue clear
          </div>
        )}
        {confirms.slice(0, 4).map((c) => (
          <div
            key={c.id}
            className="flex items-center justify-between border-b border-[var(--ops-line-faint)] py-1 last:border-b-0"
          >
            <div>
              <div className="font-mono text-[8px] uppercase tracking-widest text-[var(--ops-crit)]">
                {c.agent}
              </div>
              <div className="line-clamp-1 font-mono text-[10px] text-[var(--ops-fg-mute)]">
                {c.action}
              </div>
            </div>
            <span className="hud-pill" style={{ color: "var(--ops-crit)" }}>
              REVIEW
            </span>
          </div>
        ))}
      </section>

      {/* Active tasks */}
      <section className="hud-panel hud-corners flex min-h-0 flex-1 flex-col gap-1.5 px-3 py-2.5">
        <header className="hud-label">{"// TASKS"}</header>
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
          {tasks.length === 0 && (
            <div className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
              no active tasks
            </div>
          )}
          {tasks.map((t) => {
            const color = colorFor(t.tag);
            return (
              <div
                key={t.id}
                className="flex items-start gap-2 border-b border-[var(--ops-line-faint)] py-1 last:border-b-0"
              >
                <span
                  aria-hidden
                  className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: color, boxShadow: `0 0 4px ${color}` }}
                />
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 font-mono text-[10px] leading-snug text-[var(--ops-fg)]">
                    {t.title}
                  </div>
                  {t.tag && (
                    <span
                      className="hud-pill mt-0.5 inline-flex"
                      style={{ color }}
                    >
                      {t.tag}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </aside>
  );
}
