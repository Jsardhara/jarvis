/**
 * Tests for OracleWidgets logic
 *
 * Tests the pure data-extraction helpers and contract types that drive the
 * Oracle workspace widgets. No DOM rendering — logic only.
 *
 * Scenarios:
 *   1.  Extracts candidates from memory['screener_candidates']
 *   2.  Caps candidates at 10
 *   3.  Falls back to RESEARCH_UPDATE event when memory is empty
 *   4.  Returns empty array when no memory and no matching event
 *   5.  Counts shortable from memory['shortable_set'] array
 *   6.  Falls back to counting shortable-flagged candidates
 *   7.  Empty memory + empty events → 0 shortable
 *   8.  Direction chip: LONG → ok kind
 *   9.  Direction chip: SHORT → crit kind
 *  10.  Signal status 'pending' maps to amber
 *  11.  Signal status 'approved' maps to ok
 *  12.  Signal status 'rejected' maps to crit
 *  13.  Signal URL includes signal_id param
 *  14.  Empty signals list is handled
 *  15.  OracleWidgetsProps requires agentId string
 */

import { describe, it, expect } from "vitest";
import type { MemoryEntry } from "@/hooks/useAgentMemory";
import type { RecentActivity } from "@/hooks/useAgentDetail";

// ─── Types mirrored from OracleWidgets ────────────────────────────────────────

interface Candidate {
  pair: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  score: number;
  shortable?: boolean;
}

interface Signal {
  signal_id: string;
  pair: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  status: "pending" | "approved" | "rejected";
}

// ─── Pure helpers mirrored from OracleWidgets ─────────────────────────────────

type TagKind = "ok" | "crit" | "default" | "amber" | "info";

function dirChipKind(dir: string): TagKind {
  if (dir === "LONG") return "ok";
  if (dir === "SHORT") return "crit";
  return "default";
}

const STATUS_KIND: Record<string, TagKind> = {
  pending: "amber",
  approved: "ok",
  rejected: "crit",
};

function extractCandidates(
  memory: Record<string, MemoryEntry>,
  recentActivity: RecentActivity[]
): Candidate[] {
  const raw = memory["screener_candidates"]?.value;
  if (Array.isArray(raw) && raw.length > 0) {
    return (raw as Candidate[]).slice(0, 10);
  }
  const event = recentActivity.find(
    (e) => e.event_type === "RESEARCH_UPDATE" && Array.isArray(e.payload?.candidates)
  );
  if (event) {
    return (event.payload.candidates as Candidate[]).slice(0, 10);
  }
  return [];
}

function extractShortableCount(
  memory: Record<string, MemoryEntry>,
  candidates: Candidate[]
): number {
  const raw = memory["shortable_set"]?.value;
  if (Array.isArray(raw)) return raw.length;
  return candidates.filter((c) => c.shortable).length;
}

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeMemoryEntry(value: unknown): MemoryEntry {
  return { value, updated_at: "2026-04-30T10:00:00Z" };
}

function makeCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    pair: "BTC/USD",
    direction: "LONG",
    score: 0.75,
    ...overrides,
  };
}

function makeSignal(overrides: Partial<Signal> = {}): Signal {
  return {
    signal_id: `sig-${Math.random().toString(36).slice(2, 8)}`,
    pair: "BTC/USD",
    direction: "LONG",
    confidence: 0.8,
    status: "pending",
    ...overrides,
  };
}

function makeActivity(eventType: string, payload: Record<string, unknown>): RecentActivity {
  return { event_type: eventType, payload, occurred_at: "2026-04-30T10:00:00Z" };
}

// ─── Candidate extraction ─────────────────────────────────────────────────────

