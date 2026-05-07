/**
 * Tests for AgentStatusRow — per-agent health indicator logic.
 *
 * We test the pure logic layers extracted from the component:
 *   - dotKind color mapping (green/amber/red/idle)
 *   - parseHealth from WS payload
 *   - parseAgentName validation
 *   - Staleness transition (ok → warn when age > threshold)
 *
 * Scenarios:
 *   1. dotKind maps health states to correct visual kinds
 *   2. parseHealth: running/active/ok → ok
 *   3. parseHealth: paused/stale/warn → warn
 *   4. parseHealth: error/failed → error
 *   5. parseHealth: error in payload.error field → error
 *   6. parseHealth: unknown status → ok (benign default for heartbeat)
 *   7. parseAgentName: known agents return correct value
 *   8. parseAgentName: unknown agent returns null
 *   9. parseAgentName: prefers agent_name over agent field
 *  10. Staleness: entry transitions ok → warn when age > STALE_THRESHOLD_MS
 *  11. Staleness: entry stays ok within threshold
 *  12. Five known agent names are the correct set
 */

import { describe, it, expect } from "vitest";

// ─── Mirror constants from AgentStatusRow ────────────────────────────────────

const ATLAS_SUB_AGENTS = ["oracle", "architect", "guardian", "trader", "sage"] as const;
type AtlasSubAgent = typeof ATLAS_SUB_AGENTS[number];
type AgentHealth = "ok" | "warn" | "error" | "unknown";
const STALE_THRESHOLD_MS = 90_000;

// ─── Mirror logic from AgentStatusRow ────────────────────────────────────────

interface AgentStatusPayload {
  agent_name?: string;
  agent?: string;
  status?: string;
  error?: string;
}

function parseAgentName(payload: AgentStatusPayload): AtlasSubAgent | null {
  const raw = (payload.agent_name ?? payload.agent ?? "").toLowerCase();
  if ((ATLAS_SUB_AGENTS as readonly string[]).includes(raw)) {
    return raw as AtlasSubAgent;
  }
  return null;
}

function parseHealth(payload: AgentStatusPayload): AgentHealth {
  const s = (payload.status ?? "").toLowerCase();
  if (payload.error) return "error";
  if (s === "running" || s === "active" || s === "ok") return "ok";
  if (s === "paused" || s === "stale" || s === "warn") return "warn";
  if (s === "error" || s === "failed") return "error";
  return "ok";
}

function dotKind(health: AgentHealth): "ok" | "warn" | "crit" | "idle" {
  switch (health) {
    case "ok": return "ok";
    case "warn": return "warn";
    case "error": return "crit";
    default: return "idle";
  }
}

function evalStaleness(
  entry: { status: AgentHealth; lastSeenMs: number | null },
  nowMs: number
): AgentHealth {
  if (entry.lastSeenMs === null || entry.status === "error") return entry.status;
  const age = nowMs - entry.lastSeenMs;
  return age > STALE_THRESHOLD_MS ? "warn" : "ok";
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AgentStatusRow — dotKind mapping", () => {
  it("ok health → ok dot (green)", () => {
    expect(dotKind("ok")).toBe("ok");
  });

  it("warn health → warn dot (amber)", () => {
    expect(dotKind("warn")).toBe("warn");
  });

  it("error health → crit dot (red)", () => {
    expect(dotKind("error")).toBe("crit");
  });

  it("unknown health → idle dot (grey)", () => {
    expect(dotKind("unknown")).toBe("idle");
  });
});

describe("AgentStatusRow — parseHealth", () => {
  it("returns ok for status=running", () => {
    expect(parseHealth({ status: "running" })).toBe("ok");
  });

  it("returns ok for status=active", () => {
    expect(parseHealth({ status: "active" })).toBe("ok");
  });

  it("returns ok for status=ok", () => {
    expect(parseHealth({ status: "ok" })).toBe("ok");
  });

  it("returns warn for status=paused", () => {
    expect(parseHealth({ status: "paused" })).toBe("warn");
  });

  it("returns warn for status=stale", () => {
    expect(parseHealth({ status: "stale" })).toBe("warn");
  });

  it("returns error for status=error", () => {
    expect(parseHealth({ status: "error" })).toBe("error");
  });

  it("returns error for status=failed", () => {
    expect(parseHealth({ status: "failed" })).toBe("error");
  });

  it("returns error when payload.error is non-empty, regardless of status", () => {
    expect(parseHealth({ status: "running", error: "NaN in weights" })).toBe("error");
  });

  it("returns ok for unknown status (benign heartbeat default)", () => {
    expect(parseHealth({ status: "some_future_status" })).toBe("ok");
  });

  it("returns ok for empty status (heartbeat with no status field)", () => {
    expect(parseHealth({})).toBe("ok");
  });
});

describe("AgentStatusRow — parseAgentName", () => {
  it("returns oracle for agent_name=oracle", () => {
    expect(parseAgentName({ agent_name: "oracle" })).toBe("oracle");
  });

  it("returns architect for agent=architect", () => {
    expect(parseAgentName({ agent: "architect" })).toBe("architect");
  });

  it("prefers agent_name over agent field", () => {
    expect(parseAgentName({ agent_name: "guardian", agent: "sage" })).toBe("guardian");
  });

  it("returns null for unknown agent name", () => {
    expect(parseAgentName({ agent: "commander" })).toBeNull();
  });

  it("returns null for empty payload", () => {
    expect(parseAgentName({})).toBeNull();
  });

  it("is case-insensitive", () => {
    expect(parseAgentName({ agent: "TRADER" })).toBe("trader");
    expect(parseAgentName({ agent_name: "Sage" })).toBe("sage");
  });
});

describe("AgentStatusRow — staleness evaluation", () => {
  it("marks entry as warn when age > 90 s", () => {
    const entry = { status: "ok" as AgentHealth, lastSeenMs: 1000 };
    const nowMs = 1000 + STALE_THRESHOLD_MS + 1; // just over threshold
    expect(evalStaleness(entry, nowMs)).toBe("warn");
  });

  it("keeps entry as ok when age <= 90 s", () => {
    const entry = { status: "ok" as AgentHealth, lastSeenMs: 1000 };
    const nowMs = 1000 + STALE_THRESHOLD_MS - 1; // just under threshold
    expect(evalStaleness(entry, nowMs)).toBe("ok");
  });

  it("leaves error entries unchanged (not re-evaluated as stale)", () => {
    const entry = { status: "error" as AgentHealth, lastSeenMs: 1000 };
    const nowMs = 1000 + STALE_THRESHOLD_MS + 5000;
    expect(evalStaleness(entry, nowMs)).toBe("error");
  });

  it("returns unknown for entries with no lastSeenMs", () => {
    const entry = { status: "unknown" as AgentHealth, lastSeenMs: null };
    expect(evalStaleness(entry, Date.now())).toBe("unknown");
  });
});

describe("AgentStatusRow — agent set", () => {
  it("contains exactly 5 sub-agents in correct pipeline order", () => {
    expect(ATLAS_SUB_AGENTS).toHaveLength(5);
    expect(ATLAS_SUB_AGENTS[0]).toBe("oracle");
    expect(ATLAS_SUB_AGENTS[1]).toBe("architect");
    expect(ATLAS_SUB_AGENTS[2]).toBe("guardian");
    expect(ATLAS_SUB_AGENTS[3]).toBe("trader");
    expect(ATLAS_SUB_AGENTS[4]).toBe("sage");
  });
});
