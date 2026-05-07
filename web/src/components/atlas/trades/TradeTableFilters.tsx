"use client";

/**
 * TradeTableFilters — filter bar for the trade blotter table.
 * Split from TradeTable.tsx to keep each file under 300 lines.
 */

import { CSSProperties } from "react";
import type { TradeStatus } from "@/hooks/useTradeBlotter";

export interface TradeFilterState {
  status: TradeStatus | "all";
  pair: string;
  side: "all" | "buy" | "sell";
  mode: "all" | "paper" | "live";
  dateFrom: string;
  dateTo: string;
}

export const DEFAULT_TRADE_FILTERS: TradeFilterState = {
  status: "all",
  pair: "",
  side: "all",
  mode: "all",
  dateFrom: "",
  dateTo: "",
};

const inputStyle: CSSProperties = {
  background: "var(--ops-bg-input)",
  border: "1px solid var(--ops-line)",
  color: "var(--ops-fg)",
  fontFamily: "var(--ops-mono)",
  fontSize: "0.72rem",
  padding: "0.25rem 0.5rem",
  borderRadius: 2,
  outline: "none",
  minWidth: 0,
};

const STATUS_OPTIONS: Array<{ value: TradeFilterState["status"]; label: string }> = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "closed", label: "Closed" },
  { value: "placed", label: "Placed" },
  { value: "cancelled", label: "Cancelled" },
];

interface TradeTableFiltersProps {
  filters: TradeFilterState;
  onChange: (f: TradeFilterState) => void;
}

export function TradeTableFilters({ filters, onChange }: TradeTableFiltersProps) {
  const set = <K extends keyof TradeFilterState>(key: K, val: TradeFilterState[K]) =>
    onChange({ ...filters, [key]: val });

  return (
    <div
      style={{
        display: "flex",
        gap: "0.5rem",
        padding: "0.5rem 1rem",
        borderBottom: "1px solid var(--ops-line)",
        background: "var(--ops-bg-panel)",
        flexWrap: "wrap",
        alignItems: "center",
        flexShrink: 0,
      } as CSSProperties}
    >
      <select
        value={filters.status}
        onChange={(e) => set("status", e.target.value as TradeFilterState["status"])}
        style={inputStyle}
        aria-label="Filter by status"
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      <input
        type="text"
        value={filters.pair}
        onChange={(e) => set("pair", e.target.value)}
        placeholder="Pair (e.g. BTC/USD)"
        style={{ ...inputStyle, width: 130 }}
        aria-label="Filter by pair"
      />

      <select
        value={filters.side}
        onChange={(e) => set("side", e.target.value as TradeFilterState["side"])}
        style={inputStyle}
        aria-label="Filter by side"
      >
        <option value="all">All Sides</option>
        <option value="buy">Buy</option>
        <option value="sell">Sell</option>
      </select>

      <select
        value={filters.mode}
        onChange={(e) => set("mode", e.target.value as TradeFilterState["mode"])}
        style={inputStyle}
        aria-label="Filter by mode"
      >
        <option value="all">Paper + Live</option>
        <option value="paper">Paper Only</option>
        <option value="live">Live Only</option>
      </select>

      <input
        type="date"
        value={filters.dateFrom}
        onChange={(e) => set("dateFrom", e.target.value)}
        style={{ ...inputStyle, colorScheme: "dark" }}
        aria-label="From date"
      />

      <input
        type="date"
        value={filters.dateTo}
        onChange={(e) => set("dateTo", e.target.value)}
        style={{ ...inputStyle, colorScheme: "dark" }}
        aria-label="To date"
      />
    </div>
  );
}

// ─── Pure filter logic (exported for tests) ───────────────────────────────────

import type { Trade } from "@/hooks/useTradeBlotter";

export function filterTrades(trades: Trade[], f: TradeFilterState): Trade[] {
  return trades.filter((t) => {
    if (f.status !== "all" && t.status !== f.status) return false;
    if (f.pair && !t.pair.toLowerCase().includes(f.pair.toLowerCase())) return false;
    if (f.side !== "all" && t.side !== f.side) return false;
    if (f.mode === "paper" && !t.is_paper) return false;
    if (f.mode === "live" && t.is_paper) return false;
    const timeStr = t.closed_at ?? t.opened_at ?? t.created_at;
    if (f.dateFrom && timeStr < f.dateFrom) return false;
    if (f.dateTo && timeStr > f.dateTo + "T23:59:59") return false;
    return true;
  });
}
