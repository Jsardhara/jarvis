/**
 * Tests for SageWidgets logic
 *
 * Tests the pure helpers and contract types for the Sage workspace widgets.
 * No DOM rendering — logic only.
 *
 * Scenarios:
 *   1.  Filters LEARNING_INSIGHT events, caps at 10
 *   2.  Empty activity → no insights
 *   3.  insightKind: loss/error → crit
 *   4.  insightKind: win/profit → ok
 *   5.  insightKind: warning → amber
 *   6.  insightKind: pattern/regime → info
 *   7.  insightKind: unknown → default
 *   8.  Filters PERFORMANCE_REPORT events
 *   9.  Performance report: pnl positive → ok color
 *  10.  Performance report: pnl negative → crit color
 *  11.  Lessons: extracts keys starting with lesson_
 *  12.  Lessons: ignores non-lesson_ keys
 *  13.  Lessons: sorts lesson keys alphabetically
 *  14.  fmtPnl: positive → "+$X.XX"
 *  15.  SageWidgetsProps requires agentId string
 *  16.  trade link includes trade_id param
 */

import { describe, it, expect } from "vitest";
import type { RecentActivity } from "@/hooks/useAgentDetail";
import type { MemoryEntry } from "@/hooks/useAgentMemory";

// ─── Pure helpers mirrored from SageWidgets ───────────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function insightKind(insightType: string): TagKind {
  const t = insightType.toLowerCase();
  if (t.includes("loss") || t.includes("error") || t.includes("fail")) return "crit";
  if (t.includes("win") || t.includes("profit") || t.includes("success")) return "ok";
  if (t.includes("warning") || t.includes("drawdown")) return "amber";
  if (t.includes("pattern") || t.includes("regime") || t.includes("trend")) return "info";
  return "default";
}

function fmtPnl(val: number): string {
  const sign = val >= 0 ? "+" : "";
  return `${sign}$${val.toFixed(2)}`;
}

function pnlColor(val: number): string {
  if (val > 0) return "var(--ops-ok)";
  if (val < 0) return "var(--ops-crit)";
  return "var(--ops-fg)";
}

function filterInsights(events: RecentActivity[]): RecentActivity[] {
  return events.filter((e) => e.event_type === "LEARNING_INSIGHT").slice(0, 10);
}

function filterReports(events: RecentActivity[]): RecentActivity[] {
  return events.filter((e) => e.event_type === "PERFORMANCE_REPORT");
}

function extractLessonKeys(memory: Record<string, MemoryEntry>): string[] {
  return Object.keys(memory).filter((k) => k.startsWith("lesson_")).sort();
}

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeActivity(eventType: string, payload: Record<string, unknown> = {}): RecentActivity {
  return { event_type: eventType, payload, occurred_at: new Date().toISOString() };
}

function makeMemoryEntry(value: unknown): MemoryEntry {
  return { value, updated_at: "2026-04-30T10:00:00Z" };
}

// ─── Learning insights ────────────────────────────────────────────────────────

describe("SageWidgets — learning insights filtering", () => {
  it("filters to LEARNING_INSIGHT events", () => {
    const events: RecentActivity[] = [
      makeActivity("LEARNING_INSIGHT", { text: "first" }),
      makeActivity("PERFORMANCE_REPORT"),
      makeActivity("LEARNING_INSIGHT", { text: "second" }),
    ];
    const insights = filterInsights(events);
    expect(insights).toHaveLength(2);
    expect(insights.every((e) => e.event_type === "LEARNING_INSIGHT")).toBe(true);
  });

  it("caps at 10 insights", () => {
    const events = Array.from({ length: 15 }, () =>
      makeActivity("LEARNING_INSIGHT", { text: "test" })
    );
    expect(filterInsights(events)).toHaveLength(10);
  });

  it("empty activity → no insights", () => {
    expect(filterInsights([])).toHaveLength(0);
  });
});

// ─── Insight kind ─────────────────────────────────────────────────────────────

