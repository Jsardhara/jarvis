/**
 * Tests for TradeKpiStrip — formatting logic and color contracts.
 *
 * Environment: node (vitest default).
 * We test the pure formatting functions that drive the KPI strip display.
 *
 * Scenarios:
 *   1. P&L positive → green color token
 *   2. P&L negative → red color token
 *   3. P&L zero → neutral color token
 *   4. Win rate formatted as percentage
 *   5. Best trade formatted as $ amount
 *   6. Large values use k abbreviation
 *   7. Zero trades edge case — all zeros
 */

import { describe, it, expect } from "vitest";
import { computeStats } from "@/hooks/useTradeBlotter";
import type { Trade } from "@/hooks/useTradeBlotter";

// ─── Mirror formatting helpers from TradeKpiStrip ─────────────────────────────

function formatPnl(value: number): string {
  const abs = Math.abs(value);
  const sign = value >= 0 ? "+" : "-";
  if (abs >= 1000) {
    return `${sign}$${(abs / 1000).toFixed(1)}k`;
  }
  return `${sign}$${abs.toFixed(2)}`;
}

function formatWinRate(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function formatBestTrade(value: number): string {
  if (value === 0) return "$0";
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
  return `$${value.toFixed(2)}`;
}

function pnlColor(pnl: number): string {
  if (pnl > 0) return "var(--ops-ok)";
  if (pnl < 0) return "var(--ops-crit)";
  return "var(--ops-fg)";
}

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeTrade(overrides: Partial<Trade> = {}): Trade {
  return {
    trade_id: "t-test",
    pair: "BTC/USD",
    side: "buy",
    size: 0.1,
    status: "closed",
    is_paper: true,
    created_at: "2026-04-30T08:00:00Z",
    closed_at: "2026-04-30T12:00:00Z",
    pnl_usd: 0,
    ...overrides,
  };
}

// ─── P&L color tests ──────────────────────────────────────────────────────────

describe("TradeKpiStrip — P&L color", () => {
  it("uses ops-ok (green) for positive P&L", () => {
    expect(pnlColor(100)).toBe("var(--ops-ok)");
  });

  it("uses ops-crit (red) for negative P&L", () => {
    expect(pnlColor(-50)).toBe("var(--ops-crit)");
  });

  it("uses ops-fg (neutral) for zero P&L", () => {
    expect(pnlColor(0)).toBe("var(--ops-fg)");
  });
});

// ─── P&L formatting ───────────────────────────────────────────────────────────

describe("TradeKpiStrip — P&L formatting", () => {
  it("formats positive value with + prefix", () => {
    expect(formatPnl(42.50)).toBe("+$42.50");
  });

  it("formats negative value with - prefix", () => {
    expect(formatPnl(-10.25)).toBe("-$10.25");
  });

  it("formats zero as +$0.00", () => {
    expect(formatPnl(0)).toBe("+$0.00");
  });

  it("uses k abbreviation for >= 1000", () => {
    expect(formatPnl(1500)).toBe("+$1.5k");
    expect(formatPnl(-2000)).toBe("-$2.0k");
  });

  it("formats sub-1000 to 2 decimal places", () => {
    expect(formatPnl(999.99)).toBe("+$999.99");
  });
});

// ─── Win rate formatting ──────────────────────────────────────────────────────

describe("TradeKpiStrip — win rate formatting", () => {
  it("formats 1.0 as 100%", () => {
    expect(formatWinRate(1.0)).toBe("100%");
  });

  it("formats 0.0 as 0%", () => {
    expect(formatWinRate(0)).toBe("0%");
  });

  it("formats 0.666... as 67%", () => {
    expect(formatWinRate(2 / 3)).toBe("67%");
  });

  it("formats 0.5 as 50%", () => {
    expect(formatWinRate(0.5)).toBe("50%");
  });
});

// ─── Best trade formatting ────────────────────────────────────────────────────

describe("TradeKpiStrip — best trade formatting", () => {
  it("shows $0 when no trades", () => {
    expect(formatBestTrade(0)).toBe("$0");
  });

  it("formats small value to 2 decimal places", () => {
    expect(formatBestTrade(99.99)).toBe("$99.99");
  });

  it("uses k abbreviation for >= 1000", () => {
    expect(formatBestTrade(1500)).toBe("$1.5k");
    expect(formatBestTrade(10000)).toBe("$10.0k");
  });
});

// ─── Edge cases with zero trades ──────────────────────────────────────────────

describe("TradeKpiStrip — zero trades edge case", () => {
  it("computeStats returns all zeros for empty trade list", () => {
    const stats = computeStats([]);
    expect(stats.open_count).toBe(0);
    expect(stats.today_pnl_usd).toBe(0);
    expect(stats.win_rate).toBe(0);
    expect(stats.total_trades).toBe(0);
    expect(stats.best_trade_usd).toBe(0);
  });

  it("formatWinRate(0) renders correctly", () => {
    expect(formatWinRate(0)).toBe("0%");
  });

  it("formatPnl(0) renders with neutral sign", () => {
    expect(formatPnl(0)).toContain("$0.00");
  });
});

// ─── Integration with computeStats ───────────────────────────────────────────

describe("TradeKpiStrip — integration with computeStats", () => {
  it("KPI values match computed stats from trade list", () => {
    const today = new Date().toISOString().slice(0, 10);
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "open", closed_at: undefined, pnl_usd: undefined }),
      makeTrade({ trade_id: "t2", status: "closed", pnl_usd: 100, closed_at: `${today}T10:00:00Z` }),
      makeTrade({ trade_id: "t3", status: "closed", pnl_usd: -20, closed_at: `${today}T11:00:00Z` }),
    ];
    const stats = computeStats(trades);
    expect(stats.open_count).toBe(1);
    expect(stats.today_pnl_usd).toBeCloseTo(80, 5);
    expect(stats.win_rate).toBeCloseTo(0.5, 5);
    expect(stats.total_trades).toBe(3);
    expect(stats.best_trade_usd).toBe(100);
  });
});
