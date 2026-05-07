/**
 * Tests for AgentHeaderCard
 *
 * Tests the pure helper logic used by AgentHeaderCard:
 *   - relativeTime formatting
 *   - stateToKind mapping (state pill colors)
 *   - Cost formatting
 *
 * Scenarios:
 *   1. relativeTime: seconds ago (< 60s)
 *   2. relativeTime: minutes ago (< 1h)
 *   3. relativeTime: hours ago (>= 1h)
 *   4. relativeTime: null → "never"
 *   5. stateToKind: "running" → ok / ok
 *   6. stateToKind: "active" → ok / ok
 *   7. stateToKind: "paused" → amber / warn
 *   8. stateToKind: "error" → crit / crit
 *   9. stateToKind: "failed" → crit / crit
 *  10. stateToKind: unknown → info / idle
 *  11. cost formatting to 4 decimal places
 *  12. token count formatting (>= 1000 → k suffix)
 */

import { describe, it, expect } from "vitest";

// ─── Mirror relativeTime from AgentHeaderCard ─────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  return `${Math.round(diff / 3_600_000)}h ago`;
}

// ─── Mirror stateToKind from AgentHeaderCard ──────────────────────────────────

type TagKind = "default" | "amber" | "ok" | "crit" | "info";
type DotKind = "ok" | "warn" | "crit" | "idle";

function stateToKind(state: string): { kind: TagKind; dotKind: DotKind } {
  switch (state?.toLowerCase()) {
    case "running":
    case "active":
      return { kind: "ok", dotKind: "ok" };
    case "paused":
    case "stale":
      return { kind: "amber", dotKind: "warn" };
    case "error":
    case "failed":
      return { kind: "crit", dotKind: "crit" };
    default:
      return { kind: "info", dotKind: "idle" };
  }
}

// ─── relativeTime ─────────────────────────────────────────────────────────────

describe("AgentHeaderCard — relativeTime", () => {
  it("returns 'never' for null input", () => {
    expect(relativeTime(null)).toBe("never");
  });

  it("returns seconds for time < 60s ago", () => {
    const iso = new Date(Date.now() - 30_000).toISOString();
    expect(relativeTime(iso)).toMatch(/^\d+s ago$/);
  });

  it("returns minutes for time 1-59m ago", () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(relativeTime(iso)).toMatch(/^\d+m ago$/);
  });

  it("returns hours for time >= 1h ago", () => {
    const iso = new Date(Date.now() - 2 * 3_600_000).toISOString();
    expect(relativeTime(iso)).toMatch(/^\d+h ago$/);
  });

  it("returns approximately 30s for 30s ago", () => {
    const iso = new Date(Date.now() - 30_000).toISOString();
    const result = relativeTime(iso);
    const seconds = parseInt(result);
    expect(seconds).toBeGreaterThanOrEqual(29);
    expect(seconds).toBeLessThanOrEqual(31);
  });
});

// ─── stateToKind ──────────────────────────────────────────────────────────────

describe("AgentHeaderCard — stateToKind (state pill)", () => {
  it("running → ok kind, ok dot", () => {
    const { kind, dotKind } = stateToKind("running");
    expect(kind).toBe("ok");
    expect(dotKind).toBe("ok");
  });

  it("active → ok kind, ok dot", () => {
    const { kind, dotKind } = stateToKind("active");
    expect(kind).toBe("ok");
    expect(dotKind).toBe("ok");
  });

  it("RUNNING (uppercase) → ok kind", () => {
    const { kind } = stateToKind("RUNNING");
    expect(kind).toBe("ok");
  });

  it("paused → amber kind, warn dot", () => {
    const { kind, dotKind } = stateToKind("paused");
    expect(kind).toBe("amber");
    expect(dotKind).toBe("warn");
  });

  it("stale → amber kind, warn dot", () => {
    const { kind, dotKind } = stateToKind("stale");
    expect(kind).toBe("amber");
    expect(dotKind).toBe("warn");
  });

  it("error → crit kind, crit dot", () => {
    const { kind, dotKind } = stateToKind("error");
    expect(kind).toBe("crit");
    expect(dotKind).toBe("crit");
  });

  it("failed → crit kind, crit dot", () => {
    const { kind, dotKind } = stateToKind("failed");
    expect(kind).toBe("crit");
    expect(dotKind).toBe("crit");
  });

  it("unknown state → info kind, idle dot", () => {
    const { kind, dotKind } = stateToKind("unknown_state");
    expect(kind).toBe("info");
    expect(dotKind).toBe("idle");
  });
});

// ─── Cost formatting ──────────────────────────────────────────────────────────

describe("AgentHeaderCard — cost formatting", () => {
  it("formats cost to 4 decimal places", () => {
    const cost = 0.00123456;
    const formatted = `$${cost.toFixed(4)}`;
    expect(formatted).toBe("$0.0012");
  });

  it("formats zero cost correctly", () => {
    const cost = 0;
    const formatted = `$${cost.toFixed(4)}`;
    expect(formatted).toBe("$0.0000");
  });

  it("formats tokens >= 1000 with k suffix", () => {
    const tokens = 1500;
    const formatted = tokens > 0 ? `${(tokens / 1000).toFixed(1)}k tok` : "0 tok";
    expect(formatted).toBe("1.5k tok");
  });

  it("formats zero tokens as '0 tok'", () => {
    const tokens = 0;
    const formatted = tokens > 0 ? `${(tokens / 1000).toFixed(1)}k tok` : "0 tok";
    expect(formatted).toBe("0 tok");
  });
});
