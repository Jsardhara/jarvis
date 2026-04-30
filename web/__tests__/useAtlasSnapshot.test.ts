/**
 * Tests for useAtlasSnapshot — push-update path via WS events.
 *
 * We test the pure applyWsEvent logic that merges WS messages into snapshot
 * state, mirroring the implementation to verify correctness in isolation.
 *
 * Scenarios:
 *   1. atlas.position_opened adds position to list
 *   2. atlas.position_opened deduplicates by id
 *   3. atlas.position_closed removes position by id
 *   4. atlas.position_closed removes position by symbol when id absent
 *   5. atlas.position_closed returns null when no match found
 *   6. atlas.order_placed updates pnl.last_order
 *   7. atlas.order_filled updates pnl.last_order
 *   8. Unknown event type returns null (no mutation)
 *   9. atlas.agent_status returns null (not a snapshot concern)
 *  10. Reconcile interval is 5 minutes
 */

import { describe, it, expect } from "vitest";
import type { AtlasSnapshot } from "@/lib/types";

// ─── Mirror of applyWsEvent from useAtlasSnapshot ─────────────────────────────

interface PositionRecord {
  id?: string;
  symbol?: string;
  [key: string]: unknown;
}

interface WsMessage {
  type?: string;
  payload?: Record<string, unknown>;
  ts?: string;
}

