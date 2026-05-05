"use client";

/**
 * TradeTable
 *
 * Sortable, filterable table of trades following the CostTable pattern
 * (hand-rolled, no @tanstack/react-table, memo-optimized rows).
 *
 * Columns: time, pair, direction, side, size, leverage, entry, exit, P&L, status, paper/live
 * Click row → onSelectTrade callback
 *
 * Filters extracted to TradeTableFilters.tsx.
 */

import { CSSProperties, memo, useCallback, useMemo, useState } from "react";
import { Tag } from "@/components/ops/Tag";
import { useIsMobile } from "@/hooks/useIsMobile";
import type { Trade, TradeStatus } from "@/hooks/useTradeBlotter";
import {
  TradeTableFilters,
  DEFAULT_TRADE_FILTERS,
  filterTrades,
} from "./TradeTableFilters";
import type { TradeFilterState } from "./TradeTableFilters";

// ─── Sort types ───────────────────────────────────────────────────────────────

export type SortKey =
  | "time"
  | "pair"
  | "direction"
  | "side"
  | "size"
  | "leverage"
  | "entry"
  | "exit"
  | "pnl"
  | "status";

export type SortDir = "asc" | "desc";

// ─── Formatting helpers ───────────────────────────────────────────────────────

function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  } as Intl.DateTimeFormatOptions);
}

