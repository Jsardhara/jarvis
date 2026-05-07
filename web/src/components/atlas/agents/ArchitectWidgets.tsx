"use client";

/**
 * ArchitectWidgets
 *
 * Agent-specific widget slot for the Architect workspace.
 *
 * Panels:
 *   1. Active Strategies — GET /api/atlas/strategies; table with name, version,
 *      status, sharpe, max_drawdown, total_return, activated_at.
 *   2. Last 3 Backtests — most recent backtests across strategies.
 *   3. "Generate New Strategy" button — disabled (tooltip "wired in v2").
 */

import { useEffect, useState, useRef, CSSProperties } from "react";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import { OpsButton } from "@/components/ops/OpsButton";

// ─── Constants ────────────────────────────────────────────────────────────────

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ArchitectWidgetsProps {
  agentId: string;
}

interface Backtest {
  backtest_id: string;
  timerange: string;
  sharpe: number;
  max_drawdown: number;
  status: string;
}

interface Strategy {
  strategy_id: string;
  name: string;
  version: string;
  status: string;
  sharpe?: number;
  max_drawdown?: number;
  total_return?: number;
  activated_at?: string;
  backtests?: Backtest[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function statusKind(status: string): TagKind {
  const s = status.toLowerCase();
  if (s === "active" || s === "running") return "ok";
  if (s === "paused" || s === "draft") return "amber";
  if (s === "failed" || s === "error") return "crit";
  if (s === "backtesting") return "info";
  return "default";
}

function fmtPct(v: number | undefined): string {
  if (v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function fmtNum(v: number | undefined): string {
  if (v === undefined) return "—";
  return v.toFixed(3);
}

function relTime(iso: string | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`;
  return `${Math.round(diff / 86_400_000)}d ago`;
}

// ─── Cell / header styles ─────────────────────────────────────────────────────

const cell: CSSProperties = {
  fontFamily: "var(--ops-mono)",
  fontSize: "0.68rem",
  padding: "5px 8px",
  borderBottom: "1px solid var(--ops-line-faint)",
  color: "var(--ops-fg)",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const thSt: CSSProperties = {
  fontFamily: "var(--ops-mono)",
  fontSize: "0.6rem",
  letterSpacing: "0.1em",
  padding: "5px 8px",
  color: "var(--ops-fg-faint)",
  borderBottom: "1px solid var(--ops-line)",
  background: "var(--ops-bg-elevated)",
  textAlign: "left",
  fontWeight: 600,
  whiteSpace: "nowrap",
};

// ─── Strategies Panel ─────────────────────────────────────────────────────────

interface StrategiesPanelProps {
  strategies: Strategy[];
  isLoading: boolean;
}

function StrategiesPanel({ strategies, isLoading }: StrategiesPanelProps) {
  return (
    <Panel
      title="ACTIVE STRATEGIES"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {strategies.length} strategies
        </span>
      }
      flushBody
    >
      {isLoading ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          Loading strategies…
        </div>
      ) : strategies.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No strategies deployed.
        </div>
      ) : (
        <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: 200 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["NAME", "VER", "STATUS", "SHARPE", "DD", "RETURN", "ACTIVATED"].map((h) => (
                  <th key={h} style={thSt}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strategies.map((s) => (
                <tr key={s.strategy_id}>
                  <td style={{ ...cell, fontWeight: 600, maxWidth: 100 }}>{s.name}</td>
                  <td style={{ ...cell, color: "var(--ops-fg-dim)" }}>v{s.version}</td>
                  <td style={cell}><Tag kind={statusKind(s.status)}>{s.status.toUpperCase()}</Tag></td>
                  <td style={{ ...cell, textAlign: "right" }}>{fmtNum(s.sharpe)}</td>
                  <td style={{ ...cell, textAlign: "right", color: s.max_drawdown !== undefined && s.max_drawdown > 0.15 ? "var(--ops-crit)" : "var(--ops-fg)" }}>
                    {s.max_drawdown !== undefined ? fmtPct(-s.max_drawdown) : "—"}
                  </td>
                  <td style={{ ...cell, textAlign: "right", color: (s.total_return ?? 0) >= 0 ? "var(--ops-ok)" : "var(--ops-crit)" }}>
                    {fmtPct(s.total_return)}
                  </td>
                  <td style={{ ...cell, color: "var(--ops-fg-dim)", fontSize: "0.62rem" }}>{relTime(s.activated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ─── Backtests Panel ──────────────────────────────────────────────────────────

interface BacktestEntry {
  strategyName: string;
  backtest: Backtest;
}

interface BacktestsPanelProps {
  entries: BacktestEntry[];
  isLoading: boolean;
}

function BacktestsPanel({ entries, isLoading }: BacktestsPanelProps) {
  return (
    <Panel
      title="RECENT BACKTESTS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          last 3
        </span>
      }
      flushBody
    >
      {isLoading ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          Loading…
        </div>
      ) : entries.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No backtest history yet.
        </div>
      ) : (
        <div>
          {entries.map(({ strategyName, backtest }, i) => (
            <div
              key={`${backtest.backtest_id}-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderBottom: "1px solid var(--ops-line-faint)",
              }}
            >
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, fontWeight: 600, color: "var(--ops-fg)", minWidth: 80 }}>
                {strategyName}
              </span>
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-dim)" }}>
                {backtest.timerange}
              </span>
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg)", flex: 1 }}>
                SR {fmtNum(backtest.sharpe)}
              </span>
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-crit)" }}>
                DD {backtest.max_drawdown !== undefined ? fmtPct(-backtest.max_drawdown) : "—"}
              </span>
              <Tag kind={statusKind(backtest.status)}>{backtest.status.toUpperCase()}</Tag>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ─── Generate Button Panel ────────────────────────────────────────────────────

