"use client";

import type { CSSProperties } from "react";
import type { SentinelInboxEvent } from "@/hooks/useSentinelSnapshot";
import { Tag, Hatch, AgentGlyph, getAgentIdentity } from "@/components/ops";

interface Props {
  events: SentinelInboxEvent[];
  /** Hide the high-frequency 'heartbeat' summary lines. Default true. */
  hideHeartbeats?: boolean;
  /** Optional cap on rendered rows. Default 40. */
  limit?: number;
}

function severityKind(sev: string): "ok" | "amber" | "crit" | "default" {
  if (sev === "alert" || sev === "error") return "crit";
  if (sev === "warn") return "amber";
  if (sev === "info") return "default";
  return "default";
}

export function EventTicker({
  events,
  hideHeartbeats = true,
  limit = 40,
}: Props) {
  const filtered = events
    .filter((e) => !hideHeartbeats || e.summary !== "heartbeat")
    .slice(-limit)
    .reverse();

  if (filtered.length === 0) {
    return <Hatch label="NO RECENT EVENTS" height={120} />;
  }

  const rowStyle: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "62px 80px 1fr",
    alignItems: "center",
    gap: 10,
    padding: "8px 12px",
    borderBottom: "1px solid var(--ops-line)",
    fontFamily: "var(--ops-mono)",
    fontSize: 11,
  };

  return (
    <div style={{ maxHeight: 360, overflowY: "auto" }}>
      {filtered.map((ev, i) => {
        const identity = getAgentIdentity(ev.agent);
        const time = new Date(ev.ts).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
        return (
          <div key={`${ev.ts}-${i}`} style={rowStyle}>
            <span style={{ color: "var(--ops-amber)", fontSize: 10 }}>{time}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
              {identity ? <AgentGlyph agent={identity} size={10} /> : null}
              <span
                style={{
                  color: identity?.colorHex ?? "var(--ops-fg)",
                  fontSize: 10,
                  letterSpacing: "0.06em",
                }}
              >
                {ev.agent.toUpperCase()}
              </span>
            </span>
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                minWidth: 0,
              }}
            >
              <Tag kind={severityKind(ev.severity)}>{ev.severity}</Tag>
              <span
                style={{
                  color: "var(--ops-fg)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  flex: 1,
                  minWidth: 0,
                }}
                title={ev.summary}
              >
                {ev.summary}
              </span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
