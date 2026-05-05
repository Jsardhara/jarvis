"use client";

/**
 * TradeKpiStrip
 *
 * 5 KPI tiles sourced from TradeStats:
 *   - Open positions count
 *   - Today P&L (green/red by sign)
 *   - Win rate %
 *   - Total trades
 *   - Best trade $
 */

import { CSSProperties } from "react";
import { Panel } from "@/components/ops/Panel";
import type { TradeStats } from "@/hooks/useTradeBlotter";

interface KpiTileProps {
  label: string;
  value: string;
  valueColor?: string;
}

function KpiTile({ label, value, valueColor }: KpiTileProps) {
  return (
    <Panel>
      <div style={{ textAlign: "center", padding: "0.25rem 0" } as CSSProperties}>
        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: "1.5rem",
            fontWeight: 600,
            letterSpacing: "-0.02em",
            color: valueColor ?? "var(--ops-fg)",
            lineHeight: 1.1,
          } as CSSProperties}
        >
          {value}
        </div>
        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: "0.6rem",
            letterSpacing: "0.12em",
            color: "var(--ops-fg-dim)",
            marginTop: "0.35rem",
            textTransform: "uppercase",
          } as CSSProperties}
        >
          {label}
        </div>
      </div>
    </Panel>
  );
}

function formatPnl(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "$0.00";
  const abs = Math.abs(value);
  const sign = value >= 0 ? "+" : "-";
  if (abs >= 1000) {
    return `${sign}$${(abs / 1000).toFixed(1)}k`;
  }
  return `${sign}$${abs.toFixed(2)}`;
}

function formatWinRate(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

function formatBestTrade(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return "$0";
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
  return `$${value.toFixed(2)}`;
}

interface TradeKpiStripProps {
  stats: TradeStats;
}

export function TradeKpiStrip({ stats }: TradeKpiStripProps) {
  const pnlColor =
    stats.today_pnl_usd > 0
      ? "var(--ops-ok)"
      : stats.today_pnl_usd < 0
      ? "var(--ops-crit)"
      : "var(--ops-fg)";

  return (
    <div
      className="kpi-grid-5"
      style={{
        padding: "0.75rem 1rem",
        borderBottom: "1px solid var(--ops-line)",
        background: "var(--ops-bg-deep)",
        flexShrink: 0,
      } as CSSProperties}
      role="region"
      aria-label="Trade KPIs"
    >
      <KpiTile
        label="Open Positions"
        value={String(stats.open_count)}
      />
      <KpiTile
        label="Today P&L"
        value={formatPnl(stats.today_pnl_usd)}
        valueColor={pnlColor}
      />
      <KpiTile
        label="Win Rate"
        value={formatWinRate(stats.win_rate)}
      />
      <KpiTile
        label="Total Trades"
        value={String(stats.total_trades)}
      />
      <KpiTile
        label="Best Trade"
        value={formatBestTrade(stats.best_trade_usd)}
        valueColor="var(--ops-ok)"
      />
    </div>
  );
}
