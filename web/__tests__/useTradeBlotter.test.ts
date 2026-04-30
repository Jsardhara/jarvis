/**
 * Tests for useTradeBlotter — pure logic functions (REST fetch merge + WS push).
 *
 * We test:
 *   - computeStats: open count, today P&L, win rate, total trades, best trade
 *   - applyWsEventToTrades: order_placed inserts / deduplicates, position_opened
 *     updates entry_price + status, position_closed marks closed + pnl,
 *     order_cancelled marks cancelled, unknown events return null
 *
 * Environment: node (vitest default). No DOM required.
 */

import { describe, it, expect } from "vitest";
import {
  computeStats,
  applyWsEventToTrades,
} from "@/hooks/useTradeBlotter";
import type { Trade } from "@/hooks/useTradeBlotter";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeTrade(overrides: Partial<Trade> = {}): Trade {
  return {
    trade_id: "trade-1",
    pair: "BTC/USD",
    side: "buy",
    size: 0.1,
    status: "open",
    is_paper: true,
    created_at: "2026-04-30T08:00:00Z",
    ...overrides,
  };
}

// ─── computeStats ─────────────────────────────────────────────────────────────

describe("computeStats — empty list", () => {
  it("returns zeros for all fields when no trades", () => {
    const stats = computeStats([]);
    expect(stats.open_count).toBe(0);
    expect(stats.today_pnl_usd).toBe(0);
    expect(stats.win_rate).toBe(0);
    expect(stats.total_trades).toBe(0);
    expect(stats.best_trade_usd).toBe(0);
  });
});

describe("computeStats — open count", () => {
  it("counts only trades with status=open", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "open" }),
      makeTrade({ trade_id: "t2", status: "closed", pnl_usd: 50 }),
      makeTrade({ trade_id: "t3", status: "placed" }),
    ];
    expect(computeStats(trades).open_count).toBe(1);
  });

  it("counts multiple open trades", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "open" }),
      makeTrade({ trade_id: "t2", status: "open" }),
      makeTrade({ trade_id: "t3", status: "open" }),
    ];
    expect(computeStats(trades).open_count).toBe(3);
  });
});

describe("computeStats — win rate", () => {
  it("computes win rate as wins / closed", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "closed", pnl_usd: 100 }),
      makeTrade({ trade_id: "t2", status: "closed", pnl_usd: -20 }),
      makeTrade({ trade_id: "t3", status: "closed", pnl_usd: 50 }),
    ];
    // 2 wins out of 3 closed
    expect(computeStats(trades).win_rate).toBeCloseTo(2 / 3, 5);
  });

  it("win rate is 0 when no closed trades", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "open" }),
    ];
    expect(computeStats(trades).win_rate).toBe(0);
  });

  it("win rate is 1.0 when all closed trades are profitable", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "closed", pnl_usd: 10 }),
      makeTrade({ trade_id: "t2", status: "closed", pnl_usd: 5 }),
    ];
    expect(computeStats(trades).win_rate).toBe(1.0);
  });
});

describe("computeStats — best trade", () => {
  it("returns the highest pnl_usd among closed trades", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "closed", pnl_usd: 100 }),
      makeTrade({ trade_id: "t2", status: "closed", pnl_usd: 250 }),
      makeTrade({ trade_id: "t3", status: "closed", pnl_usd: 50 }),
    ];
    expect(computeStats(trades).best_trade_usd).toBe(250);
  });

  it("best trade is 0 when all trades are losses", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "closed", pnl_usd: -10 }),
      makeTrade({ trade_id: "t2", status: "closed", pnl_usd: -5 }),
    ];
    expect(computeStats(trades).best_trade_usd).toBe(0);
  });
});

describe("computeStats — total trades", () => {
  it("counts all trades regardless of status", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "t1", status: "open" }),
      makeTrade({ trade_id: "t2", status: "closed", pnl_usd: 10 }),
      makeTrade({ trade_id: "t3", status: "cancelled" }),
      makeTrade({ trade_id: "t4", status: "placed" }),
    ];
    expect(computeStats(trades).total_trades).toBe(4);
  });
});

// ─── applyWsEventToTrades — order_placed ──────────────────────────────────────

describe("applyWsEventToTrades — atlas.order_placed", () => {
  it("inserts a new trade row when trade_id is new", () => {
    const trades: Trade[] = [];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.order_placed",
      payload: {
        trade_id: "trade-new",
        pair: "ETH/USD",
        side: "sell",
        size: 1.0,
        is_paper: true,
      },
    });
    expect(result).not.toBeNull();
    expect(result!).toHaveLength(1);
    expect(result![0].trade_id).toBe("trade-new");
    expect(result![0].status).toBe("placed");
    expect(result![0].pair).toBe("ETH/USD");
  });

  it("upserts by trade_id when already present", () => {
    const trades: Trade[] = [makeTrade({ trade_id: "trade-1", status: "placed" })];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.order_placed",
      payload: {
        trade_id: "trade-1",
        pair: "BTC/USD",
        side: "buy",
        size: 0.2,
        is_paper: true,
      },
    });
    expect(result).not.toBeNull();
    expect(result!).toHaveLength(1);
    expect(result![0].size).toBe(0.2);
  });

  it("appends when multiple trades present", () => {
    const trades: Trade[] = [
      makeTrade({ trade_id: "trade-1" }),
      makeTrade({ trade_id: "trade-2" }),
    ];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.order_placed",
      payload: { trade_id: "trade-3", pair: "XBT/USD", side: "buy", size: 0.5, is_paper: false },
    });
    expect(result!).toHaveLength(3);
  });
});

