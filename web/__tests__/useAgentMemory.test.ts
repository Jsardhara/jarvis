/**
 * Tests for useAgentMemory
 *
 * Tests the exported constant and logic from useAgentMemory:
 *   - REFRESH_INTERVAL_MS is 30s
 *   - MemoryEntry shape is correct
 *   - Memory key handling is stable
 *
 * Scenarios:
 *   1. REFRESH_INTERVAL_MS is exactly 30000
 *   2. MemoryEntry shape — value and updated_at fields
 *   3. Sorting keys alphabetically gives deterministic order
 *   4. Empty memory record has no keys
 *   5. Memory record with multiple keys sorts correctly
 */

import { describe, it, expect } from "vitest";
import { REFRESH_INTERVAL_MS } from "@/hooks/useAgentMemory";
import type { MemoryEntry } from "@/hooks/useAgentMemory";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeMemory(
  entries: [string, Partial<MemoryEntry>][]
): Record<string, MemoryEntry> {
  const out: Record<string, MemoryEntry> = {};
  for (const [k, v] of entries) {
    out[k] = {
      value: v.value ?? null,
      updated_at: v.updated_at ?? "2026-04-30T10:00:00Z",
    };
  }
  return out;
}

// ─── REFRESH_INTERVAL_MS constant ────────────────────────────────────────────

describe("useAgentMemory — REFRESH_INTERVAL_MS constant", () => {
  it("is exactly 30 seconds (30000ms)", () => {
    expect(REFRESH_INTERVAL_MS).toBe(30_000);
  });
});

// ─── MemoryEntry shape ────────────────────────────────────────────────────────

describe("useAgentMemory — MemoryEntry shape", () => {
  it("entry has value and updated_at", () => {
    const entry: MemoryEntry = {
      value: { current_regime: "bull" },
      updated_at: "2026-04-30T10:00:00Z",
    };
    expect(entry.value).toEqual({ current_regime: "bull" });
    expect(entry.updated_at).toBe("2026-04-30T10:00:00Z");
  });

  it("value can be a primitive", () => {
    const entry: MemoryEntry = { value: 42, updated_at: "2026-04-30T10:00:00Z" };
    expect(entry.value).toBe(42);
  });

  it("value can be null", () => {
    const entry: MemoryEntry = { value: null, updated_at: "2026-04-30T10:00:00Z" };
    expect(entry.value).toBeNull();
  });
});

// ─── Memory record key handling ───────────────────────────────────────────────

describe("useAgentMemory — memory record key handling", () => {
  it("empty record has no keys", () => {
    const memory: Record<string, MemoryEntry> = {};
    expect(Object.keys(memory)).toHaveLength(0);
  });

  it("sorts keys alphabetically for deterministic display", () => {
    const memory = makeMemory([
      ["zebra", {}],
      ["alpha", {}],
      ["middle", {}],
    ]);
    const sorted = Object.keys(memory).sort();
    expect(sorted).toEqual(["alpha", "middle", "zebra"]);
  });

  it("single key memory has exactly one entry", () => {
    const memory = makeMemory([["current_regime", { value: "bull" }]]);
    expect(Object.keys(memory)).toHaveLength(1);
    expect(memory["current_regime"].value).toBe("bull");
  });

  it("preserves complex nested value shapes", () => {
    const nested = { signals: [{ pair: "BTC/USD", score: 0.9 }] };
    const memory = makeMemory([["signals_cache", { value: nested }]]);
    expect(memory["signals_cache"].value).toEqual(nested);
  });

  it("updated_at is an ISO string", () => {
    const memory = makeMemory([["key", { updated_at: "2026-04-30T12:34:56Z" }]]);
    const iso = memory["key"].updated_at;
    expect(new Date(iso).toISOString()).toBe("2026-04-30T12:34:56.000Z");
  });
});
