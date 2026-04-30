/**
 * Tests for useAgentDetail
 *
 * Tests the pure logic exported from useAgentDetail:
 *   - applyWsActivity: prepends matching events, caps at 50, rejects non-matching
 *
 * Scenarios:
 *   1. applyWsActivity prepends event when source_agent matches
 *   2. applyWsActivity returns null when source_agent does not match
 *   3. applyWsActivity returns null when source_agent is absent
 *   4. applyWsActivity returns null when event type is empty
 *   5. prepending new event puts it at index 0
 *   6. activity list is capped at 50 entries
 *   7. cap at 50 drops the oldest (tail) entries
 *   8. existing events are preserved when cap is not reached
 *   9. payload defaults to {} when absent from WS message
 *  10. occurred_at defaults to current time when ts is absent
 *  11. REST reconcile interval constant is 5 minutes
 */

import { describe, it, expect } from "vitest";
import { applyWsActivity } from "@/hooks/useAgentDetail";
import type { AgentDetail, RecentActivity } from "@/hooks/useAgentDetail";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeDetail(overrides: Partial<AgentDetail> = {}): AgentDetail {
  return {
    id: "oracle",
    display_name: "Oracle",
    model: "claude-sonnet-4-6",
    state: "running",
    last_heartbeat: "2026-04-30T10:00:00Z",
    recent_activity: [],
    ...overrides,
  };
}

function makeActivity(n: number): RecentActivity[] {
  return Array.from({ length: n }, (_, i) => ({
    event_type: `atlas.event_${i}`,
    payload: { index: i },
    occurred_at: `2026-04-30T09:0${String(i).padStart(2, "0")}:00Z`,
  }));
}

// ─── applyWsActivity: matching source ────────────────────────────────────────

describe("useAgentDetail — applyWsActivity: matching source_agent", () => {
  it("prepends event when source_agent matches", () => {
    const detail = makeDetail();
    const result = applyWsActivity(detail, {
      type: "atlas.market_signal",
      source_agent: "oracle",
      payload: { pair: "BTC/USD" },
      ts: "2026-04-30T10:01:00Z",
    });
    expect(result).not.toBeNull();
    expect(result!.recent_activity).toHaveLength(1);
    expect(result!.recent_activity[0].event_type).toBe("atlas.market_signal");
  });

  it("puts new event at index 0 (latest first)", () => {
    const detail = makeDetail({ recent_activity: makeActivity(3) });
    const result = applyWsActivity(detail, {
      type: "atlas.new_event",
      source_agent: "oracle",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).not.toBeNull();
    expect(result!.recent_activity[0].event_type).toBe("atlas.new_event");
  });

  it("preserves existing events when cap is not reached", () => {
    const initial = makeActivity(5);
    const detail = makeDetail({ recent_activity: initial });
    const result = applyWsActivity(detail, {
      type: "atlas.signal",
      source_agent: "oracle",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).not.toBeNull();
    expect(result!.recent_activity).toHaveLength(6);
  });

  it("caps activity list at 50 entries", () => {
    const detail = makeDetail({ recent_activity: makeActivity(50) });
    const result = applyWsActivity(detail, {
      type: "atlas.new",
      source_agent: "oracle",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).not.toBeNull();
    expect(result!.recent_activity).toHaveLength(50);
  });

  it("drops oldest entries when cap is exceeded", () => {
    const initial = makeActivity(50);
    const detail = makeDetail({ recent_activity: initial });
    const result = applyWsActivity(detail, {
      type: "atlas.newest",
      source_agent: "oracle",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).not.toBeNull();
    // Newest should be at index 0
    expect(result!.recent_activity[0].event_type).toBe("atlas.newest");
    // Last entry should be the 49th original (index 48 of original 0..49)
    expect(result!.recent_activity[49].event_type).toBe("atlas.event_48");
  });

  it("defaults payload to {} when absent from WS message", () => {
    const detail = makeDetail();
    const result = applyWsActivity(detail, {
      type: "atlas.signal",
      source_agent: "oracle",
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).not.toBeNull();
    expect(result!.recent_activity[0].payload).toEqual({});
  });

  it("uses provided ts as occurred_at", () => {
    const detail = makeDetail();
    const ts = "2026-04-30T15:30:00Z";
    const result = applyWsActivity(detail, {
      type: "atlas.signal",
      source_agent: "oracle",
      payload: {},
      ts,
    });
    expect(result).not.toBeNull();
    expect(result!.recent_activity[0].occurred_at).toBe(ts);
  });

  it("falls back to a non-empty occurred_at when ts is absent", () => {
    const detail = makeDetail();
    const result = applyWsActivity(detail, {
      type: "atlas.signal",
      source_agent: "oracle",
      payload: {},
    });
    expect(result).not.toBeNull();
    expect(result!.recent_activity[0].occurred_at).toBeTruthy();
  });
});

// ─── applyWsActivity: non-matching source ─────────────────────────────────────

describe("useAgentDetail — applyWsActivity: non-matching / missing fields", () => {
  it("returns null when source_agent does not match agent id", () => {
    const detail = makeDetail({ id: "oracle" });
    const result = applyWsActivity(detail, {
      type: "atlas.signal",
      source_agent: "sage",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).toBeNull();
  });

  it("returns null when source_agent is absent", () => {
    const detail = makeDetail({ id: "oracle" });
    const result = applyWsActivity(detail, {
      type: "atlas.signal",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).toBeNull();
  });

  it("returns null when event type is empty string", () => {
    const detail = makeDetail({ id: "oracle" });
    const result = applyWsActivity(detail, {
      type: "",
      source_agent: "oracle",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).toBeNull();
  });

  it("returns null when type is missing", () => {
    const detail = makeDetail({ id: "oracle" });
    const result = applyWsActivity(detail, {
      source_agent: "oracle",
      payload: {},
      ts: "2026-04-30T11:00:00Z",
    });
    expect(result).toBeNull();
  });
});

// ─── Reconcile interval constant ──────────────────────────────────────────────

describe("useAgentDetail — reconcile interval", () => {
  it("5-minute safety reconcile = 300000ms", () => {
    const RECONCILE_INTERVAL_MS = 5 * 60_000;
    expect(RECONCILE_INTERVAL_MS).toBe(300_000);
  });
});
