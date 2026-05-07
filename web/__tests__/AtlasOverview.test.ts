/**
 * Tests for /atlas Overview page logic.
 *
 * We test pure formatting and logic extracted from the page:
 *   - KPI equity formatting from portfolio snapshot
 *   - Today P&L sign rendering (positive / negative / zero)
 *   - Win rate percentage formatting
 *   - Open trades count string conversion
 *   - Sentinel schedule entry sorting
 *   - deriveTarget heuristic for job name → agent
 *
 * Scenarios:
 *  1.  Equity from snapshot.portfolio.equity
 *  2.  Equity from snapshot.portfolio.portfolio_value fallback
 *  3.  Equity shows "—" when missing
 *  4.  P&L shows "+" prefix when positive
 *  5.  P&L shows no prefix when zero
 *  6.  P&L shows "-" prefix when negative
 *  7.  Win rate shows "—" when total_trades === 0
 *  8.  Win rate shows percentage when trades exist
 *  9.  Open trades count converted to string
 * 10.  Schedule entries sorted by nextIso ascending
 * 11.  Schedule entries filtered to enabled only
 * 12.  deriveTarget: inbox → tempo
 * 13.  deriveTarget: study → scholar
 * 14.  deriveTarget: atlas → atlas
 * 15.  deriveTarget: unknown → null
 */

import { describe, it, expect } from "vitest";
import type { TradeStats } from "@/hooks/useTradeBlotter";

// ─── Mirror KPI formatting from /atlas/page.tsx ───────────────────────────────