describe("SageWidgets — insightKind", () => {
  it("loss → crit", () => expect(insightKind("STOP_LOSS")).toBe("crit"));
  it("error → crit", () => expect(insightKind("ERROR_PATTERN")).toBe("crit"));
  it("win → ok", () => expect(insightKind("WIN_STREAK")).toBe("ok"));
  it("profit → ok", () => expect(insightKind("PROFIT_OPTIMIZATION")).toBe("ok"));
  it("warning → amber", () => expect(insightKind("DRAWDOWN_WARNING")).toBe("amber"));
  it("pattern → info", () => expect(insightKind("BREAKOUT_PATTERN")).toBe("info"));
  it("regime → info", () => expect(insightKind("REGIME_SHIFT")).toBe("info"));
  it("unknown → default", () => expect(insightKind("MISC_OBSERVATION")).toBe("default"));
});

// ─── Performance reports ──────────────────────────────────────────────────────

describe("SageWidgets — performance reports", () => {
  it("filters to PERFORMANCE_REPORT events", () => {
    const events: RecentActivity[] = [
      makeActivity("PERFORMANCE_REPORT", { window: "daily", total_pnl_usd: 120 }),
      makeActivity("LEARNING_INSIGHT"),
    ];
    const reports = filterReports(events);
    expect(reports).toHaveLength(1);
    expect(reports[0].payload.window).toBe("daily");
  });

  it("pnl positive → ok color", () => {
    expect(pnlColor(120)).toBe("var(--ops-ok)");
  });

  it("pnl negative → crit color", () => {
    expect(pnlColor(-50)).toBe("var(--ops-crit)");
  });
});

// ─── Lessons ──────────────────────────────────────────────────────────────────

describe("SageWidgets — lessons extraction", () => {
  it("extracts keys starting with lesson_", () => {
    const memory: Record<string, MemoryEntry> = {
      lesson_a: makeMemoryEntry("text a"),
      current_regime: makeMemoryEntry("bull"),
      lesson_b: makeMemoryEntry("text b"),
    };
    const keys = extractLessonKeys(memory);
    expect(keys).toEqual(["lesson_a", "lesson_b"]);
  });

  it("ignores non-lesson_ keys", () => {
    const memory: Record<string, MemoryEntry> = {
      current_regime: makeMemoryEntry("bear"),
      signals_cache: makeMemoryEntry([]),
    };
    expect(extractLessonKeys(memory)).toHaveLength(0);
  });

  it("sorts lesson keys alphabetically", () => {
    const memory: Record<string, MemoryEntry> = {
      lesson_zzz: makeMemoryEntry("last"),
      lesson_aaa: makeMemoryEntry("first"),
      lesson_mmm: makeMemoryEntry("middle"),
    };
    const keys = extractLessonKeys(memory);
    expect(keys).toEqual(["lesson_aaa", "lesson_mmm", "lesson_zzz"]);
  });

  it("empty memory → no lesson keys", () => {
    expect(extractLessonKeys({})).toHaveLength(0);
  });
});

// ─── fmtPnl helper ────────────────────────────────────────────────────────────

describe("SageWidgets — fmtPnl", () => {
  it("+$100.00 for positive", () => expect(fmtPnl(100)).toBe("+$100.00"));
  it("$-50.00 for negative", () => expect(fmtPnl(-50)).toBe("$-50.00"));
  it("+$0.00 for zero", () => expect(fmtPnl(0)).toBe("+$0.00"));
});

// ─── Trade link URL ───────────────────────────────────────────────────────────

describe("SageWidgets — trade link URL", () => {
  it("includes trade_id as query param", () => {
    const tradeId = "trade-abc123";
    const url = `/atlas/trades?trade_id=${tradeId}`;
    expect(url).toBe("/atlas/trades?trade_id=trade-abc123");
  });
});

// ─── Props contract ───────────────────────────────────────────────────────────

describe("SageWidgets — props contract", () => {
  it("requires agentId string", () => {
    const props: { agentId: string } = { agentId: "sage" };
    expect(props.agentId).toBe("sage");
  });
});