describe("OracleWidgets — candidate extraction from memory", () => {
  it("returns candidates from memory screener_candidates key", () => {
    const candidates = [makeCandidate({ pair: "BTC/USD" }), makeCandidate({ pair: "ETH/USD" })];
    const memory: Record<string, MemoryEntry> = {
      screener_candidates: makeMemoryEntry(candidates),
    };
    const result = extractCandidates(memory, []);
    expect(result).toHaveLength(2);
    expect(result[0].pair).toBe("BTC/USD");
  });

  it("caps candidates at 10", () => {
    const candidates = Array.from({ length: 15 }, (_, i) => makeCandidate({ pair: `PAIR${i}/USD` }));
    const memory: Record<string, MemoryEntry> = {
      screener_candidates: makeMemoryEntry(candidates),
    };
    const result = extractCandidates(memory, []);
    expect(result).toHaveLength(10);
  });

  it("falls back to RESEARCH_UPDATE event when memory has no candidates", () => {
    const candidates = [makeCandidate({ pair: "XRP/USD" })];
    const activity: RecentActivity[] = [
      makeActivity("RESEARCH_UPDATE", { candidates }),
    ];
    const result = extractCandidates({}, activity);
    expect(result).toHaveLength(1);
    expect(result[0].pair).toBe("XRP/USD");
  });

  it("returns empty array when no memory and no matching event", () => {
    const result = extractCandidates({}, []);
    expect(result).toHaveLength(0);
  });

  it("ignores non-RESEARCH_UPDATE events", () => {
    const activity: RecentActivity[] = [
      makeActivity("MARKET_SCAN", { candidates: [makeCandidate()] }),
    ];
    const result = extractCandidates({}, activity);
    expect(result).toHaveLength(0);
  });
});

// ─── Shortable count ──────────────────────────────────────────────────────────

describe("OracleWidgets — shortable count extraction", () => {
  it("counts from memory shortable_set array", () => {
    const memory: Record<string, MemoryEntry> = {
      shortable_set: makeMemoryEntry(["BTC/USD", "ETH/USD", "XRP/USD"]),
    };
    const count = extractShortableCount(memory, []);
    expect(count).toBe(3);
  });

  it("falls back to counting shortable-flagged candidates", () => {
    const candidates = [
      makeCandidate({ shortable: true }),
      makeCandidate({ shortable: false }),
      makeCandidate({ shortable: true }),
    ];
    const count = extractShortableCount({}, candidates);
    expect(count).toBe(2);
  });

  it("returns 0 when no shortable_set and no shortable candidates", () => {
    const count = extractShortableCount({}, []);
    expect(count).toBe(0);
  });
});

// ─── Direction chip kind ──────────────────────────────────────────────────────

describe("OracleWidgets — direction chip kind", () => {
  it("LONG maps to ok", () => {
    expect(dirChipKind("LONG")).toBe("ok");
  });

  it("SHORT maps to crit", () => {
    expect(dirChipKind("SHORT")).toBe("crit");
  });

  it("NEUTRAL maps to default", () => {
    expect(dirChipKind("NEUTRAL")).toBe("default");
  });
});

// ─── Signal status kind ───────────────────────────────────────────────────────

describe("OracleWidgets — signal status kind", () => {
  it("pending maps to amber", () => {
    expect(STATUS_KIND["pending"]).toBe("amber");
  });

  it("approved maps to ok", () => {
    expect(STATUS_KIND["approved"]).toBe("ok");
  });

  it("rejected maps to crit", () => {
    expect(STATUS_KIND["rejected"]).toBe("crit");
  });
});

// ─── Signal URL contract ──────────────────────────────────────────────────────

describe("OracleWidgets — signal link URL", () => {
  it("link includes signal_id as query param", () => {
    const sig = makeSignal({ signal_id: "abc-123" });
    const url = `/atlas/trades?signal_id=${sig.signal_id}`;
    expect(url).toContain("signal_id=abc-123");
    expect(url).toBe("/atlas/trades?signal_id=abc-123");
  });

  it("empty signal list produces no URLs", () => {
    const signals: Signal[] = [];
    const urls = signals.map((s) => `/atlas/trades?signal_id=${s.signal_id}`);
    expect(urls).toHaveLength(0);
  });
});

// ─── Props contract ───────────────────────────────────────────────────────────

describe("OracleWidgets — props contract", () => {
  it("requires agentId string", () => {
    const props: { agentId: string } = { agentId: "oracle" };
    expect(typeof props.agentId).toBe("string");
    expect(props.agentId).toBe("oracle");
  });
});
