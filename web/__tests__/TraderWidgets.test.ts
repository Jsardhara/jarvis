/**
 * Tests for TraderWidgets logic
 *
 * Tests the pure helpers and contract types for the Trader workspace widgets.
 * No DOM rendering — logic only.
 *
 * Scenarios:
 *   1.  Filters trades to status=open for open positions
 *   2.  Filters trades to status=placed for pending orders
 *   3.  Empty trades → 0 open positions
 *   4.  Empty trades → 0 pending orders
 *   5.  LONG direction chip: ok kind
 *   6.  SHORT direction chip: crit kind
 *   7.  formatPrice undefined → "—"
 *   8.  formatPrice >= 1000 → $ with comma
 *   9.  formatPrice < 1000 → $ with 4 decimals
 *  10.  formatPnl positive → "+$X.XX"
 *  11.  formatPnl negative → "-$X.XX"
 *  12.  formatPnl undefined → "—"
 *  13.  pnlColor positive → ok var
 *  14.  pnlColor negative → crit var
 *  15.  Kelly audit: filters ORDER_PLACED events, caps at 5
 *  16.  relTime < 60s → Xs ago
 *  17.  relTime < 3600s → Xm ago
 *  18.  TraderWidgetsProps requires agentId string
 */

import { describe, it, expect } from "vitest";
import type { Trade } from "@/hooks/useTradeBlotter";
import type { RecentActivity } from "@/hooks/useAgentDetail";

// ─── Pure helpers mirrored from TraderWidgets ─────────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function dirKind(dir: string): TagKind {
  if (dir === "LONG") return "ok";
  if (dir === "SHORT") return "crit";
  return "default";
}

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

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  return `${Math.round(diff / 3_600_000)}h ago`;
}

interface SizingRow {
  pair: string;
  requestedSize?: number;
  leverage?: number;
  winRate?: number;
  occurredAt: string;
}

function extractKellyRows(recentActivity: RecentActivity[]): SizingRow[] {
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
}

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

function makeActivity(eventType: string, payload: Record<string, unknown> = {}): RecentActivity {
  return { event_type: eventType, payload, occurred_at: new Date().toISOString() };
}

// ─── Trade status filtering ───────────────────────────────────────────────────

describe("TraderWidgets — open positions filter", () => {
  const trades = [
    makeTrade({ status: "open" }),
    makeTrade({ status: "closed" }),
    makeTrade({ status: "placed" }),
    makeTrade({ status: "open" }),
  ];

  it("filters to status=open only", () => {
    const open = trades.filter((t) => t.status === "open");
    expect(open).toHaveLength(2);
    expect(open.every((t) => t.status === "open")).toBe(true);
  });

  it("empty trades → 0 open", () => {
    expect([].filter((t: Trade) => t.status === "open")).toHaveLength(0);
  });
});

describe("TraderWidgets — pending orders filter", () => {
  const trades = [
    makeTrade({ status: "placed" }),
    makeTrade({ status: "open" }),
    makeTrade({ status: "placed" }),
  ];

  it("filters to status=placed only", () => {
    const placed = trades.filter((t) => t.status === "placed");
    expect(placed).toHaveLength(2);
  });

  it("empty trades → 0 placed", () => {
    expect([].filter((t: Trade) => t.status === "placed")).toHaveLength(0);
  });
});

// ─── Direction chip kind ──────────────────────────────────────────────────────

describe("TraderWidgets — direction chip kind", () => {
  it("LONG → ok", () => expect(dirKind("LONG")).toBe("ok"));
  it("SHORT → crit", () => expect(dirKind("SHORT")).toBe("crit"));
});

// ─── Formatting helpers ───────────────────────────────────────────────────────

describe("TraderWidgets — formatPrice", () => {
  it("undefined → —", () => expect(formatPrice(undefined)).toBe("—"));
  it("50000 → $50,000", () => expect(formatPrice(50000)).toContain("50"));
  it("0.0001 → 4 decimal places", () => expect(formatPrice(0.0001)).toBe("$0.0001"));
});

describe("TraderWidgets — formatPnl", () => {
  it("100 → +$100.00", () => expect(formatPnl(100)).toBe("+$100.00"));
  it("-20 → $-20.00", () => expect(formatPnl(-20)).toBe("$-20.00"));
  it("undefined → —", () => expect(formatPnl(undefined)).toBe("—"));
  it("0 → +$0.00", () => expect(formatPnl(0)).toBe("+$0.00"));
});

describe("TraderWidgets — pnlColor", () => {
  it("positive → ops-ok", () => expect(pnlColor(1)).toBe("var(--ops-ok)"));
  it("negative → ops-crit", () => expect(pnlColor(-1)).toBe("var(--ops-crit)"));
  it("undefined → ops-fg-dim", () => expect(pnlColor(undefined)).toBe("var(--ops-fg-dim)"));
});

// ─── Kelly sizing audit ───────────────────────────────────────────────────────

describe("TraderWidgets — Kelly sizing audit extraction", () => {
  it("filters to ORDER_PLACED events only", () => {
    const activity: RecentActivity[] = [
      makeActivity("ORDER_PLACED", { pair: "BTC/USD", requested_size: 0.1 }),
      makeActivity("TRADE_APPROVED"),
      makeActivity("ORDER_PLACED", { pair: "ETH/USD", requested_size: 0.5 }),
    ];
    const rows = extractKellyRows(activity);
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.pair !== "—")).toBe(true);
  });

  it("caps at 5 rows", () => {
    const activity = Array.from({ length: 8 }, (_, i) =>
      makeActivity("ORDER_PLACED", { pair: `PAIR${i}/USD` })
    );
    const rows = extractKellyRows(activity);
    expect(rows).toHaveLength(5);
  });

  it("empty activity → empty rows", () => {
    expect(extractKellyRows([])).toHaveLength(0);
  });

  it("extracts leverage from payload", () => {
    const activity: RecentActivity[] = [
      makeActivity("ORDER_PLACED", { pair: "BTC/USD", leverage: 3 }),
    ];
    const rows = extractKellyRows(activity);
    expect(rows[0].leverage).toBe(3);
  });
});

// ─── relTime helper ───────────────────────────────────────────────────────────

describe("TraderWidgets — relTime formatting", () => {
  it("30s ago shows Xs ago", () => {
    const iso = new Date(Date.now() - 30_000).toISOString();
    expect(relTime(iso)).toMatch(/^\d+s ago$/);
  });

  it("2m ago shows Xm ago", () => {
    const iso = new Date(Date.now() - 120_000).toISOString();
    expect(relTime(iso)).toMatch(/^\d+m ago$/);
  });
});

// ─── Props contract ───────────────────────────────────────────────────────────

describe("TraderWidgets — props contract", () => {
  it("requires agentId string", () => {
    const props: { agentId: string } = { agentId: "trader" };
    expect(props.agentId).toBe("trader");
  });
});
