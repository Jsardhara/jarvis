"use client";

/**
 * /atlas — Atlas pipeline + sentinel timeline
 *
 * Left (1fr): PipelineSwimlane (oracle → architect → guardian → trader)
 * Right (380px): Atlas snapshot KV + Sentinel schedule timeline
 *
 * A1: SentinelTimeline wired to useDaemon() schedule — no mock data.
 * A4: Atlas snapshot uses typed AtlasSnapshot fields.
 */

import { CSSProperties, useCallback } from "react";
import { PipelineSwimlane } from "@/components/PipelineSwimlane";
import { usePipelineStream } from "@/hooks/usePipelineStream";
import type { ConnectionState } from "@/hooks/usePipelineStream";
import { useAtlasSnapshot } from "@/hooks/useAtlasSnapshot";
import { useDaemon } from "@/hooks/use-daemon";
import type { AtlasSnapshot } from "@/lib/types";
import { Panel, AgentGlyph, Dot, KV, Tag, Hatch, getAgentIdentity } from "@/components/ops";

const JARVIS_API = process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765";

async function resolveConfirmation(
  eventId: string,
  decision: "approve" | "reject",
): Promise<void> {
  const requestId = eventId.split(":")[0];
  const endpoint = `${JARVIS_API}/api/confirmations/${requestId}/${decision}`;
  const res = await fetch(endpoint, { method: "POST" });
  if (!res.ok) {
    void res.status;
  }
}

// ─── Atlas snapshot panel ─────────────────────────────────────────────────────

