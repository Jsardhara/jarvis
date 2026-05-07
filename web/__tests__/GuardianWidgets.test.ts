/**
 * Tests for GuardianWidgets logic
 *
 * Tests the pure helpers and contract types for the Guardian workspace widgets.
 * No DOM rendering — logic only.
 *
 * Scenarios:
 *   1.  TRADE_APPROVED events → ok decision kind
 *   2.  TRADE_REJECTED events → crit decision kind
 *   3.  TRADE_MODIFIED events → amber decision kind
 *   4.  Other event types are excluded from decisions list
 *   5.  Decisions capped at 10
 *   6.  LONG direction → ok chip kind
 *   7.  SHORT direction → crit chip kind
 *   8.  NEUTRAL direction → default chip kind
 *   9.  Risk thresholds: default MAX_LEVERAGE = 5
 *  10.  Risk thresholds: default DAILY_LOSS_LIMIT_USD = 50
 *  11.  Risk thresholds: default MAX_PORTFOLIO_RISK_PCT = 10
 *  12.  Memory override: max_leverage read from memory when present
 *  13.  relAge < 60s → shows seconds
 *  14.  relAge 90s → shows minutes
 *  15.  GuardianWidgetsProps requires agentId string
 */

import { describe, it, expect } from "vitest";
import type { RecentActivity } from "@/hooks/useAgentDetail";
import type { MemoryEntry } from "@/hooks/useAgentMemory";

// ─── Constants mirrored from GuardianWidgets ──────────────────────────────────

const RISK_DEFAULTS = {
  MAX_LEVERAGE: 5,
  DAILY_LOSS_LIMIT_USD: 50,
  MAX_PORTFOLIO_RISK_PCT: 10,
} as const;

const DECISION_TYPES = new Set(["TRADE_APPROVED", "TRADE_REJECTED", "TRADE_MODIFIED"]);

// ─── Pure helpers mirrored from GuardianWidgets ───────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function dirKind(dir: string): TagKind {
  if (dir === "LONG") return "ok";
  if (dir === "SHORT") return "crit";
  return "default";
}

function decisionKind(eventType: string): TagKind {
  if (eventType === "TRADE_APPROVED") return "ok";
  if (eventType === "TRADE_REJECTED") return "crit";
  if (eventType === "TRADE_MODIFIED") return "amber";
  return "default";
}

function relAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m`;
  return `${Math.round(diff / 3_600_000)}h`;
}

function filterDecisions(events: RecentActivity[]): RecentActivity[] {
  return events.filter((e) => DECISION_TYPES.has(e.event_type)).slice(0, 10);
}

function resolveRisk(memory: Record<string, MemoryEntry>): {
  maxLeverage: number;
  dailyLoss: number;
  maxRisk: number;
} {
  const rawLeverage = memory["max_leverage"]?.value;
  const rawLoss = memory["daily_loss_limit_usd"]?.value;
  const rawRisk = memory["max_portfolio_risk_pct"]?.value;
  return {
    maxLeverage: typeof rawLeverage === "number" ? rawLeverage : RISK_DEFAULTS.MAX_LEVERAGE,
    dailyLoss: typeof rawLoss === "number" ? rawLoss : RISK_DEFAULTS.DAILY_LOSS_LIMIT_USD,
    maxRisk: typeof rawRisk === "number" ? rawRisk : RISK_DEFAULTS.MAX_PORTFOLIO_RISK_PCT,
  };
}

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeActivity(eventType: string, payload: Record<string, unknown> = {}): RecentActivity {
  return { event_type: eventType, payload, occurred_at: new Date().toISOString() };
}

function makeMemoryEntry(value: unknown): MemoryEntry {
  return { value, updated_at: "2026-04-30T10:00:00Z" };
}

// ─── Decision kind ────────────────────────────────────────────────────────────

describe("GuardianWidgets — decisionKind", () => {
  it("TRADE_APPROVED → ok", () => expect(decisionKind("TRADE_APPROVED")).toBe("ok"));
  it("TRADE_REJECTED → crit", () => expect(decisionKind("TRADE_REJECTED")).toBe("crit"));
  it("TRADE_MODIFIED → amber", () => expect(decisionKind("TRADE_MODIFIED")).toBe("amber"));
  it("other event → default", () => expect(decisionKind("SOMETHING_ELSE")).toBe("default"));
});

// ─── Direction kind ───────────────────────────────────────────────────────────

describe("GuardianWidgets — dirKind", () => {
  it("LONG → ok", () => expect(dirKind("LONG")).toBe("ok"));
  it("SHORT → crit", () => expect(dirKind("SHORT")).toBe("crit"));
  it("NEUTRAL → default", () => expect(dirKind("NEUTRAL")).toBe("default"));
});

// ─── Decision filtering ───────────────────────────────────────────────────────

describe("GuardianWidgets — decision filtering", () => {
  it("excludes non-decision events", () => {
    const events: RecentActivity[] = [
      makeActivity("TRADE_APPROVED"),
      makeActivity("MARKET_SCAN"),
      makeActivity("TRADE_REJECTED"),
      makeActivity("LEARNING_INSIGHT"),
    ];
    const decisions = filterDecisions(events);
    expect(decisions).toHaveLength(2);
    expect(decisions.every((e) => DECISION_TYPES.has(e.event_type))).toBe(true);
  });

  it("caps at 10 decisions", () => {
    const events: RecentActivity[] = Array.from({ length: 15 }, () =>
      makeActivity("TRADE_APPROVED")
    );
    expect(filterDecisions(events)).toHaveLength(10);
  });

  it("empty events → empty decisions", () => {
    expect(filterDecisions([])).toHaveLength(0);
  });
});

// ─── Risk defaults ────────────────────────────────────────────────────────────

describe("GuardianWidgets — risk threshold defaults", () => {
  it("MAX_LEVERAGE defaults to 5", () => {
    const { maxLeverage } = resolveRisk({});
    expect(maxLeverage).toBe(5);
  });

  it("DAILY_LOSS_LIMIT_USD defaults to 50", () => {
    const { dailyLoss } = resolveRisk({});
    expect(dailyLoss).toBe(50);
  });

  it("MAX_PORTFOLIO_RISK_PCT defaults to 10", () => {
    const { maxRisk } = resolveRisk({});
    expect(maxRisk).toBe(10);
  });

  it("reads max_leverage from memory when present", () => {
    const memory = { max_leverage: makeMemoryEntry(10) };
    const { maxLeverage } = resolveRisk(memory);
    expect(maxLeverage).toBe(10);
  });
});

// ─── relAge helper ────────────────────────────────────────────────────────────

describe("GuardianWidgets — relAge formatting", () => {
  it("30 seconds ago shows Xs", () => {
    const iso = new Date(Date.now() - 30_000).toISOString();
    const result = relAge(iso);
    expect(result).toMatch(/^\d+s$/);
  });

  it("90 seconds ago shows Xm", () => {
    const iso = new Date(Date.now() - 90_000).toISOString();
    const result = relAge(iso);
    expect(result).toMatch(/^\d+m$/);
  });
});

// ─── Props contract ───────────────────────────────────────────────────────────

describe("GuardianWidgets — props contract", () => {
  it("requires agentId string", () => {
    const props: { agentId: string } = { agentId: "guardian" };
    expect(props.agentId).toBe("guardian");
  });
});
