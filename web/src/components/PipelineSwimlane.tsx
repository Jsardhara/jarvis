"use client";

/**
 * PipelineSwimlane
 *
 * Renders the 5-lane Atlas pipeline swimlane per the terminal-brutalism spec.
 * Does NOT own WebSocket — receives events as props from the page.
 *
 * Spec: docs/design/swimlane.md §2, §3
 */

import { useCallback, useEffect, useRef } from "react";
import type { ConnectionState } from "@/hooks/usePipelineStream";
import type { PipelineLane, PipelineState, TraceEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Constants ────────────────────────────────────────────────────────────────

const LANES: { id: PipelineLane; label: string; verb: string }[] = [
  { id: "oracle",    label: "ORACLE",    verb: "scan"    },
  { id: "architect", label: "ARCHITECT", verb: "rank"    },
  { id: "guardian",  label: "GUARDIAN",  verb: "check"   },
  { id: "trader",    label: "TRADER",    verb: "execute" },
  { id: "sage",      label: "SAGE",      verb: "reflect" },
];

// State precedence: error > blocked > running > pending > done
const STATE_PRECEDENCE: PipelineState[] = [
  "error",
  "blocked",
  "running",
  "pending",
  "done",
];

// ─── Props ────────────────────────────────────────────────────────────────────

export interface PipelineSwimlaneProps {
  events: TraceEvent[];
  connectionState: ConnectionState;
  onConfirm: (eventId: string, decision: "approve" | "reject") => Promise<void>;
  maxEventsPerLane?: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function worstState(states: PipelineState[]): PipelineState {
  for (const s of STATE_PRECEDENCE) {
    if (states.includes(s)) return s;
  }
  return "done";
}

function formatDuration(ms?: number): string {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  return `${m}m${String(s).padStart(2, "0")}s`;
}

function shortId(id: string): string {
  const parts = id.split(":");
  const base = parts[parts.length - 1] || id;
  return `#${base.slice(-6)}`;
}

function computeP50P95(durations: number[]): { p50: number; p95: number } {
  if (durations.length === 0) return { p50: 0, p95: 0 };
  const sorted = [...durations].sort((a, b) => a - b);
  const p50 = sorted[Math.floor(sorted.length * 0.5)] ?? 0;
  const p95 = sorted[Math.floor(sorted.length * 0.95)] ?? 0;
  return { p50, p95 };
}

// ─── State color styles (using CSS variables from globals.css) ────────────────

const STATE_BORDER: Record<PipelineState, string> = {
  pending: "border-[color:var(--pipeline-stage-pending)]",
  running: "border-[color:var(--pipeline-stage-running)]",
  done:    "border-[color:var(--pipeline-stage-done)]",
  blocked: "border-2 border-[color:var(--pipeline-stage-blocked)]",
  error:   "border-2 border-[color:var(--pipeline-stage-error)]",
};

const STATE_PILL_BG: Record<PipelineState, string> = {
  pending: "bg-[color:var(--pipeline-stage-pending)]",
  running: "bg-[color:var(--pipeline-stage-running)]",
  done:    "bg-[color:var(--pipeline-stage-done)]",
  blocked: "bg-[color:var(--pipeline-stage-blocked)]",
  error:   "bg-[color:var(--pipeline-stage-error)]",
};

const STATE_TEXT: Record<PipelineState, string> = {
  pending: "text-[color:var(--pipeline-stage-pending)]",
  running: "text-[color:var(--pipeline-stage-running)]",
  done:    "text-[color:var(--pipeline-stage-done)]",
  blocked: "text-[color:var(--pipeline-stage-blocked)]",
  error:   "text-[color:var(--pipeline-stage-error)]",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

interface EventCardProps {
  event: TraceEvent;
  p95: number;
  isNew: boolean;
  onConfirm: PipelineSwimlaneProps["onConfirm"];
}

function EventCard({ event, p95, isNew, onConfirm }: EventCardProps) {
  const {
    id,
    state,
    lane,
    durationMs,
    tier,
    startedAt,
    needsConfirm,
    violations,
  } = event;

  const isConfirmGate = state === "blocked" && needsConfirm;
  const isSlow = durationMs != null && p95 > 0 && durationMs >= p95;

  const borderClass = STATE_BORDER[state];
  const durationClass = isSlow
    ? "text-[color:var(--pipeline-stage-blocked)]"
    : "text-foreground";

  const ts = new Date(startedAt).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  if (isConfirmGate) {
    return (
      <div
        data-event-id={id}
        className={cn(
          "flex-1 font-mono text-xs border bg-card p-3 rounded-none",
          borderClass,
          isNew ? "animate-pipeline-event" : undefined
        )}
        style={{ minWidth: 280 }}
      >
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-foreground font-semibold">
            {shortId(id)}&nbsp;&nbsp;{lane}_check
          </span>
          <span className={cn("font-bold uppercase text-xs tracking-widest", STATE_TEXT.blocked)}>
            BLOCKED
          </span>
        </div>
        <div
          aria-hidden="true"
          className="border-t border-[color:var(--pipeline-lane-divider)] mb-2"
        />
        <div className={cn("mb-1 flex items-center gap-1", STATE_TEXT.blocked)}>
          <span aria-hidden="true">{">"} </span>
          <span>awaiting operator</span>
        </div>
        {violations && violations.length > 0 && (
          <p className="text-muted-foreground text-[10px] mb-2 leading-relaxed">
            violations: {violations.join(", ")}
          </p>
        )}
        <div className="flex gap-2 justify-end mt-2">
          <button
            type="button"
            onClick={() => void onConfirm(id, "approve")}
            className={cn(
              "font-mono text-[11px] uppercase tracking-widest px-2 py-0.5 rounded-none",
              "border border-[color:var(--pipeline-stage-done)]",
              "text-[color:var(--pipeline-stage-done)]",
              "hover:bg-[color:var(--pipeline-stage-done)]/10 transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-1"
            )}
            aria-label="Approve confirmation"
          >
            approve
          </button>
          <button
            type="button"
            onClick={() => void onConfirm(id, "reject")}
            className={cn(
              "font-mono text-[11px] uppercase tracking-widest px-2 py-0.5 rounded-none",
              "border border-[color:var(--pipeline-stage-error)]",
              "text-[color:var(--pipeline-stage-error)]",
              "hover:bg-[color:var(--pipeline-stage-error)]/10 transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-1"
            )}
            aria-label="Reject confirmation"
          >
            reject
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      data-event-id={id}
      className={cn(
        "font-mono text-xs border bg-card p-2 rounded-none",
        borderClass,
        "transition-[border-color] duration-200",
        isNew ? "animate-pipeline-event" : undefined
      )}
      style={{ minWidth: 140, maxWidth: 280, height: 88, flexShrink: 0 }}
    >
      <div className="flex items-start justify-between gap-1 mb-1">
        <span className="text-foreground font-semibold truncate">
          {shortId(id)}&nbsp;{lane}
        </span>
        <span className={cn("tabular-nums text-[11px]", durationClass, "whitespace-nowrap")}>
          {formatDuration(durationMs)}
        </span>
      </div>
      <div
        aria-hidden="true"
        className="border-t border-[color:var(--pipeline-lane-divider)] mb-1"
      />
      {tier != null && (
        <p className="text-[10px] text-muted-foreground mb-0.5">
          tier T{tier} · {event.intent ?? "trade"}
        </p>
      )}
      <p className="text-[10px] text-muted-foreground">{ts}</p>
    </div>
  );
}

// ─── Lane sparkline (p50/p95 strip) ──────────────────────────────────────────

interface SparklineProps {
  durations: number[];
  mean: number;
}

function Sparkline({ durations, mean }: SparklineProps) {
  if (durations.length < 2) return null;
  const last20 = durations.slice(-20);
  const maxVal = Math.max(...last20, 1);
  const w = 60;
  const h = 8;
  const step = w / (last20.length - 1);

  const points = last20.map((v, i) => {
    const x = i * step;
    const y = h - (v / maxVal) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const baseline = h - (mean / maxVal) * h;

  return (
    <svg
      width={w}
      height={h}
      aria-hidden="true"
      className="shrink-0"
      style={{ overflow: "visible" }}
    >
      <line
        x1={0}
        y1={baseline.toFixed(1)}
        x2={w}
        y2={baseline.toFixed(1)}
        stroke="var(--pipeline-lane-divider)"
        strokeWidth={0.5}
        strokeDasharray="2 2"
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="var(--pipeline-stage-running)"
        strokeWidth={1}
      />
    </svg>
  );
}

// ─── LaneRow — extracted component to satisfy React hooks rules ───────────────

interface LaneRowProps {
  laneId: PipelineLane;
  label: string;
  verb: string;
  laneIndex: number;
  events: TraceEvent[];
  maxEventsPerLane: number;
  animatedRef: React.MutableRefObject<Set<string>>;
  onConfirm: PipelineSwimlaneProps["onConfirm"];
}

function LaneRow({
  laneId,
  label,
  verb,
  laneIndex,
  events,
  maxEventsPerLane,
  animatedRef,
  onConfirm,
}: LaneRowProps) {
  const laneEvents = events
    .filter((e) => e.lane === laneId)
    .slice(-maxEventsPerLane);

  const states = laneEvents.map((e) => e.state);
  const dominant = states.length > 0 ? worstState(states) : "pending";
  const inFlight = laneEvents.filter((e) => e.state === "running").length;

  const durations = laneEvents
    .filter((e) => e.durationMs != null)
    .map((e) => e.durationMs as number);
  const { p50, p95 } = computeP50P95(durations);
  const mean = durations.length
    ? durations.reduce((a, b) => a + b, 0) / durations.length
    : 0;

  const trackRef = useRef<HTMLDivElement>(null);

  // Auto-scroll newest event into view when at right edge
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const tolerance = 32;
    const atEdge =
      el.scrollWidth - el.scrollLeft - el.clientWidth < tolerance;
    if (atEdge) {
      el.lastElementChild?.scrollIntoView({
        behavior: "smooth",
        inline: "end",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [laneEvents.length]);

  const isNew = (id: string): boolean => {
    if (animatedRef.current.has(id)) return false;
    animatedRef.current.add(id);
    return true;
  };

  return (
    <div
      className="flex min-h-[96px]"
      style={{
        backgroundColor:
          laneIndex % 2 === 0
            ? "var(--pipeline-lane-bg)"
            : "var(--pipeline-lane-bg-alt)",
      }}
    >
      {/* Header column — sticky left */}
      <div
        className="sticky left-0 z-10 flex flex-col justify-center gap-1 px-3 py-2 shrink-0"
        style={{
          width: 200,
          backgroundColor: "var(--pipeline-lane-header-bg)",
          borderRight: "1px solid var(--pipeline-lane-divider)",
        }}
      >
        <div className="flex items-center justify-between gap-1">
          <span className="uppercase tracking-widest text-[13px] text-foreground font-semibold">
            {label}
          </span>
          <div className="flex items-center gap-1">
            <span
              aria-label={`lane state: ${dominant}`}
              className={cn(
                "h-2 w-2 shrink-0",
                dominant !== "blocked" ? "rounded-full" : "rounded-none",
                STATE_PILL_BG[dominant],
                dominant === "running" ? "animate-stage-breathe" : undefined
              )}
            />
            {inFlight > 0 && (
              <span className="tabular-nums text-[10px] text-muted-foreground">
                {inFlight}
              </span>
            )}
          </div>
        </div>
        <span className="text-[11px] text-muted-foreground">{verb}</span>
        {durations.length > 0 && (
          <div className="flex items-center gap-2 mt-1">
            <Sparkline durations={durations} mean={mean} />
            <span className="text-[10px] text-muted-foreground tabular-nums whitespace-nowrap">
              p50 {formatDuration(p50)} · p95 {formatDuration(p95)}
            </span>
          </div>
        )}
      </div>

      {/* Event track — scrolls horizontally */}
      <div
        ref={trackRef}
        className="flex items-center gap-3 px-3 py-2 overflow-x-auto flex-1"
        style={{ scrollbarWidth: "thin" }}
      >
        {laneEvents.length === 0 ? (
          <span className="text-[11px] text-muted-foreground/50">no events</span>
        ) : (
          laneEvents.map((evt) => (
            <EventCard
              key={evt.id}
              event={evt}
              p95={p95}
              isNew={isNew(evt.id)}
              onConfirm={onConfirm}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function PipelineSwimlane({
  events,
  connectionState,
  onConfirm,
  maxEventsPerLane = 80,
}: PipelineSwimlaneProps) {
  // Track which event ids have received their entrance animation
  const animatedRef = useRef<Set<string>>(new Set());

  // Stable onConfirm wrapper
  const handleConfirm = useCallback(
    (eventId: string, decision: "approve" | "reject") =>
      onConfirm(eventId, decision),
    [onConfirm]
  );

  const guardianBlocked = events.some(
    (e) => e.lane === "guardian" && e.state === "blocked" && e.needsConfirm
  );

  const currentRun = events.reduce((max, e) => Math.max(max, e.pipelineRun), 0);
  const activeCount = events.filter((e) => e.state === "running").length;

  return (
    <div className="font-mono text-xs w-full">
      {/* Pipeline header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[color:var(--pipeline-lane-divider)] text-[13px]">
        <span className="text-foreground">
          pipeline run <span className="tabular-nums">#{currentRun || "—"}</span>
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="tabular-nums text-muted-foreground">{activeCount} active</span>
        <span className="text-muted-foreground">·</span>
        <span
          className={cn(
            guardianBlocked
              ? "text-[color:var(--pipeline-stage-blocked)]"
              : "text-muted-foreground"
          )}
        >
          guardian: {guardianBlocked ? "AWAITING" : "PASS"}
        </span>

        {connectionState !== "live" && (
          <span className="ml-auto text-[color:var(--pipeline-stage-error)] uppercase tracking-widest text-[11px]">
            connection: {connectionState === "lost" ? "LOST" : "CONNECTING"}
          </span>
        )}
      </div>

      {/* Lanes */}
      <div className="flex flex-col divide-y divide-[color:var(--pipeline-lane-divider)]">
        {LANES.map(({ id: laneId, label, verb }, laneIndex) => (
          <LaneRow
            key={laneId}
            laneId={laneId}
            label={label}
            verb={verb}
            laneIndex={laneIndex}
            events={events}
            maxEventsPerLane={maxEventsPerLane}
            animatedRef={animatedRef}
            onConfirm={handleConfirm}
          />
        ))}
      </div>
    </div>
  );
}
