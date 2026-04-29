"use client";

import { useState } from "react";
import { Activity } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { BreadcrumbNav } from "@/components/breadcrumb-nav";
import { AgentGlyph } from "@/components/ops/AgentGlyph";
import { Tag } from "@/components/ops/Tag";
import { Dot } from "@/components/ops/Dot";
import { useActivityLog } from "@/hooks/use-data";
import { EventRowSkeleton } from "@/components/skeletons";
import { ErrorState } from "@/components/error-state";
import { getAgentIdentity } from "@/components/ops/agent-identity";
import type { EventType, ActivityEvent } from "@/lib/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ─── Event metadata ────────────────────────────────────────────────────────────

const eventTypeLabels: Record<EventType, string> = {
  task_created: "TASK CREATED",
  task_updated: "TASK UPDATED",
  task_completed: "TASK DONE",
  task_delegated: "DELEGATED",
  task_failed: "TASK FAILED",
  message_sent: "MESSAGE",
  decision_requested: "DECISION REQ",
  decision_answered: "DECISION ANS",
  brain_dump_triaged: "TRIAGE",
  milestone_completed: "MILESTONE",
  agent_checkin: "CHECKIN",
};

type DotKind = "ok" | "warn" | "crit" | "info" | "idle";

const eventTypeDot: Record<EventType, DotKind> = {
  task_created: "info",
  task_updated: "idle",
  task_completed: "ok",
  task_delegated: "info",
  task_failed: "crit",
  message_sent: "idle",
  decision_requested: "warn",
  decision_answered: "ok",
  brain_dump_triaged: "info",
  milestone_completed: "ok",
  agent_checkin: "idle",
};

// Known actors from current data (legacy roles + new agent ids)
const ACTOR_OPTIONS: { value: string; label: string }[] = [
  { value: "me", label: "ME" },
  { value: "researcher", label: "RESEARCHER" },
  { value: "developer", label: "DEVELOPER" },
  { value: "marketer", label: "MARKETER" },
  { value: "business-analyst", label: "ANALYST" },
  { value: "tempo", label: "TEMPO" },
  { value: "scholar", label: "SCHOLAR" },
  { value: "lens", label: "LENS" },
  { value: "forge", label: "FORGE" },
  { value: "atlas", label: "ATLAS" },
  { value: "sentinel", label: "SENTINEL" },
  { value: "system", label: "SYSTEM" },
];

function fmtTime(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  if (d.toDateString() === today.toDateString()) return "TODAY";
  if (d.toDateString() === yesterday.toDateString()) return "YESTERDAY";
  return d
    .toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
    .toUpperCase();
}

function groupByDate(events: ActivityEvent[]): Map<string, ActivityEvent[]> {
  const groups = new Map<string, ActivityEvent[]>();
  for (const event of events) {
    const label = fmtDate(event.timestamp);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(event);
  }
  return groups;
}

// ─── Single event row ──────────────────────────────────────────────────────────