function formatPrice(val: number | null | undefined): string {
  if (val == null || !Number.isFinite(val)) return "—";
  if (val >= 1000)
    return `$${val.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  return `$${val.toFixed(4)}`;
}

function formatPnl(val: number | null | undefined): string {
  if (val == null || !Number.isFinite(val)) return "—";
  const sign = val >= 0 ? "+" : "";
  return `${sign}$${val.toFixed(2)}`;
}

function pnlColor(val: number | null | undefined): string {
  if (val == null || !Number.isFinite(val)) return "var(--ops-fg-dim)";
  if (val > 0) return "var(--ops-ok)";
  if (val < 0) return "var(--ops-crit)";
  return "var(--ops-fg)";
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_TAG: Record<TradeStatus, "ok" | "info" | "crit" | "default" | "amber"> = {
  open: "ok",
  placed: "info",
  closed: "default",
  cancelled: "crit",
};

// ─── Sort logic (exported for tests) ─────────────────────────────────────────

export function tradeValue(t: Trade, key: SortKey): string | number {
  switch (key) {
    case "time":      return t.closed_at ?? t.opened_at ?? t.created_at;
    case "pair":      return t.pair;
    case "direction": return t.direction ?? (t.side === "buy" ? "LONG" : "SHORT");
    case "side":      return t.side;
    case "size":      return t.size;
    case "leverage":  return t.leverage ?? 0;
    case "entry":     return t.entry_price ?? 0;
    case "exit":      return t.exit_price ?? 0;
    case "pnl":       return t.pnl_usd ?? 0;
    case "status":    return t.status;
  }
}

export function sortTrades(trades: Trade[], key: SortKey, dir: SortDir): Trade[] {
  return [...trades].sort((a, b) => {
    const av = tradeValue(a, key);
    const bv = tradeValue(b, key);
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return dir === "asc" ? cmp : -cmp;
  });
}

// ─── Row component (memoized) ─────────────────────────────────────────────────

const cellStyle: CSSProperties = {
  padding: "0.35rem 0.6rem",
  fontFamily: "var(--ops-mono)",
  fontSize: "0.72rem",
  color: "var(--ops-fg)",
  borderBottom: "1px solid var(--ops-line-faint)",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

interface RowProps {
  trade: Trade;
  onSelect: (trade: Trade) => void;
}

const TradeRow = memo(function TradeRow({ trade, onSelect }: RowProps) {
  const timeStr = formatTime(trade.closed_at ?? trade.opened_at ?? trade.created_at);
  const direction = trade.direction ?? (trade.side === "buy" ? "LONG" : "SHORT");

  return (
    <tr
      onClick={() => onSelect(trade)}
      style={{ cursor: "pointer", background: "transparent", transition: "background 100ms" } as CSSProperties}
      onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "var(--ops-bg-hover)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "transparent"; }}
    >
      <td style={{ ...cellStyle, color: "var(--ops-fg-dim)", fontSize: "0.68rem" }}>{timeStr}</td>
      <td style={{ ...cellStyle, fontWeight: 600 }}>{trade.pair}</td>
      <td style={cellStyle}>
        <span style={{
          display: "inline-block",
          padding: "0.1rem 0.4rem",
          borderRadius: 2,
          fontSize: "0.65rem",
          fontWeight: 700,
          letterSpacing: "0.06em",
          background: direction === "LONG"
            ? "color-mix(in oklch, var(--ops-ok) 15%, transparent)"
            : "color-mix(in oklch, var(--ops-crit) 15%, transparent)",
          color: direction === "LONG" ? "var(--ops-ok)" : "var(--ops-crit)",
        } as CSSProperties}>
          {direction}
        </span>
      </td>
      <td style={{ ...cellStyle, textTransform: "uppercase", fontSize: "0.68rem" }}>{trade.side}</td>
      <td style={{ ...cellStyle, textAlign: "right" }}>
        {Number.isFinite(trade.size) ? (trade.size as number).toFixed(4) : "—"}
      </td>
      <td style={{ ...cellStyle, textAlign: "right", color: "var(--ops-fg-mute)" }}>
        {trade.leverage != null ? `${trade.leverage}x` : "—"}
      </td>
      <td style={{ ...cellStyle, textAlign: "right" }}>{formatPrice(trade.entry_price)}</td>
      <td style={{ ...cellStyle, textAlign: "right", color: "var(--ops-fg-mute)" }}>{formatPrice(trade.exit_price)}</td>
      <td style={{ ...cellStyle, textAlign: "right", color: pnlColor(trade.pnl_usd), fontWeight: trade.pnl_usd != null ? 600 : 400 }}>
        {formatPnl(trade.pnl_usd)}
      </td>
      <td style={cellStyle}>
        <Tag kind={STATUS_TAG[trade.status] ?? "default"}>{String(trade.status ?? "").toUpperCase() || "—"}</Tag>
      </td>
      <td style={cellStyle}><Tag kind={trade.is_paper ? "amber" : "ok"}>{trade.is_paper ? "PAPER" : "LIVE"}</Tag></td>
    </tr>
  );
});

// ─── Mobile card row (memoized) ───────────────────────────────────────────────

const MobileTradeCard = memo(function MobileTradeCard({ trade, onSelect }: RowProps) {
  const direction = trade.direction ?? (trade.side === "buy" ? "LONG" : "SHORT");
  const timeStr = formatTime(trade.closed_at ?? trade.opened_at ?? trade.created_at);
  const dirBg = direction === "LONG"
    ? "color-mix(in oklch, var(--ops-ok) 15%, transparent)"
    : "color-mix(in oklch, var(--ops-crit) 15%, transparent)";
  const dirFg = direction === "LONG" ? "var(--ops-ok)" : "var(--ops-crit)";

  return (
    <button
      onClick={() => onSelect(trade)}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        padding: "0.75rem",
        margin: 0,
        border: 0,
        borderBottom: "1px solid var(--ops-line-faint)",
        background: "transparent",
        fontFamily: "var(--ops-mono)",
        cursor: "pointer",
        color: "var(--ops-fg)",
      } as CSSProperties}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" } as CSSProperties}>
        <span style={{ fontSize: "0.85rem", fontWeight: 700 } as CSSProperties}>{trade.pair}</span>
        <span style={{ display: "flex", gap: "0.35rem", alignItems: "center" } as CSSProperties}>
          <span style={{
            padding: "0.1rem 0.4rem", borderRadius: 2, fontSize: "0.6rem",
            fontWeight: 700, letterSpacing: "0.06em", background: dirBg, color: dirFg,
          } as CSSProperties}>{direction}</span>
          {trade.leverage != null && (
            <span style={{ fontSize: "0.65rem", color: "var(--ops-fg-mute)" } as CSSProperties}>{trade.leverage}x</span>
          )}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginTop: "0.35rem" } as CSSProperties}>
        <span style={{ fontSize: "1rem", fontWeight: 600, color: pnlColor(trade.pnl_usd) } as CSSProperties}>
          {formatPnl(trade.pnl_usd)}
        </span>
        <span style={{ display: "flex", gap: "0.35rem", alignItems: "center" } as CSSProperties}>
          <Tag kind={STATUS_TAG[trade.status] ?? "default"}>{String(trade.status ?? "").toUpperCase() || "—"}</Tag>
          <Tag kind={trade.is_paper ? "amber" : "ok"}>{trade.is_paper ? "PAPER" : "LIVE"}</Tag>
        </span>
      </div>

      <div style={{ marginTop: "0.4rem", fontSize: "0.65rem", color: "var(--ops-fg-dim)", display: "flex", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" } as CSSProperties}>
        <span>{formatPrice(trade.entry_price)} → {formatPrice(trade.exit_price)}</span>
        <span>
          {Number.isFinite(trade.size) ? (trade.size as number).toFixed(4) : "—"} · {timeStr}
        </span>
      </div>
    </button>
  );
});

// ─── Column header ────────────────────────────────────────────────────────────

interface ColHeadProps {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  dir: SortDir;
  onSort: (key: SortKey) => void;
  align?: "left" | "right";
}

function ColHead({ label, sortKey, current, dir, onSort, align = "left" }: ColHeadProps) {
  const active = current === sortKey;
  return (
    <th
      onClick={() => onSort(sortKey)}
      style={{
        padding: "0.4rem 0.6rem",
        fontFamily: "var(--ops-mono)",
        fontSize: "0.6rem",
        letterSpacing: "0.1em",
        color: active ? "var(--ops-amber)" : "var(--ops-fg-dim)",
        fontWeight: 600,
        textAlign: align,
        cursor: "pointer",
        userSelect: "none",
        borderBottom: "1px solid var(--ops-line)",
        whiteSpace: "nowrap",
        background: "var(--ops-bg-elevated)",
        textTransform: "uppercase",
      } as CSSProperties}
    >
      {label}
      {active && <span style={{ marginLeft: "0.25rem", opacity: 0.7 }}>{dir === "asc" ? "↑" : "↓"}</span>}
    </th>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface TradeTableProps {
  trades: Trade[];
  onSelectTrade: (trade: Trade) => void;
}

export function TradeTable({ trades, onSelectTrade }: TradeTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [filters, setFilters] = useState<TradeFilterState>(DEFAULT_TRADE_FILTERS);
  const isMobile = useIsMobile();

  const handleSort = useCallback((key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }, [sortKey]);

  const visible = useMemo(
    () => sortTrades(filterTrades(trades, filters), sortKey, sortDir),
    [trades, filters, sortKey, sortDir]
  );

  const col = (label: string, key: SortKey, align?: "left" | "right") => ({
    label, sortKey: key, current: sortKey, dir: sortDir, onSort: handleSort, align,
  });

  if (isMobile) {
    return (
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" } as CSSProperties}>
        <TradeTableFilters filters={filters} onChange={setFilters} />
        <div style={{ flex: 1, overflowY: "auto" } as CSSProperties}>
          {visible.length === 0 ? (
            <div style={{ padding: "3rem 1rem", textAlign: "center", fontFamily: "var(--ops-mono)", fontSize: "0.75rem", color: "var(--ops-fg-dim)", lineHeight: 1.6 } as CSSProperties}>
              <div>No trades yet — Atlas will place paper trades after Oracle finds signals.</div>
              <div style={{ marginTop: "0.5rem" }}>
                <a href="/atlas/agents/oracle" style={{ color: "var(--ops-amber)", textDecoration: "underline", fontSize: "0.72rem" } as CSSProperties}>
                  View Oracle Agent →
                </a>
              </div>
            </div>
          ) : (
            visible.map((t) => <MobileTradeCard key={t.trade_id} trade={t} onSelect={onSelectTrade} />)
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" } as CSSProperties}>
      <TradeTableFilters filters={filters} onChange={setFilters} />
      <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" } as CSSProperties} aria-label="Trade blotter">
          <colgroup>
            <col style={{ width: 120 }} /><col style={{ width: 100 }} /><col style={{ width: 80 }} />
            <col style={{ width: 60 }} /><col style={{ width: 80 }} /><col style={{ width: 60 }} />
            <col style={{ width: 100 }} /><col style={{ width: 100 }} /><col style={{ width: 90 }} />
            <col style={{ width: 90 }} /><col style={{ width: 70 }} />
          </colgroup>
          <thead>
            <tr>
              <ColHead {...col("Time", "time")} />
              <ColHead {...col("Pair", "pair")} />
              <ColHead {...col("Dir", "direction")} />
              <ColHead {...col("Side", "side")} />
              <ColHead {...col("Size", "size", "right")} />
              <ColHead {...col("Lev", "leverage", "right")} />
              <ColHead {...col("Entry", "entry", "right")} />
              <ColHead {...col("Exit", "exit", "right")} />
              <ColHead {...col("P&L", "pnl", "right")} />
              <ColHead {...col("Status", "status")} />
              <ColHead {...col("Mode", "side")} />
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={11} style={{ padding: "3rem 1rem", textAlign: "center", fontFamily: "var(--ops-mono)", fontSize: "0.75rem", color: "var(--ops-fg-dim)", lineHeight: 1.6 } as CSSProperties}>
                  <div>No trades yet — Atlas will place paper trades after Oracle finds signals.</div>
                  <div style={{ marginTop: "0.5rem" }}>
                    <a href="/atlas/agents/oracle" style={{ color: "var(--ops-amber)", textDecoration: "underline", fontFamily: "var(--ops-mono)", fontSize: "0.72rem" } as CSSProperties}>
                      View Oracle Agent →
                    </a>
                  </div>
                </td>
              </tr>
            ) : (
              visible.map((t) => <TradeRow key={t.trade_id} trade={t} onSelect={onSelectTrade} />)
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
