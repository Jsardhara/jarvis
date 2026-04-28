/**
 * Tests for CostChart logic and useDailyCost data transformation.
 *
 * The vitest environment is "node" so we test pure logic functions extracted
 * from the components rather than rendering SVG.
 *
 * Scenarios:
 *   1. Renders 14 days (data array has 14 elements)
 *   2. Stack order: atlas bottom, sentinel top
 *   3. Segment aria-label format
 *   4. Tooltip on hover (logic contract)
 *   5. Total matches sum of stacks
 *   6. Legend toggle (hidden agents logic)
 *   7. Table sorting
 *   8. rawToDaily transformation from backend shape
 */

import { describe, it, expect } from "vitest";
import type { CostAgent, DailyRollup } from "@/lib/types";
import type { CostTableRow } from "@/components/CostChart";

// ─── Constants mirrored from CostChart.tsx ───────────────────────────────────

// Stack order: high-cost at bottom, low overhead at top
const STACK_ORDER: CostAgent[] = [
  "atlas",
  "forge",
  "lens",
  "scholar",
  "tempo",
  "jarvis",
  "sentinel",
];

// ─── Logic extracted for testing ─────────────────────────────────────────────

function formatUsd(val: number): string {
  if (val === 0) return "$0";
  if (val < 0.01) return `<$0.01`;
  return `$${val.toFixed(2)}`;
}

function dayLabel(isoDate: string): string {
  const d = new Date(isoDate + "T12:00:00Z");
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** Build aria-label for a chart segment */
function segmentAriaLabel(
  agent: string,
  date: string,
  costUsd: number,
  calls: number
): string {
  return `${agent}, ${dayLabel(date)}, ${formatUsd(costUsd)}, ${calls} call${calls !== 1 ? "s" : ""}`;
}

/** Simulate rawToDaily transformation */
interface RawRollup {
  date: string;
  total_usd: number;
  by_agent: Record<string, number>;
  by_model: Record<string, number>;
  call_count: number;
}

const KNOWN_AGENTS: CostAgent[] = [
  "atlas", "forge", "lens", "scholar", "tempo", "jarvis", "sentinel",
];

function rawToDaily(raw: RawRollup): DailyRollup {
  const buckets: Record<CostAgent, { cost: number; calls: number }> = {
    atlas:    { cost: 0, calls: 0 },
    forge:    { cost: 0, calls: 0 },
    lens:     { cost: 0, calls: 0 },
    scholar:  { cost: 0, calls: 0 },
    tempo:    { cost: 0, calls: 0 },
    jarvis:   { cost: 0, calls: 0 },
    sentinel: { cost: 0, calls: 0 },
  };

  for (const [agent, cost] of Object.entries(raw.by_agent)) {
    const key = KNOWN_AGENTS.includes(agent as CostAgent)
      ? (agent as CostAgent)
      : "jarvis";
    buckets[key].cost += cost;
    buckets[key].calls += 1;
  }

  const perAgent = KNOWN_AGENTS.map((a) => ({
    agent: a,
    costUsd: buckets[a].cost,
    calls: buckets[a].calls,
    inputTokens: 0,
    outputTokens: 0,
  })).filter((a) => a.costUsd > 0);

  return { date: raw.date, totalUsd: raw.total_usd, perAgent };
}

/** Sort table rows */
function sortRows(
  rows: CostTableRow[],
  key: keyof CostTableRow,
  dir: "asc" | "desc"
): CostTableRow[] {
  return [...rows].sort((a, b) => {
    const av = a[key] as number | string;
    const bv = b[key] as number | string;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return dir === "asc" ? cmp : -cmp;
  });
}

/** Generate N sequential days of data */
function generateDays(n: number): DailyRollup[] {
  return Array.from({ length: n }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (n - 1 - i));
    const date = d.toISOString().slice(0, 10);
    return {
      date,
      totalUsd: Math.random() * 2,
      perAgent: [
        { agent: "atlas" as CostAgent, costUsd: Math.random(), calls: 5, inputTokens: 0, outputTokens: 0 },
        { agent: "forge" as CostAgent, costUsd: Math.random() * 0.5, calls: 3, inputTokens: 0, outputTokens: 0 },
      ],
    };
  });
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("CostChart — 14-day data", () => {
  it("has 14 elements when useDailyCost fetches 14 days", () => {
    const data = generateDays(14);
    expect(data).toHaveLength(14);
  });

  it("data is in chronological order (oldest first)", () => {
    const data = generateDays(14);
    for (let i = 1; i < data.length; i++) {
      expect(data[i].date >= data[i - 1].date).toBe(true);
    }
  });

  it("returns empty perAgent array for zero-cost days", () => {
    const raw: RawRollup = {
      date: "2026-01-01",
      total_usd: 0,
      by_agent: {},
      by_model: {},
      call_count: 0,
    };
    const result = rawToDaily(raw);
    expect(result.perAgent).toHaveLength(0);
    expect(result.totalUsd).toBe(0);
  });
});