function EventRow({ evt }: { evt: ActivityEvent }) {
  const identity = getAgentIdentity(evt.actor);
  const dotKind = eventTypeDot[evt.type];
  const tagLabel = eventTypeLabels[evt.type];

  return (
    <div
      className="grid items-start gap-x-3 py-2 border-b border-[color:var(--ops-line-dim)] last:border-0"
      style={{ gridTemplateColumns: "18px 1fr auto" }}
    >
      {/* col 1 — agent glyph or fallback */}
      <div className="pt-0.5">
        {identity ? (
          <AgentGlyph agent={identity} size={18} />
        ) : (
          <span
            className="inline-grid place-items-center shrink-0"
            style={{
              width: 18,
              height: 18,
              border: "1px solid var(--ops-line-strong)",
              color: "var(--ops-line-strong)",
              fontSize: 8,
              fontWeight: 700,
              letterSpacing: "-0.04em",
              fontFamily: "var(--ops-mono)",
            }}
          >
            {evt.actor.slice(0, 2).toUpperCase()}
          </span>
        )}
      </div>

      {/* col 2 — type tag + summary + details */}
      <div className="min-w-0 space-y-0.5">
        <div className="flex items-center gap-2 flex-wrap">
          <Dot kind={dotKind} />
          <Tag kind="default" className="text-[9px] tracking-wider">
            {tagLabel}
          </Tag>
          <span
            className="text-[11px] font-mono uppercase tracking-wide"
            style={{ color: identity?.colorHex ?? "var(--ops-fg-dim)" }}
          >
            {identity?.name ?? evt.actor}
          </span>
        </div>
        <p className="text-xs" style={{ color: "var(--ops-fg-base)" }}>
          {evt.summary}
        </p>
        {evt.details && (
          <p
            className="text-[11px] font-mono"
            style={{ color: "var(--ops-fg-dim)" }}
          >
            {evt.details}
          </p>
        )}
      </div>

      {/* col 3 — mono timestamp */}
      <span
        className="text-[10px] font-mono tabular-nums pt-0.5 shrink-0"
        style={{ color: "var(--ops-fg-dim)" }}
      >
        {fmtTime(evt.timestamp)}
      </span>
    </div>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function ActivityPage() {
  const { events, loading, error: activityError, refetch } = useActivityLog();
  const [filterActor, setFilterActor] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");

  let filtered = [...events].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );
  if (filterActor !== "all") {
    filtered = filtered.filter((e) => e.actor === filterActor);
  }
  if (filterType !== "all") {
    filtered = filtered.filter((e) => e.type === filterType);
  }
  const grouped = groupByDate(filtered);

  if (loading) {
    return (
      <div className="space-y-6 p-5">
        <BreadcrumbNav items={[{ label: "Activity" }]} />
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <EventRowSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (activityError) {
    return (
      <div className="space-y-6 p-5">
        <BreadcrumbNav items={[{ label: "Activity Log" }]} />
        <ErrorState message={activityError} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="space-y-5 p-5">
      <BreadcrumbNav items={[{ label: "Activity" }]} />

      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <h1
          className="text-sm font-mono font-bold tracking-[0.18em] uppercase flex items-center gap-2"
          style={{ color: "var(--ops-fg-base)" }}
        >
          <Activity className="h-4 w-4" style={{ color: "var(--ops-amber)" }} />
          Activity Log
          <span
            className="text-[10px] font-mono tracking-wider"
            style={{ color: "var(--ops-fg-dim)" }}
          >
            · {filtered.length} events
          </span>
        </h1>

        {/* Filters */}
        <div className="flex items-center gap-2">
          <Select value={filterActor} onValueChange={setFilterActor}>
            <SelectTrigger className="h-7 w-36 text-[10px] font-mono uppercase tracking-wide">
              <SelectValue placeholder="ALL ACTORS" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">ALL ACTORS</SelectItem>
              {ACTOR_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="h-7 w-40 text-[10px] font-mono uppercase tracking-wide">
              <SelectValue placeholder="ALL TYPES" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">ALL TYPES</SelectItem>
              {(Object.keys(eventTypeLabels) as EventType[]).map((type) => (
                <SelectItem key={type} value={type}>
                  {eventTypeLabels[type]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Log */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No activity yet"
          description="Actions taken by you and your AI agents will be logged here."
        />
      ) : (
        <div className="space-y-6">
          {Array.from(grouped.entries()).map(([dateLabel, dateEvents]) => (
            <section key={dateLabel}>
              {/* Date divider */}
              <div
                className="flex items-center gap-3 mb-2"
                style={{ borderBottom: "1px solid var(--ops-line-dim)", paddingBottom: 6 }}
              >
                <span
                  className="text-[9px] font-mono font-bold tracking-[0.22em] uppercase shrink-0"
                  style={{ color: "var(--ops-amber)" }}
                >
                  {dateLabel}
                </span>
                <span
                  className="text-[9px] font-mono"
                  style={{ color: "var(--ops-fg-dim)" }}
                >
                  {dateEvents.length} event{dateEvents.length !== 1 ? "s" : ""}
                </span>
              </div>

              {/* Rows */}
              <div>
                {dateEvents.map((evt) => (
                  <EventRow key={evt.id} evt={evt} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