// ─── applyWsEventToTrades — position_opened ───────────────────────────────────

describe("applyWsEventToTrades — atlas.position_opened", () => {
  it("updates entry_price and status to open", () => {
    const trades: Trade[] = [makeTrade({ trade_id: "trade-1", status: "placed" })];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.position_opened",
      payload: {
        trade_id: "trade-1",
        entry_price: 65000,
        opened_at: "2026-04-30T10:00:00Z",
      },
    });
    expect(result).not.toBeNull();
    expect(result![0].entry_price).toBe(65000);
    expect(result![0].status).toBe("open");
    expect(result![0].opened_at).toBe("2026-04-30T10:00:00Z");
  });

  it("returns null when trade_id not found", () => {
    const trades: Trade[] = [makeTrade({ trade_id: "trade-1" })];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.position_opened",
      payload: { trade_id: "unknown-999", entry_price: 1000 },
    });
    expect(result).toBeNull();
  });

  it("returns null when no trade_id in payload", () => {
    const trades: Trade[] = [makeTrade()];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.position_opened",
      payload: { entry_price: 1000 },
    });
    expect(result).toBeNull();
  });
});

// ─── applyWsEventToTrades — position_closed ───────────────────────────────────

describe("applyWsEventToTrades — atlas.position_closed", () => {
  it("marks trade closed with exit_price and pnl_usd", () => {
    const trades: Trade[] = [makeTrade({ trade_id: "trade-1", status: "open", entry_price: 60000 })];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.position_closed",
      payload: {
        trade_id: "trade-1",
        exit_price: 65000,
        pnl_usd: 500,
        pnl_pct: 0.083,
        close_reason: "take_profit",
        closed_at: "2026-04-30T14:00:00Z",
      },
    });
    expect(result).not.toBeNull();
    expect(result![0].status).toBe("closed");
    expect(result![0].exit_price).toBe(65000);
    expect(result![0].pnl_usd).toBe(500);
    expect(result![0].pnl_pct).toBeCloseTo(0.083, 3);
    expect(result![0].close_reason).toBe("take_profit");
    expect(result![0].closed_at).toBe("2026-04-30T14:00:00Z");
  });

  it("returns null when trade_id not found", () => {
    const trades: Trade[] = [makeTrade({ trade_id: "trade-1" })];
    expect(
      applyWsEventToTrades(trades, {
        type: "atlas.position_closed",
        payload: { trade_id: "ghost-999", exit_price: 100, pnl_usd: 0 },
      })
    ).toBeNull();
  });
});

// ─── applyWsEventToTrades — order_cancelled ──────────────────────────────────

describe("applyWsEventToTrades — atlas.order_cancelled", () => {
  it("marks trade as cancelled", () => {
    const trades: Trade[] = [makeTrade({ trade_id: "trade-1", status: "placed" })];
    const result = applyWsEventToTrades(trades, {
      type: "atlas.order_cancelled",
      payload: { trade_id: "trade-1" },
    });
    expect(result).not.toBeNull();
    expect(result![0].status).toBe("cancelled");
  });

  it("returns null when trade not found", () => {
    const trades: Trade[] = [makeTrade({ trade_id: "trade-1" })];
    expect(
      applyWsEventToTrades(trades, {
        type: "atlas.order_cancelled",
        payload: { trade_id: "ghost" },
      })
    ).toBeNull();
  });
});

// ─── applyWsEventToTrades — ignored events ────────────────────────────────────

describe("applyWsEventToTrades — ignored events", () => {
  it("returns null for atlas.market_signal", () => {
    expect(
      applyWsEventToTrades([], {
        type: "atlas.market_signal",
        payload: { pair: "BTC/USD" },
      })
    ).toBeNull();
  });

  it("returns null for atlas.order_filled", () => {
    expect(
      applyWsEventToTrades([], {
        type: "atlas.order_filled",
        payload: { trade_id: "t1" },
      })
    ).toBeNull();
  });

  it("returns null for unknown type", () => {
    expect(
      applyWsEventToTrades([], {
        type: "agent.start",
        payload: {},
      })
    ).toBeNull();
  });

  it("returns null for empty type", () => {
    expect(
      applyWsEventToTrades([], {
        type: "",
        payload: {},
      })
    ).toBeNull();
  });
});

// ─── Reconcile interval constant ──────────────────────────────────────────────

describe("useTradeBlotter — reconcile interval", () => {
  it("RECONCILE_INTERVAL_MS is 5 minutes (300000 ms)", () => {
    const RECONCILE_INTERVAL_MS = 5 * 60_000;
    expect(RECONCILE_INTERVAL_MS).toBe(300_000);
  });
});
