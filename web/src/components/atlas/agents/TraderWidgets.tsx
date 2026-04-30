"use client";

/**
 * TraderWidgets
 *
 * Agent-specific widget slot for the Trader workspace.
 *
 * Panels:
 *   1. Open Positions — compact 5-col view of open trades.
 *   2. Pending Kraken Orders — placed (unfilled) trades.
 *   3. Kelly Sizing Audit — last 5 ORDER_PLACED events from recentActivity.
 *
 * Trades are sourced from useTradeBlotter to avoid double-fetching the same
 * endpoint that the shell's TradeTable (if composed) also needs.
 */

import { CSSProperties, useMemo } from "react";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import { useAgentDetail } from "@/hooks/useAgentDetail";
import { useTradeBlotter } from "@/hooks/useTradeBlotter";
import type { RecentActivity } from "@/hooks/useAgentDetail";
import type { Trade } from "@/hooks/useTradeBlotter";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TraderWidgetsProps {
  agentId: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function formatPrice(val: number | undefined): string {
  if (val === undefined) return "—";
  if (val >= 1000) return `$${val.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  return `$${val.toFixed(4)}`;
}

function formatPnl(val: number | undefined): string {
  if (val === undefined) return "—";
  const sign = val >= 0 ? "+" : "";
  return `${sign}$${val.toFixed(2)}`;
}

function pnlColor(val: number | undefined): string {
  if (val === undefined) return "var(--ops-fg-dim)";
  if (val > 0) return "var(--ops-ok)";
  if (val < 0) return "var(--ops-crit)";
  return "var(--ops-fg)";
}

function dirKind(dir: string): TagKind {
  if (dir === "LONG") return "ok";
  if (dir === "SHORT") return "crit";
  return "default";
}

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  return `${Math.round(diff / 3_600_000)}h ago`;
}

// ─── Cell / header styles ─────────────────────────────────────────────────────

const cell: CSSProperties = {
  fontFamily: "var(--ops-mono)",
  fontSize: "0.68rem",
  padding: "5px 8px",
  borderBottom: "1px solid var(--ops-line-faint)",
  color: "var(--ops-fg)",
  whiteSpace: "nowrap",
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
};

// ─── Open Positions Panel (compact 5-col) ─────────────────────────────────────

interface OpenPositionsPanelProps {
  trades: Trade[];
}

function OpenPositionsPanel({ trades }: OpenPositionsPanelProps) {
  const open = useMemo(() => trades.filter((t) => t.status === "open"), [trades]);

  return (
    <Panel
      title="OPEN POSITIONS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {open.length} positions
        </span>
      }
      flushBody
    >
      {open.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No open positions.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 200 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["PAIR", "DIR", "ENTRY", "P&L", "STATUS"].map((h) => (
                  <th key={h} style={{ ...thSt, textAlign: h === "ENTRY" || h === "P&L" ? "right" : "left" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {open.map((t) => {
                const direction = t.direction ?? (t.side === "buy" ? "LONG" : "SHORT");
                return (
                  <tr key={t.trade_id}>
                    <td style={{ ...cell, fontWeight: 600 }}>{t.pair}</td>
                    <td style={cell}><Tag kind={dirKind(direction)}>{direction}</Tag></td>
                    <td style={{ ...cell, textAlign: "right" }}>{formatPrice(t.entry_price)}</td>
                    <td style={{ ...cell, textAlign: "right", color: pnlColor(t.pnl_usd), fontWeight: 600 }}>
                      {formatPnl(t.pnl_usd)}
                    </td>
                    <td style={cell}><Tag kind="ok">OPEN</Tag></td>
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

// ─── Pending Orders Panel ─────────────────────────────────────────────────────

interface PendingOrdersPanelProps {
  trades: Trade[];
}

function PendingOrdersPanel({ trades }: PendingOrdersPanelProps) {
  const placed = useMemo(() => trades.filter((t) => t.status === "placed"), [trades]);

  return (
    <Panel
      title="PENDING KRAKEN ORDERS"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          {placed.length} unfilled
        </span>
      }
      flushBody
    >
      {placed.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No pending orders.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 160 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["PAIR", "SIDE", "SIZE", "LEV", "STATUS"].map((h) => (
                  <th key={h} style={{ ...thSt, textAlign: h === "SIZE" || h === "LEV" ? "right" : "left" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {placed.map((t) => (
                <tr key={t.trade_id}>
                  <td style={{ ...cell, fontWeight: 600 }}>{t.pair}</td>
                  <td style={{ ...cell, textTransform: "uppercase" }}>{t.side}</td>
                  <td style={{ ...cell, textAlign: "right" }}>{t.size.toFixed(4)}</td>
                  <td style={{ ...cell, textAlign: "right", color: "var(--ops-fg-dim)" }}>
                    {t.leverage !== undefined ? `${t.leverage}x` : "—"}
                  </td>
                  <td style={cell}><Tag kind="info">PLACED</Tag></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ─── Kelly Sizing Audit Panel ─────────────────────────────────────────────────

interface SizingRow {
  pair: string;
  requestedSize?: number;
  leverage?: number;
  winRate?: number;
  occurredAt: string;
}

interface KellySizingPanelProps {
  recentActivity: RecentActivity[];
}

function KellySizingPanel({ recentActivity }: KellySizingPanelProps) {
  const rows: SizingRow[] = useMemo(() => {
    return recentActivity
      .filter((e) => e.event_type === "ORDER_PLACED")
      .slice(0, 5)
      .map((e) => ({
        pair: String(e.payload?.pair ?? "—"),
        requestedSize: typeof e.payload?.requested_size === "number" ? e.payload.requested_size : undefined,
        leverage: typeof e.payload?.leverage === "number" ? e.payload.leverage : undefined,
        winRate: typeof e.payload?.win_rate === "number" ? e.payload.win_rate : undefined,
        occurredAt: e.occurred_at,
      }));
  }, [recentActivity]);

  return (
    <Panel
      title="KELLY SIZING AUDIT"
      trailing={
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
          last 5
        </span>
      }
      flushBody
    >
      {rows.length === 0 ? (
        <div style={{ padding: 12, fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg-faint)" }}>
          No ORDER_PLACED events yet.
        </div>
      ) : (
        <div style={{ overflowY: "auto", maxHeight: 160 }}>
          {rows.map((r, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "5px 10px",
                borderBottom: "1px solid var(--ops-line-faint)",
              }}
            >
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, fontWeight: 600, color: "var(--ops-fg)", minWidth: 80 }}>
                {r.pair}
              </span>
              {r.requestedSize !== undefined && (
                <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-dim)" }}>
                  sz {r.requestedSize.toFixed(4)}
                </span>
              )}
              {r.leverage !== undefined && (
                <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-dim)" }}>
                  {r.leverage}x
                </span>
              )}
              {r.winRate !== undefined && (
                <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--atlas-trader, var(--ops-info))" }}>
                  WR {(r.winRate * 100).toFixed(0)}%
                </span>
              )}
              <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-faint)", marginLeft: "auto" }}>
                {relTime(r.occurredAt)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function TraderWidgets({ agentId }: TraderWidgetsProps) {
  const { detail } = useAgentDetail(agentId);
  const { trades } = useTradeBlotter();
  const recentActivity = detail?.recent_activity ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", overflow: "auto" }}>
      <OpenPositionsPanel trades={trades} />
      <PendingOrdersPanel trades={trades} />
      <KellySizingPanel recentActivity={recentActivity} />
    </div>
  );
}