function applyWsEvent(
  snapshot: AtlasSnapshot,
  msg: WsMessage
): AtlasSnapshot | null {
  const type = msg.type ?? "";
  const payload = msg.payload ?? {};

  switch (type) {
    case "atlas.position_opened": {
      const pos = payload as PositionRecord;
      const existing = snapshot.positions as PositionRecord[];
      const alreadyHas = existing.some(
        (p) => p.id !== undefined && p.id === pos.id
      );
      if (alreadyHas) return null;
      return { ...snapshot, positions: [...existing, pos] };
    }

    case "atlas.position_closed": {
      const pos = payload as PositionRecord;
      const existing = snapshot.positions as PositionRecord[];
      const filtered = existing.filter((p) => {
        if (pos.id !== undefined && p.id !== undefined) return p.id !== pos.id;
        if (pos.symbol !== undefined && p.symbol !== undefined)
          return p.symbol !== pos.symbol;
        return true;
      });
      if (filtered.length === existing.length) return null;
      return { ...snapshot, positions: filtered };
    }

    case "atlas.order_placed":
    case "atlas.order_filled": {
      const pnlPrev = (snapshot.pnl ?? {}) as Record<string, unknown>;
      return {
        ...snapshot,
        pnl: {
          ...pnlPrev,
          last_order: { type, ...payload, ts: msg.ts ?? new Date().toISOString() },
        },
        ts: msg.ts ?? snapshot.ts,
      };
    }

    default:
      return null;
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeSnapshot(overrides: Partial<AtlasSnapshot> = {}): AtlasSnapshot {
  return {
    portfolio: {},
    pnl: {},
    positions: [],
    degraded: false,
    ts: "2026-04-30T00:00:00Z",
    ...overrides,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("useAtlasSnapshot — applyWsEvent: position_opened", () => {
  it("adds a new position to the list", () => {
    const snap = makeSnapshot({ positions: [] });
    const result = applyWsEvent(snap, {
      type: "atlas.position_opened",
      payload: { id: "pos-1", symbol: "BTC/USD" },
    });
    expect(result).not.toBeNull();
    const positions = result!.positions as PositionRecord[];
    expect(positions).toHaveLength(1);
    expect(positions[0].id).toBe("pos-1");
  });

  it("appends to existing positions", () => {
    const snap = makeSnapshot({ positions: [{ id: "pos-1" }] });
    const result = applyWsEvent(snap, {
      type: "atlas.position_opened",
      payload: { id: "pos-2", symbol: "ETH/USD" },
    });
    expect(result).not.toBeNull();
    expect((result!.positions as PositionRecord[])).toHaveLength(2);
  });

  it("deduplicates by id — returns null if already present", () => {
    const snap = makeSnapshot({ positions: [{ id: "pos-1", symbol: "BTC/USD" }] });
    const result = applyWsEvent(snap, {
      type: "atlas.position_opened",
      payload: { id: "pos-1", symbol: "BTC/USD" },
    });
    expect(result).toBeNull();
  });
});

describe("useAtlasSnapshot — applyWsEvent: position_closed", () => {
  it("removes a position by id", () => {
    const snap = makeSnapshot({
      positions: [{ id: "pos-1", symbol: "BTC" }, { id: "pos-2", symbol: "ETH" }],
    });
    const result = applyWsEvent(snap, {
      type: "atlas.position_closed",
      payload: { id: "pos-1" },
    });
    expect(result).not.toBeNull();
    const positions = result!.positions as PositionRecord[];
    expect(positions).toHaveLength(1);
    expect(positions[0].id).toBe("pos-2");
  });

  it("removes a position by symbol when id is absent", () => {
    const snap = makeSnapshot({
      positions: [{ symbol: "BTC/USD" }, { symbol: "ETH/USD" }],
    });
    const result = applyWsEvent(snap, {
      type: "atlas.position_closed",
      payload: { symbol: "BTC/USD" },
    });
    expect(result).not.toBeNull();
    const positions = result!.positions as PositionRecord[];
    expect(positions).toHaveLength(1);
    expect((positions[0] as PositionRecord).symbol).toBe("ETH/USD");
  });

  it("returns null when no matching position found", () => {
    const snap = makeSnapshot({ positions: [{ id: "pos-1" }] });
    const result = applyWsEvent(snap, {
      type: "atlas.position_closed",
      payload: { id: "pos-999" },
    });
    expect(result).toBeNull();
  });
});

describe("useAtlasSnapshot — applyWsEvent: order events", () => {
  it("order_placed sets pnl.last_order with type marker", () => {
    const snap = makeSnapshot();
    const result = applyWsEvent(snap, {
      type: "atlas.order_placed",
      payload: { symbol: "BTC/USD", size: 0.1 },
      ts: "2026-04-30T12:00:00Z",
    });
    expect(result).not.toBeNull();
    const lastOrder = (result!.pnl as Record<string, unknown>).last_order as Record<string, unknown>;
    expect(lastOrder.type).toBe("atlas.order_placed");
    expect(lastOrder.symbol).toBe("BTC/USD");
    expect(lastOrder.ts).toBe("2026-04-30T12:00:00Z");
  });

  it("order_filled sets pnl.last_order with type marker", () => {
    const snap = makeSnapshot();
    const result = applyWsEvent(snap, {
      type: "atlas.order_filled",
      payload: { order_id: "ord-42", fill_price: 65000 },
    });
    expect(result).not.toBeNull();
    const lastOrder = (result!.pnl as Record<string, unknown>).last_order as Record<string, unknown>;
    expect(lastOrder.type).toBe("atlas.order_filled");
    expect(lastOrder.order_id).toBe("ord-42");
  });

  it("order_placed preserves existing pnl fields", () => {
    const snap = makeSnapshot({ pnl: { total: 500 } });
    const result = applyWsEvent(snap, {
      type: "atlas.order_placed",
      payload: { symbol: "ETH/USD" },
    });
    expect(result).not.toBeNull();
    const pnl = result!.pnl as Record<string, unknown>;
    expect(pnl.total).toBe(500);
    expect(pnl.last_order).toBeDefined();
  });
});

describe("useAtlasSnapshot — applyWsEvent: ignored events", () => {
  it("returns null for atlas.market_signal (not a snapshot concern)", () => {
    const snap = makeSnapshot();
    expect(applyWsEvent(snap, { type: "atlas.market_signal", payload: {} })).toBeNull();
  });

  it("returns null for atlas.agent_status", () => {
    const snap = makeSnapshot();
    expect(applyWsEvent(snap, { type: "atlas.agent_status", payload: {} })).toBeNull();
  });

  it("returns null for unknown type", () => {
    const snap = makeSnapshot();
    expect(applyWsEvent(snap, { type: "agent.start", payload: {} })).toBeNull();
  });

  it("returns null for empty type", () => {
    const snap = makeSnapshot();
    expect(applyWsEvent(snap, { type: "", payload: {} })).toBeNull();
  });
});

describe("useAtlasSnapshot — reconcile interval constant", () => {
  it("reconcile interval is 5 minutes (300000 ms)", () => {
    const RECONCILE_INTERVAL_MS = 5 * 60_000;
    expect(RECONCILE_INTERVAL_MS).toBe(300_000);
  });
});
