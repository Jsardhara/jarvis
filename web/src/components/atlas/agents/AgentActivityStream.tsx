"use client";

/**
 * AgentActivityStream
 *
 * Renders a vertical list of RecentActivity events, latest at top.
 * Each row: relative timestamp, event_type chip (color by kind),
 * payload preview (first 100 chars), expand button → inline JSON viewer.
 *
 * Color map:
 *   signal   → gold (amber)
 *   decision → blue (info)
 *   order    → green (ok)
 *   insight  → violet (scholar)
 *   status   → neutral (default)
 *   error    → red (crit)
 */

import { useState } from "react";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import type { RecentActivity } from "@/hooks/useAgentDetail";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentActivityStreamProps {
  events: RecentActivity[];
}

// ─── Event type → chip kind ───────────────────────────────────────────────────

type TagKind = "default" | "amber" | "ok" | "crit" | "info";

function eventKind(eventType: string): TagKind {
  const t = eventType.toLowerCase();
  // Error/reject checked first — "trade_rejected" must not fall into the "trade" bucket
  if (t.includes("error") || t.includes("reject") || t.includes("fail")) return "crit";
  if (t.includes("signal") || t.includes("market")) return "amber";
  if (t.includes("decision") || t.includes("strategy") || t.includes("insight") || t.includes("learning")) return "info";
  if (t.includes("order") || t.includes("trade") || t.includes("fill") || t.includes("position")) return "ok";
  return "default";
}

// ─── Relative time ────────────────────────────────────────────────────────────

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m`;
  return `${Math.round(diff / 3_600_000)}h`;
}

// ─── Activity row ─────────────────────────────────────────────────────────────

interface ActivityRowProps {
  event: RecentActivity;
}

function ActivityRow({ event }: ActivityRowProps) {
  const [expanded, setExpanded] = useState(false);

  const preview = (() => {
    try {
      const raw = JSON.stringify(event.payload);
      return raw.length > 100 ? raw.slice(0, 100) + "…" : raw;
    } catch {
      return String(event.payload);
    }
  })();

  const full = (() => {
    try {
      return JSON.stringify(event.payload, null, 2);
    } catch {
      return String(event.payload);
    }
  })();

  return (
    <div
      className="activity-row"
      style={{
        borderBottom: "1px solid var(--ops-line-faint)",
        padding: "8px 14px",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 9,
            color: "var(--ops-fg-faint)",
            whiteSpace: "nowrap",
            paddingTop: 2,
            minWidth: 28,
          }}
        >
          {relTime(event.occurred_at)}
        </span>
        <Tag kind={eventKind(event.event_type)}>
          {event.event_type}
        </Tag>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-dim)",
            flex: 1,
            wordBreak: "break-all",
          }}
        >
          {preview}
        </span>
        <button
          onClick={() => setExpanded((e) => !e)}
          aria-label={expanded ? "Collapse payload" : "Expand payload"}
          style={{
            background: "none",
            border: "none",
            color: "var(--ops-fg-faint)",
            fontFamily: "var(--ops-mono)",
            fontSize: 9,
            cursor: "pointer",
            padding: "0 4px",
            flexShrink: 0,
          }}
        >
          {expanded ? "▲" : "▼"}
        </button>
      </div>
      {expanded && (
        <pre
          style={{
            marginTop: 8,
            marginLeft: 38,
            padding: "8px 10px",
            background: "var(--ops-bg-void)",
            border: "1px solid var(--ops-line)",
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-mute)",
            overflowX: "auto",
            maxHeight: 260,
          }}
        >
          {full}
        </pre>
      )}
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentActivityStream({ events }: AgentActivityStreamProps) {
  return (
    <Panel
      title="ACTIVITY"
      trailing={
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-faint)",
          }}
        >
          {events.length} events
        </span>
      }
      flushBody
      className="agent-activity-stream"
      bodyClassName="agent-activity-stream-body"
    >
      {events.length === 0 ? (
        <div
          style={{
            padding: 14,
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg-faint)",
          }}
        >
          No activity yet.
        </div>
      ) : (
        <div style={{ overflowY: "auto", height: "100%" }}>
          {events.map((ev, i) => (
            <ActivityRow key={`${ev.event_type}-${ev.occurred_at}-${i}`} event={ev} />
          ))}
        </div>
      )}
    </Panel>
  );
}
