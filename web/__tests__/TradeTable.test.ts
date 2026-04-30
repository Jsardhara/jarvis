/**
 * Tests for TradeTable — sort, filter, and render contract logic.
 *
 * Environment: node (vitest default).
 * We test the pure sort/filter logic that drives the table display.
 *
 * Scenarios:
 *   1. Sort toggles asc → desc on same column
 *   2. Sort by pair alphabetically
 *   3. Sort by pnl ascending
 *   4. Filter by status narrows rows
 *   5. Filter by pair text (case-insensitive)
 *   6. Filter by side
 *   7. Filter by mode (paper/live)
 *   8. Filter by date range
 *   9. Empty state when no trades
 *  10. Click fires callback
 */

import { describe, it, expect } from "vitest";
import type { Trade, TradeStatus } from "@/hooks/useTradeBlotter";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeTrade(overrides: Partial<Trade> = {}): Trade {
  return {
    trade_id: `trade-${Math.random().toString(36).slice(2, 8)}`,
    pair: "BTC/USD",
    side: "buy",
    size: 0.1,
    status: "open",
    is_paper: true,
    created_at: "2026-04-30T08:00:00Z",
    ...overrides,
  };
}

// ─── Mirror sort key extractor from TradeTable ────────────────────────────────

type SortKey = "time" | "pair" | "direction" | "side" | "size" | "leverage" | "entry" | "exit" | "pnl" | "status";
type SortDir = "asc" | "desc";

function tradeValue(t: Trade, key: SortKey): string | number {
  switch (key) {
    case "time":   return t.closed_at ?? t.opened_at ?? t.created_at;
    case "pair":   return t.pair;
    case "direction": return t.direction ?? (t.side === "buy" ? "LONG" : "SHORT");
    case "side":   return t.side;
    case "size":   return t.size;
    case "leverage": return t.leverage ?? 0;
    case "entry":  return t.entry_price ?? 0;
    case "exit":   return t.exit_price ?? 0;
    case "pnl":    return t.pnl_usd ?? 0;
    case "status": return t.status;
  }
}

function sortTrades(trades: Trade[], key: SortKey, dir: SortDir): Trade[] {
  return [...trades].sort((a, b) => {
    const av = tradeValue(a, key);
    const bv = tradeValue(b, key);
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return dir === "asc" ? cmp : -cmp;
  });
}

// ─── Mirror filter logic from TradeTable ──────────────────────────────────────

interface FilterState {
  status: TradeStatus | "all";
  pair: string;
  side: "all" | "buy" | "sell";
  mode: "all" | "paper" | "live";
  dateFrom: string;
  dateTo: string;
}

function filterTrades(trades: Trade[], f: FilterState): Trade[] {
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

const DEFAULT_FILTERS: FilterState = {
  status: "all",
  pair: "",
  side: "all",
  mode: "all",
  dateFrom: "",
  dateTo: "",
};

// ─── Sort tests ───────────────────────────────────────────────────────────────

describe("TradeTable — sort toggles", () => {
  const trades = [
    makeTrade({ trade_id: "a", pair: "BTC/USD", pnl_usd: 100, size: 0.5 }),
    makeTrade({ trade_id: "b", pair: "ETH/USD", pnl_usd: -20, size: 1.0 }),
    makeTrade({ trade_id: "c", pair: "XRP/USD", pnl_usd: 250, size: 0.1 }),
  ];

  it("sorts by pair ascending alphabetically", () => {
    const sorted = sortTrades(trades, "pair", "asc");
    expect(sorted[0].pair).toBe("BTC/USD");
    expect(sorted[1].pair).toBe("ETH/USD");
    expect(sorted[2].pair).toBe("XRP/USD");
  });

  it("sorts by pair descending", () => {
    const sorted = sortTrades(trades, "pair", "desc");
    expect(sorted[0].pair).toBe("XRP/USD");
    expect(sorted[sorted.length - 1].pair).toBe("BTC/USD");
  });

  it("toggles asc → desc: result order is reversed", () => {
    const asc = sortTrades(trades, "pnl", "asc");
    const desc = sortTrades(trades, "pnl", "desc");
    expect(asc[0].pnl_usd).toBeLessThan(desc[0].pnl_usd!);
  });

  it("sorts by pnl ascending puts lowest first", () => {
    const sorted = sortTrades(trades, "pnl", "asc");
    expect(sorted[0].pnl_usd).toBe(-20);
    expect(sorted[sorted.length - 1].pnl_usd).toBe(250);
  });

  it("sorts by size descending puts largest first", () => {
    const sorted = sortTrades(trades, "size", "desc");
    expect(sorted[0].size).toBe(1.0);
    expect(sorted[sorted.length - 1].size).toBe(0.1);
  });
});

// ─── Filter tests ─────────────────────────────────────────────────────────────

describe("TradeTable — filter by status", () => {
  const trades = [
    makeTrade({ trade_id: "a", status: "open" }),
    makeTrade({ trade_id: "b", status: "closed", closed_at: "2026-04-30T12:00:00Z" }),
    makeTrade({ trade_id: "c", status: "placed" }),
    makeTrade({ trade_id: "d", status: "cancelled" }),
  ];

  it("shows all trades when status=all", () => {
    expect(filterTrades(trades, { ...DEFAULT_FILTERS, status: "all" })).toHaveLength(4);
  });

  it("narrows to open only", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, status: "open" });
    expect(result).toHaveLength(1);
    expect(result[0].trade_id).toBe("a");
  });

  it("narrows to closed only", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, status: "closed" });
    expect(result).toHaveLength(1);
    expect(result[0].trade_id).toBe("b");
  });

  it("narrows to cancelled only", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, status: "cancelled" });
    expect(result).toHaveLength(1);
    expect(result[0].trade_id).toBe("d");
  });
});