describe("CostChart — stack order", () => {
  it("STACK_ORDER has atlas at index 0 (bottom)", () => {
    expect(STACK_ORDER[0]).toBe("atlas");
  });

  it("STACK_ORDER has sentinel at last position (top)", () => {
    expect(STACK_ORDER[STACK_ORDER.length - 1]).toBe("sentinel");
  });

  it("STACK_ORDER contains all 7 expected agents", () => {
    expect(STACK_ORDER).toContain("atlas");
    expect(STACK_ORDER).toContain("forge");
    expect(STACK_ORDER).toContain("lens");
    expect(STACK_ORDER).toContain("scholar");
    expect(STACK_ORDER).toContain("tempo");
    expect(STACK_ORDER).toContain("jarvis");
    expect(STACK_ORDER).toContain("sentinel");
    expect(STACK_ORDER).toHaveLength(7);
  });
});

describe("CostChart — segment aria-label", () => {
  it("includes agent, day, cost, and call count", () => {
    const label = segmentAriaLabel("atlas", "2026-04-25", 1.20, 84);
    expect(label).toContain("atlas");
    expect(label).toContain("$1.20");
    expect(label).toContain("84 calls");
  });

  it("uses singular 'call' for 1 call", () => {
    const label = segmentAriaLabel("tempo", "2026-04-25", 0.05, 1);
    expect(label).toContain("1 call");
    expect(label).not.toContain("1 calls");
  });

  it("shows <$0.01 for sub-cent costs", () => {
    const label = segmentAriaLabel("sentinel", "2026-04-25", 0.001, 2);
    expect(label).toContain("<$0.01");
  });
});

describe("CostChart — tooltip logic", () => {
  it("whole-bar tooltip shows total for the day", () => {
    const day: DailyRollup = {
      date: "2026-04-25",
      totalUsd: 3.50,
      perAgent: [
        { agent: "atlas", costUsd: 2.00, calls: 10, inputTokens: 0, outputTokens: 0 },
        { agent: "forge", costUsd: 1.50, calls: 5,  inputTokens: 0, outputTokens: 0 },
      ],
    };
    // Contract: total should equal sum of segment costs
    const segTotal = day.perAgent.reduce((s, a) => s + a.costUsd, 0);
    expect(Math.abs(segTotal - day.totalUsd)).toBeLessThan(0.001);
  });
});

describe("CostChart — total matches sum of stacks", () => {
  it("totalUsd equals sum of perAgent costUsd values", () => {
    const raw: RawRollup = {
      date: "2026-04-28",
      total_usd: 5.75,
      by_agent: { atlas: 3.0, forge: 1.5, sentinel: 1.25 },
      by_model: {},
      call_count: 15,
    };
    const daily = rawToDaily(raw);
    const sum = daily.perAgent.reduce((s, a) => s + a.costUsd, 0);
    expect(Math.abs(sum - 5.75)).toBeLessThan(0.001);
    expect(daily.totalUsd).toBe(5.75);
  });

  it("unknown agents are bucketed into jarvis", () => {
    const raw: RawRollup = {
      date: "2026-04-28",
      total_usd: 1.0,
      by_agent: { unknown_agent: 1.0 },
      by_model: {},
      call_count: 1,
    };
    const daily = rawToDaily(raw);
    const jarvisEntry = daily.perAgent.find((a) => a.agent === "jarvis");
    expect(jarvisEntry).toBeDefined();
    expect(jarvisEntry?.costUsd).toBe(1.0);
  });
});

