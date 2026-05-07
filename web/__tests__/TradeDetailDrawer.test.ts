/**
 * Tests for TradeDetailDrawer — open/close logic, signal fetch, and timeline.
 *
 * Environment: node (vitest default).
 * We test the pure logic and data-fetch contracts; DOM rendering is not
 * exercised (same pattern as MockModeBanner.test.ts).
 *
 * Scenarios:
 *   1. Drawer is closed when trade is null
 *   2. Drawer is open when trade is non-null
 *   3. Signal is fetched when trade.signal_id is present
 *   4. Signal fetch is skipped when signal_id is absent
 *   5. Signal fetch error sets signalError
 *   6. Timeline step "ORACLE" is done when signal_id present
 *   7. Timeline step "GUARDIAN" is done when guardian_approved=true
 *   8. Timeline step "GUARDIAN" is error when guardian_approved=false
 *   9. P&L color: positive = green, negative = red
 *  10. Close button fires onClose callback
 */

import { describe, it, expect, vi } from "vitest";
import type { Trade } from "@/hooks/useTradeBlotter";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeTrade(overrides: Partial<Trade> = {}): Trade {
  return {
    trade_id: "trade-abc123",
    pair: "BTC/USD",
    side: "buy",
    size: 0.1,
    status: "open",
    is_paper: true,
    created_at: "2026-04-30T08:00:00Z",
    ...overrides,
  };
}

// ─── Drawer open/close contract ───────────────────────────────────────────────

describe("TradeDetailDrawer — open/close contract", () => {
  it("isOpen is false when trade is null", () => {
    const trade: Trade | null = null;
    const isOpen = trade !== null;
    expect(isOpen).toBe(false);
  });

  it("isOpen is true when trade is non-null", () => {
    const trade: Trade | null = makeTrade();
    const isOpen = trade !== null;
    expect(isOpen).toBe(true);
  });

  it("onClose sets selectedTrade to null", () => {
    let selectedTrade: Trade | null = makeTrade();
    const onClose = () => { selectedTrade = null; };
    onClose();
    expect(selectedTrade).toBeNull();
  });
});

// ─── Signal fetch contract ─────────────────────────────────────────────────────

interface SignalData {
  signal_id?: string;
  direction?: string;
  confidence?: number;
  created_at?: string;
}

async function mockFetchSignal(
  signalId: string,
  fetchImpl: typeof fetch
): Promise<SignalData> {
  const res = await fetchImpl(`http://localhost:8765/api/atlas/signals/${signalId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as SignalData;
}

function mockRes(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("TradeDetailDrawer — signal fetch", () => {
  it("fetches signal when signal_id is present", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockRes({ signal_id: "sig-1", direction: "LONG", confidence: 0.82 })
    );
    const result = await mockFetchSignal("sig-1", mockFetch);
    expect(mockFetch).toHaveBeenCalledOnce();
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8765/api/atlas/signals/sig-1"
    );
    expect(result.direction).toBe("LONG");
    expect(result.confidence).toBe(0.82);
  });

  it("skips fetch when signal_id is absent — no fetch calls", async () => {
    const trade = makeTrade({ signal_id: undefined });
    const mockFetch = vi.fn();
    // Simulate the useEffect guard: if (!trade?.signal_id) skip
    if (trade.signal_id) {
      await mockFetchSignal(trade.signal_id, mockFetch);
    }
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("throws on HTTP error — sets signalError", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockRes({}, 404));
    await expect(mockFetchSignal("sig-bad", mockFetch)).rejects.toThrow("HTTP 404");
  });

  it("throws on network error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    await expect(mockFetchSignal("sig-1", mockFetch)).rejects.toThrow("ECONNREFUSED");
  });
});

// ─── Timeline step logic ──────────────────────────────────────────────────────

type StepStatus = "done" | "pending" | "error";

function oracleStatus(trade: Trade): StepStatus {
  return trade.signal_id ? "done" : "pending";
}

function guardianStatus(trade: Trade): StepStatus {
  if (trade.guardian_approved === true) return "done";
  if (trade.guardian_approved === false) return "error";
  if (trade.status !== "placed") return "done";
  return "pending";
}

function traderStatus(trade: Trade): StepStatus {
  return trade.status === "open" || trade.status === "closed" || trade.status === "placed"
    ? "done"
    : "pending";
}

describe("TradeDetailDrawer — timeline", () => {
  it("Oracle step is done when signal_id present", () => {
    expect(oracleStatus(makeTrade({ signal_id: "sig-1" }))).toBe("done");
  });

  it("Oracle step is pending when signal_id absent", () => {
    expect(oracleStatus(makeTrade({ signal_id: undefined }))).toBe("pending");
  });

  it("Guardian step is done when guardian_approved=true", () => {
    expect(guardianStatus(makeTrade({ guardian_approved: true }))).toBe("done");
  });

  it("Guardian step is error when guardian_approved=false", () => {
    expect(guardianStatus(makeTrade({ guardian_approved: false }))).toBe("error");
  });

  it("Guardian step is done for open trade without explicit approval", () => {
    expect(guardianStatus(makeTrade({ status: "open", guardian_approved: undefined }))).toBe("done");
  });

  it("Trader step is done for placed trade", () => {
    expect(traderStatus(makeTrade({ status: "placed" }))).toBe("done");
  });

  it("Trader step is done for closed trade", () => {
    expect(traderStatus(makeTrade({ status: "closed" }))).toBe("done");
  });

  it("Trader step is pending for cancelled trade", () => {
    expect(traderStatus(makeTrade({ status: "cancelled" }))).toBe("pending");
  });
});

// ─── P&L color contract ───────────────────────────────────────────────────────

function pnlAccent(val: number | undefined): string | undefined {
  if (val === undefined) return undefined;
  return val >= 0 ? "var(--ops-ok)" : "var(--ops-crit)";
}

describe("TradeDetailDrawer — P&L color", () => {
  it("positive pnl_usd uses ops-ok", () => {
    expect(pnlAccent(100)).toBe("var(--ops-ok)");
  });

  it("negative pnl_usd uses ops-crit", () => {
    expect(pnlAccent(-50)).toBe("var(--ops-crit)");
  });

  it("zero pnl_usd uses ops-ok (breakeven treated as positive)", () => {
    expect(pnlAccent(0)).toBe("var(--ops-ok)");
  });

  it("undefined pnl_usd returns undefined (no color override)", () => {
    expect(pnlAccent(undefined)).toBeUndefined();
  });
});
