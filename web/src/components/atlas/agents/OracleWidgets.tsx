"use client";

/**
 * OracleWidgets
 *
 * Agent-specific widget slot for the Oracle workspace.
 * Fetches its own data — accepts agentId and reads hooks internally.
 *
 * Panels:
 *   1. Screener Candidates — top-10 from memory['screener_candidates']
 *      or last RESEARCH_UPDATE event payload.
 *   2. Last 5 Signals — GET /api/atlas/signals?limit=5; each links to
 *      /atlas/trades?signal_id=<id>.
 *   3. Shortable Count — from memory['shortable_set'] or screener data.
 */

import { useEffect, useState, CSSProperties } from "react";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import { useAgentDetail } from "@/hooks/useAgentDetail";
import { useAgentMemory } from "@/hooks/useAgentMemory";

// ─── Constants ────────────────────────────────────────────────────────────────

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface OracleWidgetsProps {
  agentId: string;
}

interface Candidate {
  pair: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  score: number;
  shortable?: boolean;
}

interface Signal {
  signal_id: string;
  pair: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  status: "pending" | "approved" | "rejected";
}

// ─── Data extraction helpers ───────────────────────────────────────────────────

function extractCandidates(
  memory: ReturnType<typeof useAgentMemory>["memory"],
  recentActivity: ReturnType<typeof useAgentDetail>["detail"] extends null ? [] : NonNullable<ReturnType<typeof useAgentDetail>["detail"]>["recent_activity"]
): Candidate[] {
  const raw = memory["screener_candidates"]?.value;
  if (Array.isArray(raw) && raw.length > 0) {
    return (raw as Candidate[]).slice(0, 10);
  }
  const event = recentActivity.find(
    (e) => e.event_type === "RESEARCH_UPDATE" && Array.isArray(e.payload?.candidates)
  );
  if (event) {
    return (event.payload.candidates as Candidate[]).slice(0, 10);
  }
  return [];
}

function extractShortableCount(
  memory: ReturnType<typeof useAgentMemory>["memory"],
  candidates: Candidate[]
): number {
  const raw = memory["shortable_set"]?.value;
  if (Array.isArray(raw)) return raw.length;
  return candidates.filter((c) => c.shortable).length;
}

// ─── Direction chip kind ──────────────────────────────────────────────────────

type TagKind = "ok" | "crit" | "default" | "amber" | "info";

function dirChipKind(dir: string): TagKind {
  if (dir === "LONG") return "ok";
  if (dir === "SHORT") return "crit";
  return "default";
}

// ─── Cell style ───────────────────────────────────────────────────────────────

const cellSt: CSSProperties = {
  fontFamily: "var(--ops-mono)",
  fontSize: "0.68rem",
  padding: "5px 8px",
  borderBottom: "1px solid var(--ops-line-faint)",
  whiteSpace: "nowrap",
};

// ─── Screener Panel ───────────────────────────────────────────────────────────

interface ScreenerPanelProps {
  candidates: Candidate[];
  shortableCount: number;
}

function ScreenerPanel({ candidates, shortableCount }: ScreenerPanelProps) {
  return (
    <Panel
      title="SCREENER"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {shortableCount} shortable
        </span>
      }
      flushBody
    >
      {candidates.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No candidates this cycle.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 200 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["PAIR", "DIR", "SCORE", "SH"].map((h) => (
                  <th
                    key={h}
                    style={{
                      ...cellSt,
                      color: "var(--ops-fg-faint)",
                      letterSpacing: "0.1em",
                      fontSize: "0.6rem",
                      borderBottom: "1px solid var(--ops-line)",
                      background: "var(--ops-bg-elevated)",
                      textAlign: h === "SCORE" ? "right" : "left",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, i) => (
                <tr key={`${c.pair}-${i}`}>
                  <td style={{ ...cellSt, fontWeight: 600, color: "var(--ops-fg)" }}>{c.pair}</td>
                  <td style={cellSt}><Tag kind={dirChipKind(c.direction)}>{c.direction}</Tag></td>
                  <td style={{ ...cellSt, textAlign: "right", color: c.score >= 0 ? "var(--ops-ok)" : "var(--ops-crit)" }}>
                    {c.score >= 0 ? "+" : ""}{c.score.toFixed(3)}
                  </td>
                  <td style={cellSt}>
                    {c.shortable ? (
                      <Tag kind="info">SH</Tag>
                    ) : (
                      <span style={{ color: "var(--ops-fg-faint)", fontFamily: "var(--ops-mono)", fontSize: "0.6rem" }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ─── Signals Panel ────────────────────────────────────────────────────────────

const STATUS_KIND: Record<string, TagKind> = {
  pending: "amber",
  approved: "ok",
  rejected: "crit",
};

interface SignalsPanelProps {
  signals: Signal[];
  isLoading: boolean;
}

function SignalsPanel({ signals, isLoading }: SignalsPanelProps) {
  return (
    <Panel
      title="LAST 5 SIGNALS"
      trailing={
        isLoading ? (
          <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>loading…</span>
        ) : undefined
      }
      flushBody
    >
      {!isLoading && signals.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No signals published yet.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 200 }}>
          {signals.map((s) => (
            <div
              key={s.signal_id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderBottom: "1px solid var(--ops-line-faint)",
              }}
            >
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, fontWeight: 600, color: "var(--ops-fg)", minWidth: 80 }}>
                {s.pair}
              </span>
              <Tag kind={dirChipKind(s.direction)}>{s.direction}</Tag>
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-dim)", flex: 1 }}>
                {(s.confidence * 100).toFixed(0)}%
              </span>
              <Tag kind={STATUS_KIND[s.status] ?? "default"}>
                {s.status.toUpperCase()}
              </Tag>
              <a
                href={`/atlas/trades?signal_id=${s.signal_id}`}
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: "var(--atlas-oracle, var(--ops-amber))",
                  textDecoration: "underline",
                }}
              >
                →
              </a>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function OracleWidgets({ agentId }: OracleWidgetsProps) {
  const { detail } = useAgentDetail(agentId);
  const { memory } = useAgentMemory(agentId);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(true);

  const recentActivity = detail?.recent_activity ?? [];
  const candidates = extractCandidates(memory, recentActivity);
  const shortableCount = extractShortableCount(memory, candidates);

  useEffect(() => {
    let cancelled = false;
    setSignalsLoading(true);
    fetch(`${JARVIS_API}/api/atlas/signals?limit=5`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Signal[] | { signals: Signal[] }>;
      })
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : (data.signals ?? []);
        setSignals(list);
        setSignalsLoading(false);
      })
      .catch(() => {
        if (!cancelled) setSignalsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", overflow: "auto" }}>
      <ScreenerPanel candidates={candidates} shortableCount={shortableCount} />
      <SignalsPanel signals={signals} isLoading={signalsLoading} />
    </div>
  );
}