function AtlasSnapshotPanel({ snapshot }: { snapshot: AtlasSnapshot }) {
  const posCount = Array.isArray(snapshot.positions) ? snapshot.positions.length : 0;

  // pnl: try to extract a numeric total — structure is unknown but commonly { total: number }
  const pnlRaw = snapshot.pnl as Record<string, unknown> | null | undefined;
  const pnlTotal =
    typeof pnlRaw?.total === "number"
      ? `$${(pnlRaw.total as number).toFixed(2)}`
      : typeof pnlRaw?.unrealized === "number"
      ? `$${(pnlRaw.unrealized as number).toFixed(2)}`
      : "—";

  // portfolio: try to extract account value or buying power
  const portRaw = snapshot.portfolio as Record<string, unknown> | null | undefined;
  const equity =
    typeof portRaw?.equity === "number"
      ? `$${(portRaw.equity as number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : typeof portRaw?.portfolio_value === "number"
      ? `$${(portRaw.portfolio_value as number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : "—";

  const buyingPower =
    typeof portRaw?.buying_power === "number"
      ? `$${(portRaw.buying_power as number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : "—";

  const lastUpdated = snapshot.ts
    ? new Date(snapshot.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";

  return (
    <Panel
      title="ATLAS · STATUS"
      trailing={
        <Tag kind={snapshot.degraded ? "crit" : "ok"}>
          {snapshot.degraded ? "DEGRADED" : "LIVE"}
        </Tag>
      }
    >
      <KV label="EQUITY">{equity}</KV>
      <KV label="BUYING POWER">{buyingPower}</KV>
      <KV label="POSITIONS">{String(posCount)}</KV>
      <KV label="PNL">{pnlTotal}</KV>
      <KV label="LAST UPDATE" accent="var(--ops-fg-dim)">{lastUpdated}</KV>
    </Panel>
  );
}

// ─── Sentinel schedule timeline ───────────────────────────────────────────────

interface ScheduleEntry {
  name: string;
  nextIso: string;
}

function SentinelTimeline() {
  const { status, config } = useDaemon();

  // Merge config.schedule (name → { enabled, cron, command }) with
  // status.nextScheduledRuns (name → next ISO string) to build timeline entries.
  const entries: ScheduleEntry[] = Object.entries(config.schedule)
    .filter(([, job]) => job.enabled)
    .map(([name]) => ({
      name,
      nextIso: status.nextScheduledRuns[name] ?? "",
    }))
    .filter((e) => e.nextIso !== "")
    .sort((a, b) => a.nextIso.localeCompare(b.nextIso))
    .slice(0, 8);

  if (entries.length === 0) {
    return <Hatch label="NO SCHEDULED JOBS" height={120} />;
  }

  return (
    <div
      style={{
        position: "relative",
        minHeight: 80,
        paddingLeft: 60,
      } as CSSProperties}
    >
      {/* vertical timeline rail */}
      <div
        style={{
          position: "absolute",
          left: 50,
          top: 0,
          bottom: 0,
          width: 1,
          background: "var(--ops-line-bright)",
        } as CSSProperties}
      />

      {entries.map((entry, i) => {
        const timeLabel = new Date(entry.nextIso).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
        // Derive a target agent from the job name (e.g. "inbox-triage" → "tempo")
        const target = deriveTarget(entry.name);
        const identity = target ? getAgentIdentity(target) : null;
        const dotColor = identity ? identity.colorHex : "var(--ops-amber)";

        return (
          <div
            key={entry.name}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 12,
              position: "relative",
              paddingTop: i === 0 ? 4 : 18,
            } as CSSProperties}
          >
            {/* time label */}
            <span
              style={{
                position: "absolute",
                left: -54,
                top: i === 0 ? 4 : 18,
                fontFamily: "var(--ops-mono)",
                fontSize: 10,
                color: "var(--ops-amber)",
                width: 44,
                textAlign: "right",
                lineHeight: "14px",
              } as CSSProperties}
            >
              {timeLabel}
            </span>

            {/* dot on rail */}
            <div
              style={{
                position: "absolute",
                left: -14,
                top: i === 0 ? 7 : 21,
                width: 9,
                height: 9,
                borderRadius: "50%",
                background: dotColor,
                boxShadow: `0 0 6px ${dotColor}`,
                flexShrink: 0,
              } as CSSProperties}
            />

            <div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--ops-fg)",
                  fontFamily: "var(--ops-mono)",
                  lineHeight: "14px",
                } as CSSProperties}
              >
                {entry.name}
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
                  } as CSSProperties}
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

/** Heuristic: map job name keywords to known agent ids. */
function deriveTarget(name: string): string | null {
  const n = name.toLowerCase();
  if (n.includes("inbox") || n.includes("mail") || n.includes("tempo") || n.includes("calendar")) return "tempo";
  if (n.includes("scholar") || n.includes("study") || n.includes("academic")) return "scholar";
  if (n.includes("lens") || n.includes("research") || n.includes("monitor")) return "lens";
  if (n.includes("forge") || n.includes("build") || n.includes("deploy")) return "forge";
  if (n.includes("atlas") || n.includes("trade") || n.includes("portfolio")) return "atlas";
  if (n.includes("sentinel") || n.includes("daemon")) return "sentinel";
  return null;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AtlasPage() {
  const { events, connectionState } = usePipelineStream();
  const { snapshot } = useAtlasSnapshot();

  const handleConfirm = useCallback(
    async (eventId: string, decision: "approve" | "reject") => {
      await resolveConfirmation(eventId, decision);
    },
    [],
  );

  const atlasIdentity = getAgentIdentity("atlas");
  const sentinelIdentity = getAgentIdentity("sentinel");

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      } as CSSProperties}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 380px",
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
        } as CSSProperties}
      >
        {/* ── Pipeline swimlane ─────────────────────────────────────────────── */}
        <div
          style={{
            borderRight: "1px solid var(--ops-line)",
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
            overflow: "hidden",
          } as CSSProperties}
        >
          {/* Section header */}
          <div
            style={{
              borderBottom: "1px solid var(--ops-line)",
              padding: "10px 16px",
              background: "var(--ops-bg-deep)",
              display: "flex",
              alignItems: "center",
              gap: 10,
            } as CSSProperties}
          >
            {atlasIdentity && <AgentGlyph agent={atlasIdentity} size={18} />}
            <span
              style={{
                fontFamily: "var(--ops-sans)",
                fontSize: 11,
                letterSpacing: "0.12em",
                fontWeight: 600,
              } as CSSProperties}
            >
              ATLAS · PIPELINE
            </span>
            <Dot
              kind={connectionState === "live" ? "ok" : connectionState === "connecting" ? "warn" : "crit"}
              pulse={connectionState === "live"}
            />
            <span
              style={{
                fontSize: 9,
                color: "var(--ops-fg-dim)",
                fontFamily: "var(--ops-mono)",
                letterSpacing: "0.1em",
                marginLeft: "auto",
              } as CSSProperties}
            >
              {(connectionState as ConnectionState).toUpperCase()}
            </span>
          </div>

          {/* Swimlane */}
          <div style={{ flex: 1, overflow: "hidden" } as CSSProperties}>
            <PipelineSwimlane
              events={events}
              connectionState={connectionState}
              onConfirm={handleConfirm}
              maxEventsPerLane={80}
            />
          </div>
        </div>

        {/* ── Right rail ────────────────────────────────────────────────────── */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            padding: 12,
            overflowY: "auto",
          } as CSSProperties}
        >
          {/* Atlas snapshot — typed fields */}
          {snapshot ? (
            <AtlasSnapshotPanel snapshot={snapshot} />
          ) : (
            <Panel title="ATLAS · STATUS" trailing={<Tag kind="crit">OFFLINE</Tag>}>
              <Hatch label="NO SNAPSHOT · ATLAS UNREACHABLE" height={80} />
            </Panel>
          )}

          {/* Sentinel timeline — wired to useDaemon schedule */}
          <Panel
            title="SENTINEL · SCHEDULE"
            leading={sentinelIdentity ? <AgentGlyph agent={sentinelIdentity} size={14} /> : undefined}
          >
            <SentinelTimeline />
          </Panel>
        </div>
      </div>
    </div>
  );
}