function formatEquity(portfolio: Record<string, unknown> | null | undefined): string {
  if (typeof portfolio?.equity === "number") {
    return `$${(portfolio.equity as number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (typeof portfolio?.portfolio_value === "number") {
    return `$${(portfolio.portfolio_value as number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return "—";
}

function formatPnl(stats: TradeStats): string {
  const abs = Math.abs(stats.today_pnl_usd).toFixed(2);
  if (stats.today_pnl_usd > 0) return `+$${abs}`;
  if (stats.today_pnl_usd < 0) return `-$${abs}`;
  return "$0.00";
}

function formatWinRate(stats: TradeStats): string {
  if (stats.total_trades > 0) {
    return `${(stats.win_rate * 100).toFixed(0)}%`;
  }
  return "—";
}

function formatOpenTrades(count: number): string {
  return String(count);
}

// ─── Mirror deriveTarget from /atlas/page.tsx ────────────────────────────────

function deriveTarget(name: string): string | null {
  const n = name.toLowerCase();
  if (n.includes("inbox") || n.includes("mail") || n.includes("tempo") || n.includes("calendar")) return "tempo";
  if (n.includes("scholar") || n.includes("study") || n.includes("academic")) return "scholar";
  if (n.includes("lens") || n.includes("research") || n.includes("monitor")) return "lens";
  if (n.includes("forge") || n.includes("build") || n.includes("deploy")) return "forge";
  if (n.includes("atlas") || n.includes("trade") || n.includes("portfolio")) return "atlas";
  if (n.includes("sentinel") || n.includes("daemon")) return "sentinel";
  return null;
}

// ─── Mirror schedule entry sorting ───────────────────────────────────────────

interface ScheduleJob {
  enabled: boolean;
  cron?: string;
  command?: string;
}

interface ScheduleEntry {
  name: string;
  nextIso: string;
}

function buildScheduleEntries(
  schedule: Record<string, ScheduleJob>,
  nextScheduledRuns: Record<string, string>
): ScheduleEntry[] {
  return Object.entries(schedule)
    .filter(([, job]) => job.enabled)
    .map(([name]) => ({ name, nextIso: nextScheduledRuns[name] ?? "" }))
    .filter((e) => e.nextIso !== "")
    .sort((a, b) => a.nextIso.localeCompare(b.nextIso))
    .slice(0, 6);
}

// ─── KPI formatting tests ─────────────────────────────────────────────────────

describe("AtlasOverview — equity formatting", () => {
  it("formats equity from portfolio.equity", () => {
    const result = formatEquity({ equity: 10000.5 });
    expect(result).toBe("$10,000.50");
  });

  it("falls back to portfolio_value when equity is missing", () => {
    const result = formatEquity({ portfolio_value: 9500 });
    expect(result).toBe("$9,500.00");
  });

  it("returns '—' when portfolio is null", () => {
    expect(formatEquity(null)).toBe("—");
  });

  it("returns '—' when portfolio is undefined", () => {
    expect(formatEquity(undefined)).toBe("—");
  });

  it("returns '—' when portfolio has no numeric equity or portfolio_value", () => {
    expect(formatEquity({ equity: "unknown" })).toBe("—");
  });
});

describe("AtlasOverview — P&L formatting", () => {
  const base: TradeStats = { open_count: 0, today_pnl_usd: 0, win_rate: 0, total_trades: 0, best_trade_usd: 0 };

  it("shows positive P&L with + prefix", () => {
    expect(formatPnl({ ...base, today_pnl_usd: 125.50 })).toBe("+$125.50");
  });

  it("shows zero P&L as $0.00 (no prefix)", () => {
    expect(formatPnl({ ...base, today_pnl_usd: 0 })).toBe("$0.00");
  });

  it("shows negative P&L with - prefix", () => {
    expect(formatPnl({ ...base, today_pnl_usd: -42.75 })).toBe("-$42.75");
  });
});

describe("AtlasOverview — win rate formatting", () => {
  const base: TradeStats = { open_count: 0, today_pnl_usd: 0, win_rate: 0, total_trades: 0, best_trade_usd: 0 };

  it("returns '—' when no trades", () => {
    expect(formatWinRate({ ...base, total_trades: 0 })).toBe("—");
  });

  it("returns percentage string for win_rate 0.65 with trades", () => {
    expect(formatWinRate({ ...base, total_trades: 20, win_rate: 0.65 })).toBe("65%");
  });

  it("returns 0% for win_rate 0 with trades", () => {
    expect(formatWinRate({ ...base, total_trades: 5, win_rate: 0 })).toBe("0%");
  });

  it("returns 100% for win_rate 1", () => {
    expect(formatWinRate({ ...base, total_trades: 10, win_rate: 1 })).toBe("100%");
  });
});

describe("AtlasOverview — open trades count", () => {
  it("converts 0 to '0'", () => {
    expect(formatOpenTrades(0)).toBe("0");
  });

  it("converts 3 to '3'", () => {
    expect(formatOpenTrades(3)).toBe("3");
  });
});

// ─── deriveTarget tests ───────────────────────────────────────────────────────

describe("AtlasOverview — deriveTarget", () => {
  it("inbox keyword → tempo", () => {
    expect(deriveTarget("inbox-triage")).toBe("tempo");
  });

  it("mail keyword → tempo", () => {
    expect(deriveTarget("daily-mail-check")).toBe("tempo");
  });

  it("calendar keyword → tempo", () => {
    expect(deriveTarget("calendar-sync")).toBe("tempo");
  });

  it("study keyword → scholar", () => {
    expect(deriveTarget("study-session")).toBe("scholar");
  });

  it("academic keyword → scholar", () => {
    expect(deriveTarget("academic-review")).toBe("scholar");
  });

  it("research keyword → lens", () => {
    expect(deriveTarget("daily-research")).toBe("lens");
  });

  it("monitor keyword → lens", () => {
    expect(deriveTarget("price-monitor")).toBe("lens");
  });

  it("atlas keyword → atlas", () => {
    expect(deriveTarget("atlas-scan")).toBe("atlas");
  });

  it("trade keyword → atlas", () => {
    expect(deriveTarget("trade-reconcile")).toBe("atlas");
  });

  it("sentinel keyword → sentinel", () => {
    expect(deriveTarget("sentinel-health")).toBe("sentinel");
  });

  it("unknown name → null", () => {
    expect(deriveTarget("unknown-job")).toBeNull();
  });

  it("empty string → null", () => {
    expect(deriveTarget("")).toBeNull();
  });
});

// ─── Schedule entry building ──────────────────────────────────────────────────

describe("AtlasOverview — schedule entries", () => {
  const schedule: Record<string, ScheduleJob> = {
    "inbox-triage":   { enabled: true },
    "trade-reconcile": { enabled: true },
    "disabled-job":   { enabled: false },
    "atlas-scan":     { enabled: true },
  };

  const runs: Record<string, string> = {
    "inbox-triage":    "2026-04-30T10:00:00Z",
    "trade-reconcile": "2026-04-30T08:00:00Z",
    "atlas-scan":      "2026-04-30T09:00:00Z",
  };

  it("filters out disabled jobs", () => {
    const entries = buildScheduleEntries(schedule, runs);
    expect(entries.map((e) => e.name)).not.toContain("disabled-job");
  });

  it("sorts entries ascending by nextIso", () => {
    const entries = buildScheduleEntries(schedule, runs);
    expect(entries[0].name).toBe("trade-reconcile");
    expect(entries[1].name).toBe("atlas-scan");
    expect(entries[2].name).toBe("inbox-triage");
  });

  it("returns at most 6 entries", () => {
    const bigSchedule: Record<string, ScheduleJob> = {};
    const bigRuns: Record<string, string> = {};
    for (let i = 0; i < 10; i++) {
      bigSchedule[`job-${i}`] = { enabled: true };
      bigRuns[`job-${i}`] = `2026-04-30T${String(i).padStart(2, "0")}:00:00Z`;
    }
    const entries = buildScheduleEntries(bigSchedule, bigRuns);
    expect(entries).toHaveLength(6);
  });

  it("excludes jobs with no run time", () => {
    const entries = buildScheduleEntries(
      { "no-run": { enabled: true } },
      {} // no entry for "no-run"
    );
    expect(entries).toHaveLength(0);
  });
});
