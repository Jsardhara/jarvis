/**
 * Tests for AgentMemoryPanel
 *
 * Tests the pure helper logic used by AgentMemoryPanel:
 *   - prettyValue: JSON pretty-print
 *   - relTime: relative time for updated_at
 *   - Key sorting: alphabetical
 *   - Value preview truncation at 200 chars
 *
 * Scenarios:
 *   1. empty memory → 0 keys
 *   2. keys are sorted alphabetically
 *   3. value is pretty-printed as JSON
 *   4. primitive values stringify correctly
 *   5. null value stringifies to "null"
 *   6. preview shows full value when < 200 chars
 *   7. preview truncates at 200 chars with ellipsis
 *   8. relTime: seconds
 *   9. relTime: minutes
 *  10. relTime: hours
 */

import { describe, it, expect } from "vitest";

// ─── Mirror prettyValue from AgentMemoryPanel ─────────────────────────────────

function prettyValue(val: unknown): string {
  try {
    return JSON.stringify(val, null, 2);
  } catch {
    return String(val);
  }
}

// ─── Mirror relTime from AgentMemoryPanel ─────────────────────────────────────

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  return `${Math.round(diff / 3_600_000)}h ago`;
}

// ─── Mirror preview from AgentMemoryPanel ─────────────────────────────────────

function makePreview(val: unknown): string {
  const full = prettyValue(val);
  return full.length > 200 ? full.slice(0, 200) + "…" : full;
}

// ─── Key handling ─────────────────────────────────────────────────────────────

describe("AgentMemoryPanel — key handling", () => {
  it("empty memory has 0 keys", () => {
    const memory: Record<string, unknown> = {};
    expect(Object.keys(memory)).toHaveLength(0);
  });

  it("sorts keys alphabetically", () => {
    const memory = {
      zebra: {},
      alpha: {},
      mango: {},
    };
    const sorted = Object.keys(memory).sort();
    expect(sorted).toEqual(["alpha", "mango", "zebra"]);
  });

  it("single-key memory has exactly one entry", () => {
    const memory = { current_regime: { value: "bull", updated_at: "2026-04-30T10:00:00Z" } };
    expect(Object.keys(memory)).toHaveLength(1);
  });
});

// ─── prettyValue ──────────────────────────────────────────────────────────────

describe("AgentMemoryPanel — prettyValue", () => {
  it("pretty-prints an object with 2-space indent", () => {
    const result = prettyValue({ a: 1 });
    expect(result).toContain("\n");
    expect(result).toContain("  ");
  });

  it("stringifies a string value with quotes", () => {
    const result = prettyValue("bull");
    expect(result).toBe('"bull"');
  });

  it("stringifies a number", () => {
    const result = prettyValue(42);
    expect(result).toBe("42");
  });

  it("stringifies null as 'null'", () => {
    const result = prettyValue(null);
    expect(result).toBe("null");
  });

  it("stringifies an array", () => {
    const result = prettyValue([1, 2, 3]);
    expect(JSON.parse(result)).toEqual([1, 2, 3]);
  });
});

// ─── Preview truncation ───────────────────────────────────────────────────────

describe("AgentMemoryPanel — value preview truncation", () => {
  it("shows full value when < 200 chars", () => {
    const preview = makePreview({ key: "short" });
    expect(preview).not.toContain("…");
  });

  it("truncates at 200 chars and appends ellipsis", () => {
    const longVal = { data: "x".repeat(500) };
    const preview = makePreview(longVal);
    expect(preview.endsWith("…")).toBe(true);
    expect(preview.slice(0, 200)).toHaveLength(200);
  });
});

// ─── relTime ──────────────────────────────────────────────────────────────────

describe("AgentMemoryPanel — relTime", () => {
  it("returns 'X s ago' for < 60s", () => {
    const iso = new Date(Date.now() - 10_000).toISOString();
    expect(relTime(iso)).toMatch(/^\d+s ago$/);
  });

  it("returns 'X m ago' for < 1h", () => {
    const iso = new Date(Date.now() - 15 * 60_000).toISOString();
    expect(relTime(iso)).toMatch(/^\d+m ago$/);
  });

  it("returns 'X h ago' for >= 1h", () => {
    const iso = new Date(Date.now() - 2 * 3_600_000).toISOString();
    expect(relTime(iso)).toMatch(/^\d+h ago$/);
  });
});
