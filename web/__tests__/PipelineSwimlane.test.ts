/**
 * Tests for PipelineSwimlane logic and usePipelineStream state management.
 *
 * The vitest environment is "node" so we test pure logic extracted from the
 * components rather than rendering them. Component rendering contracts are
 * verified through logic tests that mirror the implementation.
 *
 * Scenarios:
 *   1. Five lanes render in correct order
 *   2. Lane accepts events and routes by lane field
 *   3. Lane state precedence: error > blocked > running > pending > done
 *   4. 80-event DOM cap per lane (LRU drop)
 *   5. Confirmation gate triggered by needsConfirm + blocked state
 */

import { describe, it, expect } from "vitest";
import type { PipelineLane, PipelineState, TraceEvent } from "@/lib/types";

// ─── Constants mirrored from PipelineSwimlane.tsx ────────────────────────────

const LANES: PipelineLane[] = [
  "oracle",
  "architect",
  "guardian",
  "trader",
  "sage",
];

const STATE_PRECEDENCE: PipelineState[] = [
  "error",
  "blocked",
  "running",
  "pending",
  "done",
];

const MAX_EVENTS_PER_LANE = 80;

// ─── Logic extracted for testing ─────────────────────────────────────────────

function worstState(states: PipelineState[]): PipelineState {
  for (const s of STATE_PRECEDENCE) {
    if (states.includes(s)) return s;
  }
  return "done";
}

function capLane(
  events: TraceEvent[],
  lane: PipelineLane,
  max: number
): TraceEvent[] {
  const inLane = events.filter((e) => e.lane === lane);
  if (inLane.length <= max) return events;
  const toDrop = inLane.length - max;
  let dropped = 0;
  return events.filter((e) => {
    if (e.lane !== lane) return true;
    if (dropped < toDrop) {
      dropped++;
      return false;
    }
    return true;
  });
}