function GeneratePanel() {
  const [generating, setGenerating] = useState(false);
  const proxyAvailable = false; // Not wired until v2
  const containerRef = useRef<HTMLSpanElement>(null);

  const handleGenerate = async () => {
    if (!proxyAvailable || generating) return;
    setGenerating(true);
    try {
      await fetch(`${JARVIS_API}/api/atlas/strategies/generate`, { method: "POST" });
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Panel title="STRATEGY GENERATION">
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span ref={containerRef} title={!proxyAvailable ? "Wired in v2" : undefined} style={{ display: "inline-block" }}>
          <OpsButton
            variant="primary"
            disabled={!proxyAvailable || generating}
            onClick={() => { void handleGenerate(); }}
          >
            {generating ? "GENERATING…" : "GENERATE NEW STRATEGY"}
          </OpsButton>
        </span>
        {!proxyAvailable && (
          <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-faint)", letterSpacing: "0.08em" }}>
            wired in v2
          </span>
        )}
      </div>
    </Panel>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function ArchitectWidgets({ agentId }: ArchitectWidgetsProps) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    fetch(`${JARVIS_API}/api/atlas/strategies`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Strategy[] | { strategies: Strategy[] }>;
      })
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : (data.strategies ?? []);
        setStrategies(list);
        setIsLoading(false);
      })
      .catch(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // Build last-3 backtest entries
  const backtestEntries: BacktestEntry[] = [];
  for (const s of strategies) {
    if (s.backtests && s.backtests.length > 0) {
      const latest = [...s.backtests].sort((a, b) =>
        b.backtest_id.localeCompare(a.backtest_id)
      )[0];
      backtestEntries.push({ strategyName: s.name, backtest: latest });
    }
    if (backtestEntries.length >= 3) break;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", overflow: "auto" }}>
      <StrategiesPanel strategies={strategies} isLoading={isLoading} />
      <BacktestsPanel entries={backtestEntries} isLoading={isLoading} />
      <GeneratePanel />
    </div>
  );
}
