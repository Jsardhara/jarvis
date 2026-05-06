"use client";

import type { CSSProperties } from "react";
import type { SentinelJob } from "@/hooks/useSentinelSnapshot";
import { Dot, Hatch, getAgentIdentity } from "@/components/ops";

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

const JOB_DESCRIPTIONS: Record<string, string> = {
  email: "MAIL TRIAGE · 15M",
  calendar: "CAL SYNC · 1H",
  atlas: "ATLAS TICK · 5M",
  atlas_health: "ATLAS HEALTH · 1M",
  news: "NEWS SCAN · 30M",
  scholar: "STUDY POLL · 2H",
  morning: "DIGEST · 08:00 UTC",
  evening: "DIGEST · 18:00 UTC",
  heartbeat: "HEARTBEAT · 1M",
  mc_sync: "MC SYNC · 30S",
  triggers: "TRIGGERS · 30M",
  daily_forge: "DAILY FORGE · 10:00 UTC",
};

function statusKind(status: string): "ok" | "warn" | "crit" | "idle" {
  if (status === "scheduled" || status === "running") return "ok";
  if (status === "missed") return "warn";
  if (status === "error" || status === "failed") return "crit";
  return "idle";
}

interface Props {
  jobs: SentinelJob[];
  lastHeartbeat: string | null;
}

export function JobGrid({ jobs, lastHeartbeat }: Props) {
  if (jobs.length === 0) return <Hatch label="DAEMON OFFLINE — NO HEARTBEAT" height={120} />;

  const heartbeatAge = lastHeartbeat
    ? Math.max(0, Math.round((Date.now() - new Date(lastHeartbeat).getTime()) / 1000))
    : null;
  const stale = heartbeatAge !== null && heartbeatAge > 120;

  const cellStyle: CSSProperties = {
    border: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
    padding: "10px 12px",
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 4,
  };

  return (
    <div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
          gap: 8,
          padding: 8,
        }}
      >
        {jobs.map((job) => {
          const target = JOB_TARGETS[job.name] ?? null;
          const identity = target ? getAgentIdentity(target) : null;
          const desc = JOB_DESCRIPTIONS[job.name] ?? job.status.toUpperCase();
          const kind = stale ? "warn" : statusKind(job.status);
          const accent = identity?.colorHex ?? "var(--ops-fg)";
          return (
            <div key={job.name} style={cellStyle}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Dot kind={kind} />
                <span
                  style={{
                    fontFamily: "var(--ops-mono)",
                    fontSize: 11,
                    color: "var(--ops-fg)",
                    letterSpacing: "0.04em",
                    flex: 1,
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {job.name}
                </span>
              </div>
              <div
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: "var(--ops-fg-mute)",
                  letterSpacing: "0.08em",
                }}
              >
                {desc}
              </div>
              {identity && (
                <div
                  style={{
                    fontFamily: "var(--ops-mono)",
                    fontSize: 9,
                    color: accent,
                    letterSpacing: "0.06em",
                  }}
                >
                  → {identity.name}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div
        style={{
          padding: "6px 12px",
          fontFamily: "var(--ops-mono)",
          fontSize: 9,
          color: stale ? "var(--ops-crit)" : "var(--ops-fg-mute)",
          letterSpacing: "0.08em",
          borderTop: "1px solid var(--ops-line)",
        }}
      >
        LAST HEARTBEAT:{" "}
        {heartbeatAge === null
          ? "—"
          : heartbeatAge < 60
            ? `${heartbeatAge}s ago`
            : `${Math.floor(heartbeatAge / 60)}m ${heartbeatAge % 60}s ago`}
        {stale ? " · STALE" : ""}
      </div>
    </div>
  );
}
