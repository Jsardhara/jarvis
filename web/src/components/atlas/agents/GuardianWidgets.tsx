"use client";

/**
 * GuardianWidgets
 *
 * Agent-specific widget slot for the Guardian workspace.
 *
 * Panels:
 *   1. Signal Queue — pending signals from GET /api/atlas/signals/active.
 *   2. Recent Decisions — last 10 TRADE_APPROVED / TRADE_REJECTED /
 *      TRADE_MODIFIED events from recentActivity.
 *   3. Risk Thresholds — hard-coded defaults with env note.
 */

import { useEffect, useState, CSSProperties } from "react";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import { useAgentDetail } from "@/hooks/useAgentDetail";
import { useAgentMemory } from "@/hooks/useAgentMemory";
import type { MemoryEntry } from "@/hooks/useAgentMemory";
import type { RecentActivity } from "@/hooks/useAgentDetail";

// ─── Constants ────────────────────────────────────────────────────────────────

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const RISK_DEFAULTS = {
  MAX_LEVERAGE: 5,
  DAILY_LOSS_LIMIT_USD: 50,
  MAX_PORTFOLIO_RISK_PCT: 10,
} as const;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface GuardianWidgetsProps {
  agentId: string;
}

interface PendingSignal {
  signal_id: string;
  pair: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  created_at: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function dirKind(dir: string): TagKind {
  if (dir === "LONG") return "ok";
  if (dir === "SHORT") return "crit";
  return "default";
}

function decisionKind(eventType: string): TagKind {
  if (eventType === "TRADE_APPROVED") return "ok";
  if (eventType === "TRADE_REJECTED") return "crit";
  if (eventType === "TRADE_MODIFIED") return "amber";
  return "default";
}

function relAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m`;
  return `${Math.round(diff / 3_600_000)}h`;
}

const DECISION_TYPES = new Set(["TRADE_APPROVED", "TRADE_REJECTED", "TRADE_MODIFIED"]);

// ─── Cell style ───────────────────────────────────────────────────────────────

const cell: CSSProperties = {
  fontFamily: "var(--ops-mono)",
  fontSize: "0.68rem",
  padding: "5px 8px",
  borderBottom: "1px solid var(--ops-line-faint)",
  color: "var(--ops-fg)",
  whiteSpace: "nowrap",
};

// ─── Signal Queue Panel ───────────────────────────────────────────────────────

interface SignalQueuePanelProps {
  signals: PendingSignal[];
  isLoading: boolean;
}

function SignalQueuePanel({ signals, isLoading }: SignalQueuePanelProps) {
  return (
    <Panel
      title="SIGNAL QUEUE"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {signals.length} pending
        </span>
      }
      flushBody
    >
      {isLoading ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>Loading…</div>
      ) : signals.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          Queue empty — no pending signals.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 180 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["PAIR", "DIR", "CONF", "AGE"].map((h) => (
                  <th
                    key={h}
                    style={{
                      ...cell,
                      color: "var(--ops-fg-faint)",
                      letterSpacing: "0.1em",
                      fontSize: "0.6rem",
                      borderBottom: "1px solid var(--ops-line)",
                      background: "var(--ops-bg-elevated)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.signal_id}>
                  <td style={{ ...cell, fontWeight: 600 }}>{s.pair}</td>
                  <td style={cell}><Tag kind={dirKind(s.direction)}>{s.direction}</Tag></td>
                  <td style={{ ...cell, textAlign: "right" }}>{(s.confidence * 100).toFixed(0)}%</td>
                  <td style={{ ...cell, color: "var(--ops-fg-dim)" }}>{relAge(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ─── Decisions Panel ──────────────────────────────────────────────────────────

interface DecisionsPanelProps {
  events: RecentActivity[];
}

function DecisionsPanel({ events }: DecisionsPanelProps) {
  const decisions = events.filter((e) => DECISION_TYPES.has(e.event_type)).slice(0, 10);

  return (
    <Panel
      title="RECENT DECISIONS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {decisions.length} shown
        </span>
      }
      flushBody
    >
      {decisions.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No decisions yet.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 200 }}>
          {decisions.map((ev, i) => {
            const sigId = String(ev.payload?.signal_id ?? ev.payload?.id ?? "—");
            const reasoning = String(ev.payload?.reasoning ?? ev.payload?.reason ?? "");
            const label = ev.event_type.replace("TRADE_", "");
            return (
              <div
                key={`${ev.event_type}-${ev.occurred_at}-${i}`}
                style={{
                  padding: "6px 10px",
                  borderBottom: "1px solid var(--ops-line-faint)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 3,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-faint)", minWidth: 60 }}>
                    {sigId.slice(0, 8)}…
                  </span>
                  <Tag kind={decisionKind(ev.event_type)}>{label}</Tag>
                </div>
                {reasoning && (
                  <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-dim)", paddingLeft: 2 }}>
                    {reasoning.slice(0, 100)}{reasoning.length > 100 ? "…" : ""}
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

// ─── Risk Thresholds Panel ────────────────────────────────────────────────────

interface RiskThresholdsPanelProps {
  memory: Record<string, MemoryEntry>;
}

function RiskThresholdsPanel({ memory }: RiskThresholdsPanelProps) {
  const rawLeverage = memory["max_leverage"]?.value;
  const rawLoss = memory["daily_loss_limit_usd"]?.value;
  const rawRisk = memory["max_portfolio_risk_pct"]?.value;

  const maxLeverage = typeof rawLeverage === "number" ? rawLeverage : RISK_DEFAULTS.MAX_LEVERAGE;
  const dailyLoss = typeof rawLoss === "number" ? rawLoss : RISK_DEFAULTS.DAILY_LOSS_LIMIT_USD;
  const maxRisk = typeof rawRisk === "number" ? rawRisk : RISK_DEFAULTS.MAX_PORTFOLIO_RISK_PCT;

  const rows = [
    { label: "MAX_LEVERAGE", value: `${maxLeverage}x`, note: "per trade" },
    { label: "DAILY_LOSS_LIMIT", value: `$${dailyLoss}`, note: "circuit breaker" },
    { label: "MAX_PORTFOLIO_RISK", value: `${maxRisk}%`, note: "of AUM" },
  ];

  return (
    <Panel
      title="RISK THRESHOLDS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-faint)", letterSpacing: "0.08em" }}>
          from .env
        </span>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {rows.map((r) => (
          <div
            key={r.label}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "4px 6px",
              border: "1px solid var(--ops-line-faint)",
            }}
          >
            <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-dim)", letterSpacing: "0.06em" }}>
              {r.label}
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 12, fontWeight: 600, color: "var(--atlas-guardian, var(--ops-ok))" }}>
                {r.value}
              </span>
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-faint)" }}>
                {r.note}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function GuardianWidgets({ agentId }: GuardianWidgetsProps) {
  const { detail } = useAgentDetail(agentId);
  const { memory } = useAgentMemory(agentId);
  const [queue, setQueue] = useState<PendingSignal[]>([]);
  const [queueLoading, setQueueLoading] = useState(true);

  const recentActivity = detail?.recent_activity ?? [];

  useEffect(() => {
    let cancelled = false;
    setQueueLoading(true);
    fetch(`${JARVIS_API}/api/atlas/signals/active`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<PendingSignal[] | { signals: PendingSignal[] }>;
      })
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : (data.signals ?? []);
        setQueue(list);
        setQueueLoading(false);
      })
      .catch(() => {
        if (!cancelled) setQueueLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", overflow: "auto" }}>
      <SignalQueuePanel signals={queue} isLoading={queueLoading} />
      <DecisionsPanel events={recentActivity} />
      <RiskThresholdsPanel memory={memory} />
    </div>
  );
}
