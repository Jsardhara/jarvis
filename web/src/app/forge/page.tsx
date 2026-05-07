"use client";

/**
 * /forge — build pipeline monitor
 *
 * Stage swimlane (current job placeholder), daily forge run log, sub-agent roster.
 * Reads /api/forge/snapshot which tails state/daily_projects.jsonl.
 */

import type { CSSProperties } from "react";
import { useForgeSnapshot } from "@/hooks/useForge";
import { Panel, AgentGlyph, Tag, getAgentIdentity } from "@/components/ops";
import { StageSwimlane } from "@/components/forge/StageSwimlane";
import { DailyRunsList } from "@/components/forge/DailyRunsList";
import { SubAgentRoster } from "@/components/forge/SubAgentRoster";

const forge = getAgentIdentity("forge")!;

function etaLabel(iso: string): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "FIRING";
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m}M`;
  const h = m / 60;
  return `${h.toFixed(1)}H`;
}

export default function ForgePage() {
  const { snapshot, loading, error } = useForgeSnapshot();

  const counts = snapshot.status_counts;
  const successRate = (() => {
    const success = counts.success ?? 0;
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    if (total === 0) return "—";
    return `${Math.round((success / total) * 100)}%`;
  })();

  const headerStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 16px",
    borderBottom: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <header style={headerStyle}>
        <AgentGlyph agent={forge} size={22} />
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 13,
              letterSpacing: "0.12em",
              color: forge.colorHex,
            }}
          >
            FORGE · {forge.role}
          </span>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 10,
              color: "var(--ops-fg-mute)",
              letterSpacing: "0.06em",
            }}
          >
            {forge.tagline}
          </span>
        </div>
        <span style={{ marginLeft: "auto" }}>
          <Tag kind="ok">SUCCESS · {counts.success ?? 0}</Tag>
        </span>
        <Tag kind="crit">FAILED · {counts.failed ?? 0}</Tag>
        <Tag kind="amber">SKIPPED · {counts.skipped_budget ?? 0}</Tag>
        <Tag kind="info">RATE · {successRate}</Tag>
        <Tag kind="default">NEXT · {etaLabel(snapshot.next_daily_iso)}</Tag>
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
          {error}
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
          <Panel title="ACTIVE PIPELINE">
            <StageSwimlane jobTitle="No active job — pipeline idle" />
            <p
              style={{
                margin: "8px 4px 0",
                fontFamily: "var(--ops-mono)",
                fontSize: 10,
                color: "var(--ops-fg-mute)",
                letterSpacing: "0.04em",
              }}
            >
              Live job tracking lights up the swimlane in real time when a Forge run is
              in flight. Until the WorktreeRunner emits stage events, this stays a
              static template.
            </p>
          </Panel>

          <Panel
            title="DAILY FORGE LOG"
            trailing={
              <span
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: "var(--ops-fg-mute)",
                  letterSpacing: "0.08em",
                }}
              >
                STATE/DAILY_PROJECTS.JSONL
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
              <DailyRunsList runs={snapshot.daily_runs} />
            )}
          </Panel>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Panel title="SUB-AGENTS" flushBody>
            <SubAgentRoster />
          </Panel>

          <Panel title="DAILY FORGE · CRON">
            <div
              style={{
                fontFamily: "var(--ops-mono)",
                fontSize: 11,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <KvRow label="SCHEDULE" value="10:00 UTC · DAILY" />
              <KvRow
                label="NEXT FIRE"
                value={
                  snapshot.next_daily_iso
                    ? new Date(snapshot.next_daily_iso).toLocaleString()
                    : "—"
                }
              />
              <KvRow label="RUNS LOGGED" value={String(snapshot.daily_runs.length)} />
              <KvRow label="SUCCESS RATE" value={successRate} />
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
