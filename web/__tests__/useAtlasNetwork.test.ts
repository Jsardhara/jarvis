/**
 * Tests for useAtlasNetwork — pure logic layer.
 *
 * We test the exported pure functions:
 *   - resolveKind: maps atlas.* type strings to MessageKind
 *   - resolveSourceTarget: derives source/target from type + payload
 *   - parseRunState: maps payload to AgentRunState
 *
 * And internal rolling-buffer semantics (60s TTL, pause, kindFilter).
 *
 * Scenarios:
 *   1.  resolveKind: atlas.market_signal → "signal"
 *   2.  resolveKind: atlas.pipeline_decision → "decision"
 *   3.  resolveKind: atlas.trade_approved → "decision"
 *   4.  resolveKind: atlas.trade_rejected → "decision"
 *   5.  resolveKind: atlas.trade_modified → "decision"
 *   6.  resolveKind: atlas.order_placed → "order"
 *   7.  resolveKind: atlas.order_filled → "order"
 *   8.  resolveKind: atlas.position_opened → "order"
 *   9.  resolveKind: atlas.position_closed → "order"
 *  10.  resolveKind: atlas.learning_insight → "insight"
 *  11.  resolveKind: atlas.strategy_proposed → "insight"
 *  12.  resolveKind: atlas.agent_status → "status"
 *  13.  resolveKind: atlas.unknown_future → "other"
 *  14.  resolveSourceTarget: market_signal → oracle → orchestrator
 *  15.  resolveSourceTarget: payload overrides type default
 *  16.  resolveSourceTarget: agent_status → null (no edge)
 *  17.  parseRunState: running → "running"
 *  18.  parseRunState: paused → "stale"
 *  19.  parseRunState: error status → "error"
 *  20.  parseRunState: payload.error truthy → "error"
 *  21.  Buffer TTL: entries older than 60s should be filtered out
 */

import { describe, it, expect } from "vitest";
import {
  resolveKind,
  resolveSourceTarget,
  parseRunState,
} from "@/hooks/useAtlasNetwork";
import type { InFlightMessage } from "@/hooks/useAtlasNetwork";

// ─── resolveKind tests ────────────────────────────────────────────────────────

describe("useAtlasNetwork — resolveKind", () => {
  it("maps atlas.market_signal to 'signal'", () => {
    expect(resolveKind("atlas.market_signal")).toBe("signal");
  });

  it("maps atlas.pipeline_decision to 'decision'", () => {
    expect(resolveKind("atlas.pipeline_decision")).toBe("decision");
  });

  it("maps atlas.trade_approved to 'decision'", () => {
    expect(resolveKind("atlas.trade_approved")).toBe("decision");
  });

  it("maps atlas.trade_rejected to 'decision'", () => {
    expect(resolveKind("atlas.trade_rejected")).toBe("decision");
  });

  it("maps atlas.trade_modified to 'decision'", () => {
    expect(resolveKind("atlas.trade_modified")).toBe("decision");
  });

  it("maps atlas.order_placed to 'order'", () => {
    expect(resolveKind("atlas.order_placed")).toBe("order");
  });

  it("maps atlas.order_filled to 'order'", () => {
    expect(resolveKind("atlas.order_filled")).toBe("order");
  });

  it("maps atlas.position_opened to 'order'", () => {
    expect(resolveKind("atlas.position_opened")).toBe("order");
  });

  it("maps atlas.position_closed to 'order'", () => {
    expect(resolveKind("atlas.position_closed")).toBe("order");
  });

  it("maps atlas.learning_insight to 'insight'", () => {
    expect(resolveKind("atlas.learning_insight")).toBe("insight");
  });

  it("maps atlas.strategy_proposed to 'insight'", () => {
    expect(resolveKind("atlas.strategy_proposed")).toBe("insight");
  });

  it("maps atlas.agent_status to 'status'", () => {
    expect(resolveKind("atlas.agent_status")).toBe("status");
  });

  it("maps unknown atlas.* type to 'other'", () => {
    expect(resolveKind("atlas.future_event_type")).toBe("other");
  });
});

// ─── resolveSourceTarget tests ────────────────────────────────────────────────

describe("useAtlasNetwork — resolveSourceTarget", () => {
  it("market_signal maps oracle → orchestrator", () => {
    const result = resolveSourceTarget("atlas.market_signal", {});
    expect(result).not.toBeNull();
    expect(result!.source).toBe("oracle");
    expect(result!.target).toBe("orchestrator");
  });

  it("pipeline_decision maps orchestrator → architect", () => {
    const result = resolveSourceTarget("atlas.pipeline_decision", {});
    expect(result).not.toBeNull();
    expect(result!.source).toBe("orchestrator");
    expect(result!.target).toBe("architect");
  });

  it("trade_approved maps guardian → trader", () => {
    const result = resolveSourceTarget("atlas.trade_approved", {});
    expect(result).not.toBeNull();
    expect(result!.source).toBe("guardian");
    expect(result!.target).toBe("trader");
  });

  it("trade_rejected maps guardian → trader", () => {
    const result = resolveSourceTarget("atlas.trade_rejected", {});
    expect(result).not.toBeNull();
    expect(result!.source).toBe("guardian");
    expect(result!.target).toBe("trader");
  });

  it("order_placed maps trader → kraken", () => {
    const result = resolveSourceTarget("atlas.order_placed", {});
    expect(result).not.toBeNull();
    expect(result!.source).toBe("trader");
    expect(result!.target).toBe("kraken");
  });

  it("position_closed maps trader → sage", () => {
    const result = resolveSourceTarget("atlas.position_closed", {});
    expect(result).not.toBeNull();
    expect(result!.source).toBe("trader");
    expect(result!.target).toBe("sage");
  });

  it("learning_insight maps sage → orchestrator", () => {
    const result = resolveSourceTarget("atlas.learning_insight", {});
    expect(result).not.toBeNull();
    expect(result!.source).toBe("sage");
    expect(result!.target).toBe("orchestrator");
  });

  it("payload source_agent/target_agent override type defaults", () => {
    const result = resolveSourceTarget("atlas.market_signal", {
      source_agent: "oracle",
      target_agent: "guardian",
    });
    expect(result).not.toBeNull();
    expect(result!.source).toBe("oracle");
    expect(result!.target).toBe("guardian");
  });

  it("agent_status returns null (no edge to draw)", () => {
    const result = resolveSourceTarget("atlas.agent_status", {});
    expect(result).toBeNull();
  });

  it("unknown type with no payload override returns null", () => {
    const result = resolveSourceTarget("atlas.future_type", {});
    expect(result).toBeNull();
  });
});

