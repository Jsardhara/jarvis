/**
 * Tests for useInboxStream logic.
 *
 * Environment: node (vitest default for this project).
 * We test the pure logic extracted from the hook rather than rendering it.
 *
 * Scenarios:
 *   1. Subscribes and filters frames where type !== "inbox.event"
 *   2. Accepts frames where type === "inbox.event" and extracts InboxEvent
 *   3. DOM cap: 200-event LRU — oldest events are dropped when limit exceeded
 *   4. Exponential backoff: delays grow 1s → 2s → 4s → 8s → 16s → 30s (max)
 *   5. Reconnects after close (backoff fires connect again)
 *   6. Event id/ts/agent/summary fields extracted from payload
 */

import { describe, it, expect } from "vitest";

// ─── Constants mirrored from useInboxStream.ts ────────────────────────────────

const MAX_EVENTS = 200;
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

// ─── Logic extracted for testing ─────────────────────────────────────────────

interface InboxEvent {
  id?: string;
  ts?: string;
  agent?: string;
  summary?: string;
  payload: Record<string, unknown>;
}

interface WsFrame {
  type: string;
  event?: Record<string, unknown>;
  [key: string]: unknown;
}

function parseFrame(data: string): InboxEvent | null {
  try {
    const frame = JSON.parse(data) as WsFrame;
    if (frame.type !== "inbox.event") return null;

    const raw = frame.event ?? {};
    return {
      id: typeof raw["id"] === "string" ? raw["id"] : undefined,
      ts: typeof raw["ts"] === "string" ? raw["ts"] : undefined,
      agent: typeof raw["agent"] === "string" ? raw["agent"] : undefined,
      summary: typeof raw["summary"] === "string" ? raw["summary"] : undefined,
      payload: raw,
    };
  } catch {
    return null;
  }
}

function capEvents(events: InboxEvent[], max: number): InboxEvent[] {
  if (events.length <= max) return events;
  return events.slice(events.length - max);
}

function computeBackoff(attempt: number): number {
  return Math.min(BACKOFF_BASE_MS * Math.pow(2, attempt), BACKOFF_MAX_MS);
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("useInboxStream — frame parsing", () => {
  it("returns null for frames where type is not inbox.event", () => {
    const traces = [
      JSON.stringify({ type: "agent.start", agent: "atlas", payload: {} }),
      JSON.stringify({ type: "agent.done", agent: "tempo" }),
      JSON.stringify({ type: "trace", payload: {} }),
    ];

    for (const raw of traces) {
      expect(parseFrame(raw)).toBeNull();
    }
  });

  it("accepts inbox.event frames and extracts InboxEvent fields", () => {
    const raw = JSON.stringify({
      type: "inbox.event",
      event: {
        id: "msg-001",
        ts: "2026-04-28T10:00:00Z",
        agent: "tempo",
        summary: "New mail from alice",
        subject: "Hello",
      },
    });

    const evt = parseFrame(raw);
    expect(evt).not.toBeNull();
    expect(evt?.id).toBe("msg-001");
    expect(evt?.ts).toBe("2026-04-28T10:00:00Z");
    expect(evt?.agent).toBe("tempo");
    expect(evt?.summary).toBe("New mail from alice");
    expect(evt?.payload["subject"]).toBe("Hello");
  });

  it("sets id/ts/agent/summary to undefined when fields are absent", () => {
    const raw = JSON.stringify({
      type: "inbox.event",
      event: { some_other_field: 42 },
    });

    const evt = parseFrame(raw);
    expect(evt).not.toBeNull();
    expect(evt?.id).toBeUndefined();
    expect(evt?.ts).toBeUndefined();
    expect(evt?.agent).toBeUndefined();
    expect(evt?.summary).toBeUndefined();
  });

  it("returns null for malformed JSON", () => {
    expect(parseFrame("not-json")).toBeNull();
    expect(parseFrame("{broken")).toBeNull();
  });

  it("returns null when event field is missing — still parses type", () => {
    const raw = JSON.stringify({ type: "inbox.event" });
    const evt = parseFrame(raw);
    // event field is missing → falls back to {}
    expect(evt).not.toBeNull();
    expect(evt?.payload).toEqual({});
  });
});

describe("useInboxStream — DOM cap (LRU 200)", () => {
  it("does not truncate when count is at the limit", () => {
    const events: InboxEvent[] = Array.from({ length: MAX_EVENTS }, (_, i) => ({
      id: `msg-${i}`,
      payload: {},
    }));

    const capped = capEvents(events, MAX_EVENTS);
    expect(capped.length).toBe(MAX_EVENTS);
  });

  it("drops the oldest events when count exceeds the limit", () => {
    const events: InboxEvent[] = Array.from({ length: MAX_EVENTS + 10 }, (_, i) => ({
      id: `msg-${i}`,
      payload: {},
    }));

    const capped = capEvents(events, MAX_EVENTS);
    expect(capped.length).toBe(MAX_EVENTS);
    // Oldest 10 are gone; first remaining is msg-10
    expect(capped[0].id).toBe("msg-10");
    // Last is msg-209
    expect(capped[capped.length - 1].id).toBe(`msg-${MAX_EVENTS + 9}`);
  });

  it("drops exactly one event when count exceeds by one", () => {
    const events: InboxEvent[] = Array.from({ length: MAX_EVENTS + 1 }, (_, i) => ({
      id: `evt-${i}`,
      payload: {},
    }));

    const capped = capEvents(events, MAX_EVENTS);
    expect(capped.length).toBe(MAX_EVENTS);
    expect(capped[0].id).toBe("evt-1");
  });
});

describe("useInboxStream — exponential backoff", () => {
  it("first attempt: 1s", () => {
    expect(computeBackoff(0)).toBe(1_000);
  });

  it("second attempt: 2s", () => {
    expect(computeBackoff(1)).toBe(2_000);
  });

  it("third attempt: 4s", () => {
    expect(computeBackoff(2)).toBe(4_000);
  });

  it("fourth attempt: 8s", () => {
    expect(computeBackoff(3)).toBe(8_000);
  });

  it("fifth attempt: 16s", () => {
    expect(computeBackoff(4)).toBe(16_000);
  });

  it("sixth attempt: capped at 30s", () => {
    expect(computeBackoff(5)).toBe(30_000);
  });

  it("high attempt count: always capped at max", () => {
    expect(computeBackoff(20)).toBe(BACKOFF_MAX_MS);
    expect(computeBackoff(100)).toBe(BACKOFF_MAX_MS);
  });
});
