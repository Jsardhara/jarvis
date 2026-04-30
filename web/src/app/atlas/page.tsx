"use client";

/**
 * /atlas — ATLAS overview
 *
 * KPI strip (equity, today P&L, open trades, win rate)
 * Two-column body:
 *   Left  — recent trades summary, signals nudge, insights nudge
 *   Right — 5-dot agent status + sentinel schedule timeline
 *
 * PipelineSwimlane lives at /atlas/pipeline — not embedded here.
 */

import { CSSProperties } from "react";
import Link from "next/link";
import { useAtlasSnapshot } from "@/hooks/useAtlasSnapshot";
import { useTradeBlotter } from "@/hooks/useTradeBlotter";
import type { TradeStats } from "@/hooks/useTradeBlotter";
import { Panel, Tag, KV, Hatch, AgentGlyph, getAgentIdentity } from "@/components/ops";
import { AgentStatusRow } from "@/components/atlas/AgentStatusRow";
import { MockModeBanner } from "@/components/atlas/MockModeBanner";
import { SentinelTimeline } from "@/components/atlas/SentinelTimeline";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatEquity(portfolio: Record<string, unknown> | null | undefined): string {
  if (typeof portfolio?.equity === "number")
    return `$${(portfolio.equity as number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (typeof portfolio?.portfolio_value === "number")
    return `$${(portfolio.portfolio_value as number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return "—";
}

function formatPnl(stats: TradeStats): { text: string; accent: string | undefined } {
  const abs = Math.abs(stats.today_pnl_usd).toFixed(2);
  if (stats.today_pnl_usd > 0) return { text: `+$${abs}`, accent: "var(--ops-ok)" };
  if (stats.today_pnl_usd < 0) return { text: `-$${abs}`, accent: "var(--ops-crit)" };
  return { text: "$0.00", accent: undefined };
}

const VIEW_LINK_STYLE: CSSProperties = {
  fontSize: 9, color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)", letterSpacing: "0.08em"
};

// ─── KPI tile ─────────────────────────────────────────────────────────────────

function KpiTile({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div style={{ flex: 1, padding: "10px 14px", borderRight: "1px solid var(--ops-line)", minWidth: 0 }}>
      <div style={{ fontFamily: "var(--ops-mono)", fontSize: 9, letterSpacing: "0.1em", color: "var(--ops-fg-mute)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontFamily: "var(--ops-mono)", fontSize: 18, fontWeight: 600, color: accent ?? "var(--ops-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value}</div>
    </div>
  );
}

// ─── KPI strip ────────────────────────────────────────────────────────────────

function KpiStrip({ snapshot, stats }: { snapshot: ReturnType<typeof useAtlasSnapshot>["snapshot"]; stats: TradeStats }) {
  const portRaw = snapshot?.portfolio as Record<string, unknown> | null | undefined;
  const equity = formatEquity(portRaw);
  const { text: pnl, accent: pnlAccent } = formatPnl(stats);
  const winRate = stats.total_trades > 0 ? `${(stats.win_rate * 100).toFixed(0)}%` : "—";

  return (
    <div style={{ display: "flex", borderBottom: "1px solid var(--ops-line)", background: "var(--ops-bg-deep)" }}>
      <KpiTile label="EQUITY"      value={equity} />
      <KpiTile label="TODAY P&L"   value={pnl}    accent={pnlAccent} />
      <KpiTile label="OPEN TRADES" value={String(stats.open_count)} />
      <KpiTile label="WIN RATE"    value={winRate} />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AtlasPage() {
  const { snapshot, degraded } = useAtlasSnapshot();
  const { stats } = useTradeBlotter();
  const sentinelIdentity = getAgentIdentity("sentinel");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 } as CSSProperties}>
      <MockModeBanner />

      {/* KPI strip */}
      <KpiStrip snapshot={snapshot} stats={stats} />

      {/* Pipeline hint bar */}
      <div style={{ padding: "6px 16px", borderBottom: "1px solid var(--ops-line)", fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-dim)", display: "flex", alignItems: "center", gap: 8, background: "var(--ops-bg-deep)" } as CSSProperties}>
        {degraded && <Tag kind="crit">DEGRADED</Tag>}
        <span>Pipeline view</span>
        <Link href="/atlas/pipeline" style={{ color: "var(--ops-info)", textDecoration: "none" }}>→ /atlas/pipeline</Link>
      </div>

      {/* Body */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", flex: 1, minHeight: 0, overflow: "hidden" } as CSSProperties}>

        {/* Left: summary panels */}
        <div style={{ borderRight: "1px solid var(--ops-line)", overflowY: "auto", display: "flex", flexDirection: "column", gap: 12, padding: 12 } as CSSProperties}>

          <Panel title="RECENT TRADES" trailing={<Link href="/atlas/trades" style={VIEW_LINK_STYLE}>View all →</Link>}>
            {stats.total_trades === 0 ? (
              <Hatch label="NO TRADES YET" height={60} />
            ) : (
              <>
                <KV label="OPEN">{String(stats.open_count)}</KV>
                <KV label="TOTAL">{String(stats.total_trades)}</KV>
                <KV label="BEST" accent={stats.best_trade_usd > 0 ? "var(--ops-ok)" : undefined}>
                  {stats.best_trade_usd !== 0 ? `$${stats.best_trade_usd.toFixed(2)}` : "—"}
                </KV>
              </>
            )}
          </Panel>

          <Panel title="SIGNALS" trailing={<Link href="/atlas/network" style={VIEW_LINK_STYLE}>View graph →</Link>}>
            <Hatch label="SEE /ATLAS/NETWORK FOR LIVE SIGNAL FLOW" height={60} />
          </Panel>

          <Panel title="AGENT INSIGHTS" trailing={<Link href="/atlas/agents/sage" style={VIEW_LINK_STYLE}>View Sage →</Link>}>
            <Hatch label="RECENT LEARNING INSIGHTS FROM SAGE" height={60} />
          </Panel>
        </div>

        {/* Right: agent status + sentinel schedule */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 12, overflowY: "auto" } as CSSProperties}>
          <Panel title="AGENT STATUS">
            <AgentStatusRow />
          </Panel>
          <Panel title="SENTINEL · SCHEDULE" leading={sentinelIdentity ? <AgentGlyph agent={sentinelIdentity} size={14} /> : undefined}>
            <SentinelTimeline />
          </Panel>
        </div>
      </div>
    </div>
  );
}
