"use client";

import type { CSSProperties } from "react";
import type { SentinelJob } from "@/hooks/useSentinelSnapshot";
import { Hatch, AgentGlyph, getAgentIdentity } from "@/components/ops";

/**
 * Estimates the next-fire time for each known job.
 *
 * The Python sentinel does not expose APScheduler's true next-run timestamps
 * over HTTP, so we approximate using the documented intervals from
 * `jarvis/daemon/sentinel.py:104-130`. Drift accumulates between heartbeats —
 * acceptable for a status-board read.
 */
const INTERVAL_MIN: Record<string, number> = {
  email: 15,
  calendar: 60,
  atlas: 5,
  atlas_health: 1,
  news: 30,
  scholar: 120,
  heartbeat: 1,
  mc_sync: 0.5,
  triggers: 30,
};

const CRON_HOUR_UTC: Record<string, number> = {
  morning: 8,
  evening: 18,
  daily_forge: 10,
};

function nextFireTs(job: SentinelJob, now: Date): Date | null {
  if (job.name in INTERVAL_MIN) {
    return new Date(now.getTime() + INTERVAL_MIN[job.name] * 60_000);
  }
  if (job.name in CRON_HOUR_UTC) {
    const h = CRON_HOUR_UTC[job.name];
    const next = new Date(now);
    next.setUTCHours(h, 0, 0, 0);
    if (next.getTime() <= now.getTime()) {
      next.setUTCDate(next.getUTCDate() + 1);
    }
    return next;
  }
  return null;
}

const JOB_TARGETS: Record<string, string> = {
  email: "tempo",
  calendar: "tempo",
  atlas: "atlas",
  atlas_health: "atlas",
  news: "lens",
  scholar: "scholar",
  morning: "jarvis",
  evening: "jarvis",
  heartbeat: "sentinel",
  mc_sync: "sentinel",
  triggers: "sentinel",
  daily_forge: "forge",
};

interface Props {
  jobs: SentinelJob[];
  /** Visible row count. Default 8. */
  limit?: number;
}

export function ScheduleTimeline({ jobs, limit = 8 }: Props) {
  const now = new Date();
  const enriched = jobs
    .map((j) => ({ job: j, fires: nextFireTs(j, now) }))
    .filter((x): x is { job: SentinelJob; fires: Date } => x.fires !== null)
    .sort((a, b) => a.fires.getTime() - b.fires.getTime())
    .slice(0, limit);

  if (enriched.length === 0) {
    return <Hatch label="NO UPCOMING FIRES" height={80} />;
  }

  return (
    <div style={{ position: "relative", paddingLeft: 64 } as CSSProperties}>
      <div
        style={{
          position: "absolute",
          left: 54,
          top: 0,
          bottom: 0,
          width: 1,
          background: "var(--ops-line-bright)",
        }}
      />
      {enriched.map(({ job, fires }, i) => {
        const time = fires.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const target = JOB_TARGETS[job.name] ?? null;
        const identity = target ? getAgentIdentity(target) : null;
        const dotColor = identity?.colorHex ?? "var(--ops-fg)";
        const pt = i === 0 ? 4 : 16;
        const ageMs = fires.getTime() - now.getTime();
        const inSec = Math.max(0, Math.round(ageMs / 1000));
        const eta =
          inSec < 60 ? `${inSec}s` : inSec < 3600 ? `${Math.round(inSec / 60)}m` : `${(inSec / 3600).toFixed(1)}h`;
        return (
          <div
            key={job.name}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 12,
              position: "relative",
              paddingTop: pt,
            }}
          >
            <span
              style={{
                position: "absolute",
                left: -58,
                top: pt,
                fontFamily: "var(--ops-mono)",
                fontSize: 10,
                color: "var(--ops-amber)",
                width: 48,
                textAlign: "right",
                lineHeight: "14px",
              }}
            >
              {time}
            </span>
            <div
              style={{
                position: "absolute",
                left: -14,
                top: pt + 3,
                width: 9,
                height: 9,
                borderRadius: "50%",
                background: dotColor,
                boxShadow: `0 0 6px ${dotColor}`,
              }}
            />
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--ops-fg)",
                  fontFamily: "var(--ops-mono)",
                  lineHeight: "14px",
                }}
              >
                {job.name}
                <span style={{ color: "var(--ops-fg-mute)", marginLeft: 6 }}>· in {eta}</span>
              </div>
              {identity && (
                <div
                  style={{
                    fontSize: 10,
                    color: identity.colorHex,
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    marginTop: 2,
                  }}
                >
                  <AgentGlyph agent={identity} size={10} />
                  {identity.name}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