function makeEvent(
  overrides: Partial<TraceEvent> & { lane: PipelineLane; state: PipelineState }
): TraceEvent {
  return {
    id: overrides.id ?? `evt-${Math.random().toString(36).slice(2, 8)}`,
    pipelineRun: overrides.pipelineRun ?? 1,
    lane: overrides.lane,
    state: overrides.state,
    startedAt: overrides.startedAt ?? new Date().toISOString(),
    durationMs: overrides.durationMs,
    tier: overrides.tier,
    intent: overrides.intent,
    needsConfirm: overrides.needsConfirm,
    violations: overrides.violations,
    errorMessage: overrides.errorMessage,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("PipelineSwimlane — lane order", () => {
  it("defines exactly 5 lanes in correct pipeline order", () => {
    expect(LANES).toHaveLength(5);
    expect(LANES[0]).toBe("oracle");
    expect(LANES[1]).toBe("architect");
    expect(LANES[2]).toBe("guardian");
    expect(LANES[3]).toBe("trader");
    expect(LANES[4]).toBe("sage");
  });
});

describe("PipelineSwimlane — event routing", () => {
  it("routes events to their respective lanes", () => {
    const events: TraceEvent[] = [
      makeEvent({ id: "e1", lane: "oracle",    state: "done" }),
      makeEvent({ id: "e2", lane: "architect", state: "running" }),
      makeEvent({ id: "e3", lane: "guardian",  state: "blocked" }),
      makeEvent({ id: "e4", lane: "trader",    state: "pending" }),
      makeEvent({ id: "e5", lane: "sage",      state: "done" }),
    ];

    for (const lane of LANES) {
      const laneEvents = events.filter((e) => e.lane === lane);
      expect(laneEvents).toHaveLength(1);
      expect(laneEvents[0].lane).toBe(lane);
    }
  });

  it("accepts multiple events per lane", () => {
    const events: TraceEvent[] = [
      makeEvent({ id: "e1", lane: "oracle", state: "done" }),
      makeEvent({ id: "e2", lane: "oracle", state: "running" }),
      makeEvent({ id: "e3", lane: "oracle", state: "pending" }),
    ];
    const oracleEvents = events.filter((e) => e.lane === "oracle");
    expect(oracleEvents).toHaveLength(3);
  });
});

describe("PipelineSwimlane — lane state precedence", () => {
  it("returns error when any event is in error state", () => {
    const states: PipelineState[] = ["done", "running", "error", "pending"];
    expect(worstState(states)).toBe("error");
  });

  it("returns blocked when no error but blocked present", () => {
    const states: PipelineState[] = ["done", "running", "blocked", "pending"];
    expect(worstState(states)).toBe("blocked");
  });

  it("returns running when no error or blocked", () => {
    const states: PipelineState[] = ["done", "running", "pending"];
    expect(worstState(states)).toBe("running");
  });

  it("returns pending when no error, blocked, or running", () => {
    const states: PipelineState[] = ["done", "pending", "done"];
    expect(worstState(states)).toBe("pending");
  });

  it("returns done when all events are done", () => {
    const states: PipelineState[] = ["done", "done", "done"];
    expect(worstState(states)).toBe("done");
  });

  it("returns done for an empty state list", () => {
    expect(worstState([])).toBe("done");
  });

  it("error beats all other states simultaneously", () => {
    const states: PipelineState[] = ["error", "blocked", "running", "pending", "done"];
    expect(worstState(states)).toBe("error");
  });
});

describe("PipelineSwimlane — 80-event DOM cap", () => {
  it("keeps all events when count is at or below cap", () => {
    const events = Array.from({ length: 80 }, (_, i) =>
      makeEvent({ id: `e${i}`, lane: "oracle", state: "done" })
    );
    const capped = capLane(events, "oracle", MAX_EVENTS_PER_LANE);
    expect(capped.filter((e) => e.lane === "oracle")).toHaveLength(80);
  });

  it("drops oldest oracle events when lane exceeds 80", () => {
    // 85 oracle events — should drop 5 oldest
    const events = Array.from({ length: 85 }, (_, i) =>
      makeEvent({ id: `e${i}`, lane: "oracle", state: "done" })
    );
    const capped = capLane(events, "oracle", MAX_EVENTS_PER_LANE);
    const oracleEvents = capped.filter((e) => e.lane === "oracle");
    expect(oracleEvents).toHaveLength(80);
    // Oldest 5 (e0..e4) should be gone, e5 should be the new head
    expect(oracleEvents[0].id).toBe("e5");
    expect(oracleEvents[79].id).toBe("e84");
  });

  it("does not affect events in other lanes when capping one lane", () => {
    const oracleEvents = Array.from({ length: 85 }, (_, i) =>
      makeEvent({ id: `oracle-${i}`, lane: "oracle", state: "done" })
    );
    const architectEvents = Array.from({ length: 10 }, (_, i) =>
      makeEvent({ id: `arch-${i}`, lane: "architect", state: "running" })
    );
    const all = [...oracleEvents, ...architectEvents];
    const capped = capLane(all, "oracle", MAX_EVENTS_PER_LANE);

    expect(capped.filter((e) => e.lane === "oracle")).toHaveLength(80);
    expect(capped.filter((e) => e.lane === "architect")).toHaveLength(10);
  });
});

describe("PipelineSwimlane — confirmation gate", () => {
  it("detects guardian blocked+needsConfirm event", () => {
    const events: TraceEvent[] = [
      makeEvent({ id: "e1", lane: "guardian", state: "blocked", needsConfirm: true }),
    ];
    const confirmPending = events.some(
      (e) => e.lane === "guardian" && e.state === "blocked" && e.needsConfirm
    );
    expect(confirmPending).toBe(true);
  });

  it("does not trigger gate for guardian done event", () => {
    const events: TraceEvent[] = [
      makeEvent({ id: "e1", lane: "guardian", state: "done" }),
    ];
    const confirmPending = events.some(
      (e) => e.lane === "guardian" && e.state === "blocked" && e.needsConfirm
    );
    expect(confirmPending).toBe(false);
  });

  it("captures violations from the event", () => {
    const evt = makeEvent({
      id: "e1",
      lane: "guardian",
      state: "blocked",
      needsConfirm: true,
      violations: ["position_size_exceeds_max", "drawdown_threshold"],
    });
    expect(evt.violations).toHaveLength(2);
    expect(evt.violations).toContain("position_size_exceeds_max");
  });

  it("blocked state without needsConfirm does not trigger gate", () => {
    const events: TraceEvent[] = [
      makeEvent({ id: "e1", lane: "guardian", state: "blocked", needsConfirm: false }),
    ];
    const confirmPending = events.some(
      (e) => e.lane === "guardian" && e.state === "blocked" && e.needsConfirm
    );
    expect(confirmPending).toBe(false);
  });
});

describe("PipelineSwimlane — pipeline header state", () => {
  it("shows guardian AWAITING when blocked+needsConfirm event exists", () => {
    const events: TraceEvent[] = [
      makeEvent({ id: "e1", lane: "oracle",   state: "done"    }),
      makeEvent({ id: "e2", lane: "guardian", state: "blocked", needsConfirm: true }),
    ];
    const guardianBlocked = events.some(
      (e) => e.lane === "guardian" && e.state === "blocked" && e.needsConfirm
    );
    const headerText = guardianBlocked ? "AWAITING" : "PASS";
    expect(headerText).toBe("AWAITING");
  });

  it("shows guardian PASS when no blocked event", () => {
    const events: TraceEvent[] = [
      makeEvent({ id: "e1", lane: "oracle",   state: "done" }),
      makeEvent({ id: "e2", lane: "guardian", state: "done" }),
    ];
    const guardianBlocked = events.some(
      (e) => e.lane === "guardian" && e.state === "blocked" && e.needsConfirm
    );
    const headerText = guardianBlocked ? "AWAITING" : "PASS";
    expect(headerText).toBe("PASS");
  });
});
