"use client";

/**
 * SageWidgets
 *
 * Agent-specific widget slot for the Sage workspace.
 *
 * Panels:
 *   1. Learning Insights — last 10 LEARNING_INSIGHT events.
 *   2. Performance Reports — last PERFORMANCE_REPORT events.
 *   3. Lessons — memory keys starting with "lesson_" as KV cards.
 */

import { useMemo, CSSProperties } from "react";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import { useAgentDetail } from "@/hooks/useAgentDetail";
import { useAgentMemory } from "@/hooks/useAgentMemory";
import type { MemoryEntry } from "@/hooks/useAgentMemory";
import type { RecentActivity } from "@/hooks/useAgentDetail";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SageWidgetsProps {
  agentId: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function insightKind(insightType: string): TagKind {
  const t = insightType.toLowerCase();
  if (t.includes("loss") || t.includes("error") || t.includes("fail")) return "crit";
  if (t.includes("win") || t.includes("profit") || t.includes("success")) return "ok";
  if (t.includes("warning") || t.includes("drawdown")) return "amber";
  if (t.includes("pattern") || t.includes("regime") || t.includes("trend")) return "info";
  return "default";
}

function fmtPnl(val: number): string {
  const sign = val >= 0 ? "+" : "";
  return `${sign}$${val.toFixed(2)}`;
}

function pnlColor(val: number): string {
  if (val > 0) return "var(--ops-ok)";
  if (val < 0) return "var(--ops-crit)";
  return "var(--ops-fg)";
}

// ─── Cell style ───────────────────────────────────────────────────────────────

const cell: CSSProperties = {
  fontFamily: "var(--ops-mono)",
  fontSize: "0.68rem",
  padding: "5px 8px",
  borderBottom: "1px solid var(--ops-line-faint)",
  color: "var(--ops-fg)",
  whiteSpace: "nowrap",
};

// ─── Learning Insights Panel ──────────────────────────────────────────────────

interface InsightsPanelProps {
  events: RecentActivity[];
}

function InsightsPanel({ events }: InsightsPanelProps) {
  const insights = useMemo(
    () => events.filter((e) => e.event_type === "LEARNING_INSIGHT").slice(0, 10),
    [events]
  );

  return (
    <Panel
      title="LEARNING INSIGHTS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {insights.length} shown
        </span>
      }
      flushBody
    >
      {insights.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No insights yet.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 220 }}>
          {insights.map((ev, i) => {
            const tradeId = String(ev.payload?.trade_id ?? "");
            const insightType = String(ev.payload?.insight_type ?? ev.payload?.type ?? "INSIGHT");
            const confidence = typeof ev.payload?.confidence === "number" ? ev.payload.confidence : null;
            const text = String(ev.payload?.text ?? ev.payload?.insight ?? "");

            return (
              <div
                key={`${ev.occurred_at}-${i}`}
                style={{
                  padding: "8px 10px",
                  borderBottom: "1px solid var(--ops-line-faint)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {tradeId ? (
                    <a
                      href={`/atlas/trades?trade_id=${tradeId}`}
                      style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--atlas-sage, var(--ops-info))", textDecoration: "underline" }}
                    >
                      {tradeId.slice(0, 8)}…
                    </a>
                  ) : (
                    <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-faint)" }}>—</span>
                  )}
                  <Tag kind={insightKind(insightType)}>{insightType}</Tag>
                  {confidence !== null && (
                    <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-dim)", marginLeft: "auto" }}>
                      {(confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                {text && (
                  <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg)", lineHeight: 1.5 }}>
                    {text}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

// ─── Performance Reports Panel ────────────────────────────────────────────────

interface PerfReportsPanelProps {
  events: RecentActivity[];
}

function PerfReportsPanel({ events }: PerfReportsPanelProps) {
  const reports = useMemo(
    () => events.filter((e) => e.event_type === "PERFORMANCE_REPORT"),
    [events]
  );

  return (
    <Panel
      title="PERFORMANCE REPORTS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {reports.length} reports
        </span>
      }
      flushBody
    >
      {reports.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No performance reports yet.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 180 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["WINDOW", "P&L", "WIN RATE", "SHARPE"].map((h) => (
                  <th
                    key={h}
                    style={{
                      ...cell,
                      color: "var(--ops-fg-faint)",
                      letterSpacing: "0.1em",
                      fontSize: "0.6rem",
                      borderBottom: "1px solid var(--ops-line)",
                      background: "var(--ops-bg-elevated)",
                      textAlign: h === "WINDOW" ? "left" : "right",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {reports.map((ev, i) => {
                const window_ = String(ev.payload?.window ?? ev.payload?.period ?? "—");
                const pnl = typeof ev.payload?.total_pnl_usd === "number" ? ev.payload.total_pnl_usd : null;
                const winRate = typeof ev.payload?.win_rate === "number" ? ev.payload.win_rate : null;
                const sharpe = typeof ev.payload?.sharpe === "number" ? ev.payload.sharpe : null;

                return (
                  <tr key={i}>
                    <td style={{ ...cell, fontWeight: 600 }}>{window_}</td>
                    <td style={{ ...cell, textAlign: "right", color: pnl !== null ? pnlColor(pnl) : "var(--ops-fg-dim)", fontWeight: 600 }}>
                      {pnl !== null ? fmtPnl(pnl) : "—"}
                    </td>
                    <td style={{ ...cell, textAlign: "right" }}>
                      {winRate !== null ? `${(winRate * 100).toFixed(0)}%` : "—"}
                    </td>
                    <td style={{ ...cell, textAlign: "right" }}>
                      {sharpe !== null ? sharpe.toFixed(3) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ─── Lessons Panel ────────────────────────────────────────────────────────────

interface LessonsPanelProps {
  memory: Record<string, MemoryEntry>;
}

function LessonsPanel({ memory }: LessonsPanelProps) {
  const lessonKeys = useMemo(
    () => Object.keys(memory).filter((k) => k.startsWith("lesson_")).sort(),
    [memory]
  );

  return (
    <Panel
      title="LESSONS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {lessonKeys.length} lessons
        </span>
      }
    >
      {lessonKeys.length === 0 ? (
        <div style={{ fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No lessons stored yet.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {lessonKeys.map((k) => {
            const entry = memory[k];
            const raw = entry.value;
            const text = typeof raw === "string" ? raw : JSON.stringify(raw);
            const shortKey = k.replace("lesson_", "");

            return (
              <div
                key={k}
                style={{
                  padding: "6px 8px",
                  border: "1px solid var(--ops-line-faint)",
                  background: "var(--ops-bg-deep)",
                }}
              >
                <div style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--atlas-sage, var(--ops-info))", marginBottom: 4, letterSpacing: "0.08em" }}>
                  {shortKey.toUpperCase()}
                </div>
                <div style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg)", lineHeight: 1.5 }}>
                  {text}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function SageWidgets({ agentId }: SageWidgetsProps) {
  const { detail } = useAgentDetail(agentId);
  const { memory } = useAgentMemory(agentId);
  const recentActivity = detail?.recent_activity ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", overflow: "auto" }}>
      <InsightsPanel events={recentActivity} />
      <PerfReportsPanel events={recentActivity} />
      <LessonsPanel memory={memory} />
    </div>
  );
}