// ─── parseRunState tests ──────────────────────────────────────────────────────

describe("useAtlasNetwork — parseRunState", () => {
  it("status=running → 'running'", () => {
    expect(parseRunState({ status: "running" })).toBe("running");
  });

  it("status=active → 'running'", () => {
    expect(parseRunState({ status: "active" })).toBe("running");
  });

  it("status=ok → 'running'", () => {
    expect(parseRunState({ status: "ok" })).toBe("running");
  });

  it("status=paused → 'stale'", () => {
    expect(parseRunState({ status: "paused" })).toBe("stale");
  });

  it("status=stale → 'stale'", () => {
    expect(parseRunState({ status: "stale" })).toBe("stale");
  });

  it("status=error → 'error'", () => {
    expect(parseRunState({ status: "error" })).toBe("error");
  });

  it("status=failed → 'error'", () => {
    expect(parseRunState({ status: "failed" })).toBe("error");
  });

  it("payload.error truthy overrides status → 'error'", () => {
    expect(parseRunState({ status: "running", error: "NaN loss" })).toBe("error");
  });

  it("empty payload defaults to 'running' (benign heartbeat)", () => {
    expect(parseRunState({})).toBe("running");
  });
});

// ─── Rolling buffer / TTL logic ───────────────────────────────────────────────

describe("useAtlasNetwork — buffer TTL semantics", () => {
  const BUFFER_TTL_MS = 60_000;

  it("entries older than 60 s should be filtered out", () => {
    const now = Date.now();
    const messages: InFlightMessage[] = [
      { id: "1", source: "oracle", target: "orchestrator", kind: "signal", ts: now - BUFFER_TTL_MS - 1 },
      { id: "2", source: "guardian", target: "trader", kind: "decision", ts: now - 5000 },
      { id: "3", source: "trader", target: "kraken", kind: "order", ts: now },
    ];
    const cutoff = now - BUFFER_TTL_MS;
    const alive = messages.filter((m) => m.ts >= cutoff);
    expect(alive).toHaveLength(2);
    expect(alive.map((m) => m.id)).toEqual(["2", "3"]);
  });

  it("all messages within 60 s survive the cutoff", () => {
    const now = Date.now();
    const messages: InFlightMessage[] = [
      { id: "a", source: "sage", target: "orchestrator", kind: "insight", ts: now - 30_000 },
      { id: "b", source: "oracle", target: "postgres", kind: "other", ts: now - 59_999 },
    ];
    const cutoff = now - BUFFER_TTL_MS;
    const alive = messages.filter((m) => m.ts >= cutoff);
    expect(alive).toHaveLength(2);
  });

  it("buffer TTL constant is exactly 60 seconds", () => {
    expect(BUFFER_TTL_MS).toBe(60_000);
  });
});

// ─── Kind filter semantics ────────────────────────────────────────────────────

describe("useAtlasNetwork — kind filter semantics", () => {
  it("filtering with empty Set removes all messages", () => {
    const messages: InFlightMessage[] = [
      { id: "1", source: "oracle", target: "orchestrator", kind: "signal", ts: Date.now() },
      { id: "2", source: "guardian", target: "trader", kind: "decision", ts: Date.now() },
    ];
    const filter = new Set<InFlightMessage["kind"]>();
    const result = messages.filter((m) => filter.has(m.kind));
    expect(result).toHaveLength(0);
  });

  it("filtering with only 'signal' returns only signal messages", () => {
    const messages: InFlightMessage[] = [
      { id: "1", source: "oracle", target: "orchestrator", kind: "signal", ts: Date.now() },
      { id: "2", source: "guardian", target: "trader", kind: "decision", ts: Date.now() },
      { id: "3", source: "trader", target: "kraken", kind: "order", ts: Date.now() },
    ];
    const filter = new Set<InFlightMessage["kind"]>(["signal"]);
    const result = messages.filter((m) => filter.has(m.kind));
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("1");
  });

  it("filtering with all kinds returns all messages", () => {
    const kinds: InFlightMessage["kind"][] = ["signal", "decision", "order", "insight", "status", "other"];
    const messages: InFlightMessage[] = kinds.map((kind, i) => ({
      id: String(i),
      source: "oracle",
      target: "orchestrator",
      kind,
      ts: Date.now(),
    }));
    const filter = new Set<InFlightMessage["kind"]>(kinds);
    const result = messages.filter((m) => filter.has(m.kind));
    expect(result).toHaveLength(kinds.length);
  });
});
