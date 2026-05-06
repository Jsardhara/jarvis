"use client";

/**
 * /sentinel — daemon mission control
 *
 * Job grid + heartbeat sparkline + live event ticker + upcoming-fire schedule.
 * Reads /api/sentinel/snapshot which bundles inbox.jsonl + sentinel_health.jsonl.
 */

import type { CSSProperties } from "react";
import { useSentinelSnapshot } from "@/hooks/useSentinelSnapshot";
import { Panel, AgentGlyph, Tag, getAgentIdentity, Scanline } from "@/components/ops";
import { JobGrid } from "@/components/sentinel/JobGrid";
import { HeartbeatSpark } from "@/components/sentinel/HeartbeatSpark";
import { EventTicker } from "@/components/sentinel/EventTicker";
import { ScheduleTimeline } from "@/components/sentinel/ScheduleTimeline";

const sentinel = getAgentIdentity("sentinel")!;

export default function SentinelPage() {
  const { snapshot, loading, error } = useSentinelSnapshot({
    eventsLimit: 100,
    heartbeatLimit: 60,
  });

  const lastTs = snapshot.last_heartbeat
    ? new Date(snapshot.last_heartbeat).getTime()
    : null;
  const ageSec = lastTs ? Math.round((Date.now() - lastTs) / 1000) : null;
  const live = ageSec !== null && ageSec < 90;
  const statusKind: "ok" | "amber" | "crit" =
    ageSec === null ? "crit" : live ? "ok" : "amber";
  const statusLabel =
    ageSec === null ? "OFFLINE" : live ? "LIVE" : `STALE ${ageSec}S`;

  const headerStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 16px",
    borderBottom: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
    position: "relative",
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      }}
    >
      <header style={headerStyle}>
        <Scanline />
        <AgentGlyph agent={sentinel} size={22} />
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 13,
              letterSpacing: "0.12em",
              color: sentinel.colorHex,
            }}
          >
            SENTINEL · {sentinel.role}
          </span>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 10,
              color: "var(--ops-fg-mute)",
              letterSpacing: "0.06em",
            }}
          >
            {sentinel.tagline}
          </span>
        </div>
        <span style={{ marginLeft: "auto" }}>
          <Tag kind={statusKind}>{statusLabel}</Tag>
        </span>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-mute)",
            letterSpacing: "0.06em",
          }}
        >
          {snapshot.jobs.length} JOBS
        </span>
      </header>

      {error && (
        <div
          style={{
            padding: "8px 16px",
            background: "rgba(255, 90, 90, 0.08)",
            color: "var(--ops-crit)",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
          }}
        >
          fetch error: {error}
        </div>
      )}

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          gap: 12,
          padding: 12,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
          <Panel
            title="JOB GRID"
            trailing={
              <span
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: "var(--ops-fg-mute)",
                  letterSpacing: "0.08em",
                }}
              >
                APSCHEDULER · UTC
              </span>
            }
            flushBody
          >
            <JobGrid jobs={snapshot.jobs} lastHeartbeat={snapshot.last_heartbeat} />
          </Panel>

          <Panel
            title="EVENT TICKER"
            trailing={
              <span
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: "var(--ops-fg-mute)",
                  letterSpacing: "0.08em",
                }}
              >
                INBOX TAIL · HEARTBEATS HIDDEN
              </span>
            }
            flushBody
          >
            {loading ? (
              <div
                style={{
                  padding: 20,
                  textAlign: "center",
                  fontFamily: "var(--ops-mono)",
                  fontSize: 11,
                  color: "var(--ops-fg-mute)",
                }}
              >
                LOADING…
              </div>
            ) : (
              <EventTicker events={snapshot.events} />
            )}
          </Panel>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Panel title="HEARTBEAT · 60M" flushBody>
            <HeartbeatSpark heartbeats={snapshot.heartbeats} />
          </Panel>

          <Panel title="UPCOMING FIRES">
            <ScheduleTimeline jobs={snapshot.jobs} />
          </Panel>

          <Panel title="DAEMON STATS" flushBody>
            <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
              <KvRow label="JOBS" value={String(snapshot.jobs.length)} />
              <KvRow label="EVENTS (TAIL)" value={String(snapshot.events.length)} />
              <KvRow
                label="HEARTBEATS (60M)"
                value={String(snapshot.heartbeats.length)}
              />
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function KvRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        fontFamily: "var(--ops-mono)",
        fontSize: 11,
        gap: 12,
      }}
    >
      <span style={{ color: "var(--ops-fg-mute)", letterSpacing: "0.08em" }}>{label}</span>
      <span
        style={{
          color: "var(--ops-fg)",
          borderBottom: "1px dashed var(--ops-line)",
          flex: 1,
          marginBottom: 1,
        }}
      />
      <span style={{ color: "var(--ops-fg)" }}>{value}</span>
    </div>
  );
}