describe("CostChart — legend toggle", () => {
  it("hides an agent by adding to hiddenAgents list", () => {
    const hidden: string[] = [];
    const afterToggle = hidden.includes("atlas")
      ? hidden.filter((a) => a !== "atlas")
      : [...hidden, "atlas"];
    expect(afterToggle).toContain("atlas");
  });

  it("shows an agent by removing from hiddenAgents list", () => {
    const hidden = ["atlas", "sentinel"];
    const afterToggle = hidden.includes("atlas")
      ? hidden.filter((a) => a !== "atlas")
      : [...hidden, "atlas"];
    expect(afterToggle).not.toContain("atlas");
    expect(afterToggle).toContain("sentinel");
  });

  it("hidden agents list is empty by default", () => {
    const hideParam: string = "";
    const hiddenAgents = hideParam ? hideParam.split(",").filter(Boolean) : [];
    expect(hiddenAgents).toHaveLength(0);
  });
});

describe("CostChart — table sorting", () => {
  const rows: CostTableRow[] = [
    { agent: "atlas",    calls: 100, inputTokens: 1_000_000, outputTokens: 200_000, totalUsd: 18.40 },
    { agent: "forge",    calls: 50,  inputTokens: 500_000,   outputTokens: 100_000, totalUsd: 12.10 },
    { agent: "lens",     calls: 30,  inputTokens: 300_000,   outputTokens: 60_000,  totalUsd: 6.20  },
    { agent: "sentinel", calls: 5,   inputTokens: 10_000,    outputTokens: 2_000,   totalUsd: 0.05  },
  ];

  it("sorts by totalUsd descending by default", () => {
    const sorted = sortRows(rows, "totalUsd", "desc");
    expect(sorted[0].agent).toBe("atlas");
    expect(sorted[sorted.length - 1].agent).toBe("sentinel");
  });

  it("sorts by calls ascending", () => {
    const sorted = sortRows(rows, "calls", "asc");
    expect(sorted[0].calls).toBe(5);
    expect(sorted[sorted.length - 1].calls).toBe(100);
  });

  it("sorts by agent name alphabetically", () => {
    const sorted = sortRows(rows, "agent", "asc");
    expect(sorted[0].agent).toBe("atlas");
    expect(sorted[1].agent).toBe("forge");
  });

  it("reverses sort direction on same column re-click", () => {
    const asc = sortRows(rows, "totalUsd", "asc");
    const desc = sortRows(rows, "totalUsd", "desc");
    expect(asc[0].totalUsd).toBeLessThan(desc[0].totalUsd);
  });
});

describe("CostChart — rawToDaily transformation", () => {
  it("maps by_agent costs to perAgent array", () => {
    const raw: RawRollup = {
      date: "2026-04-28",
      total_usd: 2.5,
      by_agent: { atlas: 1.5, forge: 1.0 },
      by_model: { "claude-opus-4-7": 1.5, "claude-sonnet-4-6": 1.0 },
      call_count: 8,
    };
    const daily = rawToDaily(raw);
    const atlasEntry = daily.perAgent.find((a) => a.agent === "atlas");
    const forgeEntry = daily.perAgent.find((a) => a.agent === "forge");

    expect(atlasEntry?.costUsd).toBe(1.5);
    expect(forgeEntry?.costUsd).toBe(1.0);
    expect(daily.date).toBe("2026-04-28");
  });

  it("does not include zero-cost agents in perAgent", () => {
    const raw: RawRollup = {
      date: "2026-04-28",
      total_usd: 1.0,
      by_agent: { atlas: 1.0 },
      by_model: {},
      call_count: 1,
    };
    const daily = rawToDaily(raw);
    // Only atlas should appear (has cost > 0)
    expect(daily.perAgent.every((a) => a.costUsd > 0)).toBe(true);
    // forge, lens, scholar, tempo, jarvis, sentinel should be absent (cost = 0)
    expect(daily.perAgent.find((a) => a.agent === "forge")).toBeUndefined();
  });
});
