"use client";

/**
 * SentinelTimeline
 *
 * Renders upcoming sentinel scheduled jobs sorted by next run time.
 * Sourced from useDaemon() schedule + nextScheduledRuns.
 */

import type { CSSProperties } from "react";
import { useDaemon } from "@/hooks/use-daemon";
import { Hatch, AgentGlyph, getAgentIdentity } from "@/components/ops";

interface ScheduleEntry {
  name: string;
  nextIso: string;
}

/** Heuristic: map job name keywords to known agent ids. */
export function deriveTarget(name: string): string | null {
  const n = name.toLowerCase();
  if (n.includes("inbox") || n.includes("mail") || n.includes("tempo") || n.includes("calendar")) return "tempo";
  if (n.includes("scholar") || n.includes("study") || n.includes("academic")) return "scholar";
  if (n.includes("lens") || n.includes("research") || n.includes("monitor")) return "lens";
  if (n.includes("forge") || n.includes("build") || n.includes("deploy")) return "forge";
  if (n.includes("atlas") || n.includes("trade") || n.includes("portfolio")) return "atlas";
  if (n.includes("sentinel") || n.includes("daemon")) return "sentinel";
  return null;
}

export function SentinelTimeline() {
  const { status, config } = useDaemon();

  const entries: ScheduleEntry[] = Object.entries(config.schedule)
    .filter(([, job]) => job.enabled)
    .map(([name]) => ({ name, nextIso: status.nextScheduledRuns[name] ?? "" }))
    .filter((e) => e.nextIso !== "")
    .sort((a, b) => a.nextIso.localeCompare(b.nextIso))
    .slice(0, 6);

  if (entries.length === 0) {
    return <Hatch label="NO SCHEDULED JOBS" height={80} />;
  }

  return (
    <div style={{ position: "relative", paddingLeft: 60 } as CSSProperties}>
      <div style={{ position: "absolute", left: 50, top: 0, bottom: 0, width: 1, background: "var(--ops-line-bright)" } as CSSProperties} />
      {entries.map((entry, i) => {
        const timeLabel = new Date(entry.nextIso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const target = deriveTarget(entry.name);
        const identity = target ? getAgentIdentity(target) : null;
        const dotColor = identity ? identity.colorHex : "var(--ops-amber)";
        const pt = i === 0 ? 4 : 16;
        return (
          <div key={entry.name} style={{ display: "flex", alignItems: "flex-start", gap: 12, position: "relative", paddingTop: pt } as CSSProperties}>
            <span style={{ position: "absolute", left: -54, top: pt, fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-amber)", width: 44, textAlign: "right", lineHeight: "14px" } as CSSProperties}>
              {timeLabel}
            </span>
            <div style={{ position: "absolute", left: -14, top: pt + 3, width: 9, height: 9, borderRadius: "50%", background: dotColor, boxShadow: `0 0 6px ${dotColor}` } as CSSProperties} />
            <div>
              <div style={{ fontSize: 11, color: "var(--ops-fg)", fontFamily: "var(--ops-mono)", lineHeight: "14px" } as CSSProperties}>
                {entry.name}
              </div>
              {identity && (
                <div style={{ fontSize: 10, color: identity.colorHex, display: "flex", alignItems: "center", gap: 4, marginTop: 2 } as CSSProperties}>
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
