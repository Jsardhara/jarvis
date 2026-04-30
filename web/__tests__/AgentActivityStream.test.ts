/**
 * Tests for AgentActivityStream
 *
 * Tests the pure helper logic used by AgentActivityStream:
 *   - eventKind: maps event_type to Tag color kind
 *   - relTime: relative time formatting
 *   - payload preview: truncation at 100 chars
 *
 * Scenarios:
 *   1. eventKind: signal → amber
 *   2. eventKind: market signal → amber
 *   3. eventKind: decision → info
 *   4. eventKind: strategy → info
 *   5. eventKind: insight/learning → info
 *   6. eventKind: order → ok
 *   7. eventKind: trade/position → ok
 *   8. eventKind: error/fail/reject → crit
 *   9. eventKind: unknown type → default
 *  10. relTime: seconds
 *  11. relTime: minutes
 *  12. relTime: hours
 *  13. preview truncates at 100 chars with ellipsis
 *  14. preview does not truncate short payloads
 */

import { describe, it, expect } from "vitest";

// ─── Mirror eventKind from AgentActivityStream ────────────────────────────────

type TagKind = "default" | "amber" | "ok" | "crit" | "info";

function eventKind(eventType: string): TagKind {
  const t = eventType.toLowerCase();
  // Error/reject checked first — "trade_rejected" must not fall into the "trade" bucket
  if (t.includes("error") || t.includes("reject") || t.includes("fail")) return "crit";
  if (t.includes("signal") || t.includes("market")) return "amber";
  if (t.includes("decision") || t.includes("strategy") || t.includes("insight") || t.includes("learning")) return "info";
  if (t.includes("order") || t.includes("trade") || t.includes("fill") || t.includes("position")) return "ok";
  return "default";
}

// ─── Mirror relTime from AgentActivityStream ──────────────────────────────────

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m`;
  return `${Math.round(diff / 3_600_000)}h`;
}

// ─── Payload preview ──────────────────────────────────────────────────────────

function makePreview(payload: unknown): string {
  try {
    const raw = JSON.stringify(payload);
    return raw.length > 100 ? raw.slice(0, 100) + "…" : raw;
  } catch {
    return String(payload);
  }
}

// ─── eventKind ────────────────────────────────────────────────────────────────

describe("AgentActivityStream — eventKind color mapping", () => {
  it("atlas.market_signal → amber", () => {
    expect(eventKind("atlas.market_signal")).toBe("amber");
  });

  it("atlas.signal → amber", () => {
    expect(eventKind("atlas.signal")).toBe("amber");
  });

  it("atlas.pipeline_decision → info", () => {
    expect(eventKind("atlas.pipeline_decision")).toBe("info");
  });

  it("atlas.strategy_proposed → info", () => {
    expect(eventKind("atlas.strategy_proposed")).toBe("info");
  });

  it("atlas.learning_insight → info", () => {
    expect(eventKind("atlas.learning_insight")).toBe("info");
  });

  it("atlas.order_placed → ok", () => {
    expect(eventKind("atlas.order_placed")).toBe("ok");
  });

  it("atlas.position_opened → ok", () => {
    expect(eventKind("atlas.position_opened")).toBe("ok");
  });

  it("atlas.order_filled → ok", () => {
    expect(eventKind("atlas.order_filled")).toBe("ok");
  });

  it("atlas.trade_rejected → crit", () => {
    expect(eventKind("atlas.trade_rejected")).toBe("crit");
  });

  it("atlas.agent_error → crit", () => {
    expect(eventKind("atlas.agent_error")).toBe("crit");
  });

  it("unknown event type → default", () => {
    expect(eventKind("atlas.heartbeat")).toBe("default");
  });

  it("atlas.agent_status → default (not mapped)", () => {
    expect(eventKind("atlas.agent_status")).toBe("default");
  });
});

// ─── relTime ──────────────────────────────────────────────────────────────────

describe("AgentActivityStream — relTime formatting", () => {
  it("returns seconds for time < 60s ago", () => {
    const iso = new Date(Date.now() - 20_000).toISOString();
    const result = relTime(iso);
    expect(result).toMatch(/^\d+s$/);
  });

  it("returns minutes for time 1-59m ago", () => {
    const iso = new Date(Date.now() - 10 * 60_000).toISOString();
    const result = relTime(iso);
    expect(result).toMatch(/^\d+m$/);
  });

  it("returns hours for time >= 1h ago", () => {
    const iso = new Date(Date.now() - 3 * 3_600_000).toISOString();
    const result = relTime(iso);
    expect(result).toMatch(/^\d+h$/);
  });
});

// ─── Payload preview ──────────────────────────────────────────────────────────

describe("AgentActivityStream — payload preview", () => {
  it("does not truncate short payloads", () => {
    const preview = makePreview({ pair: "BTC/USD" });
    expect(preview).toBe('{"pair":"BTC/USD"}');
    expect(preview).not.toContain("…");
  });

  it("truncates payload at 100 chars and appends ellipsis", () => {
    const long = { data: "x".repeat(200) };
    const preview = makePreview(long);
    expect(preview.endsWith("…")).toBe(true);
    // The non-ellipsis portion is 100 chars
    expect(preview.slice(0, 100)).toHaveLength(100);
  });

  it("handles empty payload gracefully", () => {
    const preview = makePreview({});
    expect(preview).toBe("{}");
  });
});