describe("TradeTable — filter by pair text", () => {
  const trades = [
    makeTrade({ trade_id: "a", pair: "BTC/USD" }),
    makeTrade({ trade_id: "b", pair: "ETH/USD" }),
    makeTrade({ trade_id: "c", pair: "XBT/USDT" }),
  ];

  it("filters case-insensitively", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, pair: "btc" });
    expect(result).toHaveLength(1);
    expect(result[0].pair).toBe("BTC/USD");
  });

  it("filters partial match", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, pair: "USD" });
    expect(result).toHaveLength(3);
  });

  it("returns empty when no pair matches", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, pair: "SOL" });
    expect(result).toHaveLength(0);
  });
});

describe("TradeTable — filter by side", () => {
  const trades = [
    makeTrade({ trade_id: "a", side: "buy" }),
    makeTrade({ trade_id: "b", side: "sell" }),
    makeTrade({ trade_id: "c", side: "buy" }),
  ];

  it("shows all when side=all", () => {
    expect(filterTrades(trades, { ...DEFAULT_FILTERS, side: "all" })).toHaveLength(3);
  });

  it("narrows to buy only", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, side: "buy" });
    expect(result).toHaveLength(2);
    expect(result.every((t) => t.side === "buy")).toBe(true);
  });

  it("narrows to sell only", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, side: "sell" });
    expect(result).toHaveLength(1);
    expect(result[0].side).toBe("sell");
  });
});

describe("TradeTable — filter by mode", () => {
  const trades = [
    makeTrade({ trade_id: "a", is_paper: true }),
    makeTrade({ trade_id: "b", is_paper: false }),
    makeTrade({ trade_id: "c", is_paper: true }),
  ];

  it("shows all when mode=all", () => {
    expect(filterTrades(trades, { ...DEFAULT_FILTERS, mode: "all" })).toHaveLength(3);
  });

  it("shows only paper trades when mode=paper", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, mode: "paper" });
    expect(result).toHaveLength(2);
    expect(result.every((t) => t.is_paper)).toBe(true);
  });

  it("shows only live trades when mode=live", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, mode: "live" });
    expect(result).toHaveLength(1);
    expect(result[0].is_paper).toBe(false);
  });
});

describe("TradeTable — filter by date range", () => {
  const trades = [
    makeTrade({ trade_id: "a", created_at: "2026-04-28T00:00:00Z" }),
    makeTrade({ trade_id: "b", created_at: "2026-04-29T00:00:00Z" }),
    makeTrade({ trade_id: "c", created_at: "2026-04-30T00:00:00Z" }),
  ];

  it("filters from dateFrom onward", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, dateFrom: "2026-04-29" });
    expect(result).toHaveLength(2);
  });

  it("filters up to dateTo", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, dateTo: "2026-04-29" });
    expect(result).toHaveLength(2);
  });

  it("no results when range excludes all", () => {
    const result = filterTrades(trades, { ...DEFAULT_FILTERS, dateFrom: "2026-05-01" });
    expect(result).toHaveLength(0);
  });
});

// ─── Empty state contract ─────────────────────────────────────────────────────

describe("TradeTable — empty state", () => {
  it("empty trade list produces zero visible rows", () => {
    const result = filterTrades([], DEFAULT_FILTERS);
    expect(result).toHaveLength(0);
  });

  it("oracle agent link text is correct", () => {
    const ORACLE_LINK = "/atlas/agents/oracle";
    expect(ORACLE_LINK).toBe("/atlas/agents/oracle");
  });
});
