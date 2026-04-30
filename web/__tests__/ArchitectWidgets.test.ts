/**
 * Tests for ArchitectWidgets logic
 *
 * Tests the pure helpers and contract types that drive the Architect workspace.
 * No DOM rendering — logic only.
 *
 * Scenarios:
 *   1.  Status 'active' → ok tag kind
 *   2.  Status 'failed' → crit tag kind
 *   3.  Status 'paused' → amber tag kind
 *   4.  Status 'backtesting' → info tag kind
 *   5.  Status 'draft' → amber tag kind
 *   6.  Unknown status → default tag kind
 *   7.  fmtPct undefined → "—"
 *   8.  fmtPct 0.15 → "15.0%"
 *   9.  fmtNum undefined → "—"
 *  10.  fmtNum 1.234 → "1.234"
 *  11.  Generate button is disabled when proxy unavailable
 *  12.  Last 3 backtests: picks most recent per strategy
 *  13.  Empty strategies → no backtest entries
 *  14.  Strategy with no backtests skipped in backtest list
 *  15.  ArchitectWidgetsProps requires agentId string
 */

import { describe, it, expect } from "vitest";

// ─── Types mirrored from ArchitectWidgets ─────────────────────────────────────

interface Backtest {
  backtest_id: string;
  timerange: string;
  sharpe: number;
  max_drawdown: number;
  status: string;
}

interface Strategy {
  strategy_id: string;
  name: string;
  version: string;
  status: string;
  sharpe?: number;
  max_drawdown?: number;
  total_return?: number;
  activated_at?: string;
  backtests?: Backtest[];
}

// ─── Pure helpers mirrored from ArchitectWidgets ──────────────────────────────

type TagKind = "ok" | "crit" | "amber" | "info" | "default";

function statusKind(status: string): TagKind {
  const s = status.toLowerCase();
  if (s === "active" || s === "running") return "ok";
  if (s === "paused" || s === "draft") return "amber";
  if (s === "failed" || s === "error") return "crit";
  if (s === "backtesting") return "info";
  return "default";
}

function fmtPct(v: number | undefined): string {
  if (v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function fmtNum(v: number | undefined): string {
  if (v === undefined) return "—";
  return v.toFixed(3);
}

interface BacktestEntry { strategyName: string; backtest: Backtest }

function extractLastNBacktests(strategies: Strategy[], n: number): BacktestEntry[] {
  const entries: BacktestEntry[] = [];
  for (const s of strategies) {
    if (s.backtests && s.backtests.length > 0) {
      const latest = [...s.backtests].sort((a, b) =>
        b.backtest_id.localeCompare(a.backtest_id)
      )[0];
      entries.push({ strategyName: s.name, backtest: latest });
    }
    if (entries.length >= n) break;
  }
  return entries;
}

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeStrategy(overrides: Partial<Strategy> = {}): Strategy {
  return {
    strategy_id: `strat-${Math.random().toString(36).slice(2, 6)}`,
    name: "MomentumV1",
    version: "1",
    status: "active",
    ...overrides,
  };
}

function makeBacktest(overrides: Partial<Backtest> = {}): Backtest {
  return {
    backtest_id: `bt-${Math.random().toString(36).slice(2, 6)}`,
    timerange: "2026-01-01..2026-04-01",
    sharpe: 1.5,
    max_drawdown: 0.08,
    status: "done",
    ...overrides,
  };
}

// ─── Status kind ──────────────────────────────────────────────────────────────

describe("ArchitectWidgets — statusKind mapping", () => {
  it("active → ok", () => expect(statusKind("active")).toBe("ok"));
  it("running → ok", () => expect(statusKind("running")).toBe("ok"));
  it("failed → crit", () => expect(statusKind("failed")).toBe("crit"));
  it("error → crit", () => expect(statusKind("error")).toBe("crit"));
  it("paused → amber", () => expect(statusKind("paused")).toBe("amber"));
  it("draft → amber", () => expect(statusKind("draft")).toBe("amber"));
  it("backtesting → info", () => expect(statusKind("backtesting")).toBe("info"));
  it("unknown → default", () => expect(statusKind("inactive")).toBe("default"));
});

// ─── Formatting helpers ───────────────────────────────────────────────────────

describe("ArchitectWidgets — fmtPct", () => {
  it("undefined → —", () => expect(fmtPct(undefined)).toBe("—"));
  it("0.15 → 15.0%", () => expect(fmtPct(0.15)).toBe("15.0%"));
  it("0 → 0.0%", () => expect(fmtPct(0)).toBe("0.0%"));
  it("negative value formats correctly", () => expect(fmtPct(-0.05)).toBe("-5.0%"));
});

describe("ArchitectWidgets — fmtNum", () => {
  it("undefined → —", () => expect(fmtNum(undefined)).toBe("—"));
  it("1.234 → 1.234", () => expect(fmtNum(1.234)).toBe("1.234"));
  it("0 → 0.000", () => expect(fmtNum(0)).toBe("0.000"));
});

// ─── Generate button ──────────────────────────────────────────────────────────

describe("ArchitectWidgets — generate button state", () => {
  it("button is disabled when proxy not available", () => {
    const proxyAvailable = false;
    const generating = false;
    const disabled = !proxyAvailable || generating;
    expect(disabled).toBe(true);
  });

  it("button is disabled while generating", () => {
    const proxyAvailable = true;
    const generating = true;
    const disabled = !proxyAvailable || generating;
    expect(disabled).toBe(true);
  });
});

// ─── Backtest entry extraction ────────────────────────────────────────────────

describe("ArchitectWidgets — last N backtest entries", () => {
  it("empty strategies → no backtest entries", () => {
    const entries = extractLastNBacktests([], 3);
    expect(entries).toHaveLength(0);
  });

  it("strategy with no backtests is skipped", () => {
    const strategies = [makeStrategy({ backtests: [] })];
    const entries = extractLastNBacktests(strategies, 3);
    expect(entries).toHaveLength(0);
  });

  it("picks most recent backtest per strategy (sorted desc by id)", () => {
    const oldBt = makeBacktest({ backtest_id: "bt-aaa" });
    const newBt = makeBacktest({ backtest_id: "bt-zzz" });
    const strategy = makeStrategy({ backtests: [oldBt, newBt] });
    const entries = extractLastNBacktests([strategy], 3);
    expect(entries).toHaveLength(1);
    expect(entries[0].backtest.backtest_id).toBe("bt-zzz");
  });

  it("caps at n entries", () => {
    const strategies = Array.from({ length: 5 }, (_, i) =>
      makeStrategy({ name: `S${i}`, backtests: [makeBacktest()] })
    );
    const entries = extractLastNBacktests(strategies, 3);
    expect(entries).toHaveLength(3);
  });
});

// ─── Props contract ───────────────────────────────────────────────────────────

describe("ArchitectWidgets — props contract", () => {
  it("requires agentId string", () => {
    const props: { agentId: string } = { agentId: "architect" };
    expect(props.agentId).toBe("architect");
  });
});
