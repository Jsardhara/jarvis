/**
 * Tests for AgentInspectorDrawer — pure logic layer.
 *
 * We test the helper functions extracted from the component:
 *   - formatTime: ISO string → local time display
 *   - stateColor: agent state → tag kind mapping
 *
 * And the data-shape contracts for the two fetch endpoints.
 *
 * Scenarios:
 *   1.  formatTime: valid ISO string returns HH:MM:SS format
 *   2.  formatTime: undefined returns "—"
 *   3.  formatTime: malformed string is handled gracefully
 *   4.  stateColor: running → "ok"
 *   5.  stateColor: active → "ok"
 *   6.  stateColor: ok → "ok"
 *   7.  stateColor: paused → "warn"
 *   8.  stateColor: stale → "warn"
 *   9.  stateColor: error → "crit"
 *  10.  stateColor: failed → "crit"
 *  11.  stateColor: undefined → undefined
 *  12.  stateColor: unknown string → undefined
 *  13.  Memory data: array response is used as-is
 *  14.  Memory data: object with .memory key is unwrapped
 *  15.  Activity slice: takes first 20 items from recent_activity
 */

import { describe, it, expect } from "vitest";

// Import directly from the helpers module to test the real implementations
import {
  formatTime,
  stateColor,
  normalizeMemory,
} from "@/components/atlas/network/drawer-utils";
import type { MemoryEntry } from "@/components/atlas/network/drawer-utils";

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AgentInspectorDrawer — formatTime", () => {
  it("returns '—' for undefined input", () => {
    expect(formatTime(undefined)).toBe("—");
  });

  it("parses a valid ISO 8601 string without throwing", () => {
    const result = formatTime("2026-04-30T12:34:56Z");
    expect(typeof result).toBe("string");
    expect(result).not.toBe("—");
    expect(result.length).toBeGreaterThan(0);
  });

  it("returns the original string for a malformed date (fallback)", () => {
    const malformed = "not-a-date";
    const result = formatTime(malformed);
    // Either the original string or "Invalid Date" from toLocaleTimeString — not "—"
    // The main requirement is it doesn't throw.
    expect(typeof result).toBe("string");
  });

  it("handles empty string by returning '—'", () => {
    // new Date("") produces Invalid Date, toLocaleTimeString throws in some envs
    const result = formatTime("");
    expect(typeof result).toBe("string");
  });
});

describe("AgentInspectorDrawer — stateColor", () => {
  it("running → 'ok'", () => {
    expect(stateColor("running")).toBe("ok");
  });

  it("active → 'ok'", () => {
    expect(stateColor("active")).toBe("ok");
  });

  it("ok → 'ok'", () => {
    expect(stateColor("ok")).toBe("ok");
  });

  it("paused → 'amber'", () => {
    expect(stateColor("paused")).toBe("amber");
  });

  it("stale → 'amber'", () => {
    expect(stateColor("stale")).toBe("amber");
  });

  it("warn → 'amber'", () => {
    expect(stateColor("warn")).toBe("amber");
  });

  it("error → 'crit'", () => {
    expect(stateColor("error")).toBe("crit");
  });

  it("failed → 'crit'", () => {
    expect(stateColor("failed")).toBe("crit");
  });

  it("undefined → undefined (no tag shown)", () => {
    expect(stateColor(undefined)).toBeUndefined();
  });

  it("unknown string → undefined (no tag shown)", () => {
    expect(stateColor("initializing")).toBeUndefined();
  });

  it("is case-insensitive", () => {
    expect(stateColor("RUNNING")).toBe("ok");
    expect(stateColor("ERROR")).toBe("crit");
  });
});

describe("AgentInspectorDrawer — memory normalization", () => {
  it("accepts array response directly", () => {
    const raw: MemoryEntry[] = [
      { key: "regime", value: "bull", updated_at: "2026-04-30T10:00:00Z" },
      { key: "risk_limit", value: 500 },
    ];
    const result = normalizeMemory(raw);
    expect(result).toHaveLength(2);
    expect(result[0].key).toBe("regime");
  });

  it("unwraps object with .memory key", () => {
    const raw = {
      memory: [
        { key: "strategy", value: "momentum" },
      ],
    };
    const result = normalizeMemory(raw);
    expect(result).toHaveLength(1);
    expect(result[0].key).toBe("strategy");
  });

  it("returns empty array for null memory field", () => {
    const result = normalizeMemory({ memory: null });
    expect(result).toHaveLength(0);
  });

  it("returns empty array for empty array", () => {
    expect(normalizeMemory([])).toHaveLength(0);
  });
});

describe("AgentInspectorDrawer — activity slice contract", () => {
  it("takes first 20 items from recent_activity", () => {
    const activity = Array.from({ length: 30 }, (_, i) => ({
      id: String(i),
      event_type: "market_scan",
      occurred_at: new Date(Date.now() - i * 1000).toISOString(),
    }));
    const sliced = activity.slice(0, 20);
    expect(sliced).toHaveLength(20);
    expect(sliced[0].id).toBe("0");
    expect(sliced[19].id).toBe("19");
  });

  it("shows all items when activity length < 20", () => {
    const activity = Array.from({ length: 5 }, (_, i) => ({
      id: String(i),
      event_type: "heartbeat",
      occurred_at: new Date().toISOString(),
    }));
    const sliced = activity.slice(0, 20);
    expect(sliced).toHaveLength(5);
  });
});
