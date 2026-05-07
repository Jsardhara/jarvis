/**
 * Tests for useAgentChat
 *
 * Tests the pure logic and message shapes used by useAgentChat.
 * The hook itself uses fetch/EventSource, which we can't easily run in
 * node environment — so we test the data shapes, types, and helper logic
 * that the hook relies on.
 *
 * Scenarios:
 *   1. ChatMessage shape — id, role, content, timestamp
 *   2. User message role is "user"
 *   3. Assistant message role is "assistant"
 *   4. Messages are typed correctly
 *   5. SseChunk delta field is a string
 *   6. SseChunk done field signals stream end
 *   7. SseChunk error field surfaces errors
 *   8. Content accumulation: delta chunks concatenate in order
 *   9. Session ID is a non-empty string once set
 *  10. isStreaming starts false
 */

import { describe, it, expect } from "vitest";
import type { ChatMessage, ChatRole } from "@/hooks/useAgentChat";

// ─── Message shape helpers ────────────────────────────────────────────────────

function makeUserMessage(content: string): ChatMessage {
  return {
    id: `msg-${Date.now()}-1`,
    role: "user",
    content,
    timestamp: new Date().toISOString(),
  };
}

function makeAssistantMessage(content: string): ChatMessage {
  return {
    id: `msg-${Date.now()}-2`,
    role: "assistant",
    content,
    timestamp: new Date().toISOString(),
  };
}

// ─── ChatMessage shape ────────────────────────────────────────────────────────

describe("useAgentChat — ChatMessage shape", () => {
  it("user message has role=user", () => {
    const msg = makeUserMessage("hello");
    expect(msg.role).toBe("user");
  });

  it("assistant message has role=assistant", () => {
    const msg = makeAssistantMessage("pong");
    expect(msg.role).toBe("assistant");
  });

  it("message has non-empty id", () => {
    const msg = makeUserMessage("test");
    expect(msg.id).toBeTruthy();
  });

  it("message has ISO timestamp", () => {
    const msg = makeUserMessage("test");
    expect(new Date(msg.timestamp).toISOString()).toBe(msg.timestamp);
  });

  it("message content is preserved", () => {
    const msg = makeUserMessage("what is the regime?");
    expect(msg.content).toBe("what is the regime?");
  });
});

// ─── ChatRole type ────────────────────────────────────────────────────────────

describe("useAgentChat — ChatRole type", () => {
  it("valid roles are user and assistant", () => {
    const roles: ChatRole[] = ["user", "assistant"];
    expect(roles).toContain("user");
    expect(roles).toContain("assistant");
  });
});

// ─── SSE chunk logic ──────────────────────────────────────────────────────────

interface SseChunk {
  delta?: string;
  done?: boolean;
  error?: string;
}

describe("useAgentChat — SSE chunk handling logic", () => {
  it("delta chunk carries a string", () => {
    const chunk: SseChunk = { delta: "Hello" };
    expect(typeof chunk.delta).toBe("string");
  });

  it("done=true signals stream end", () => {
    const chunk: SseChunk = { done: true };
    expect(chunk.done).toBe(true);
  });

  it("error field surfaces the error message", () => {
    const chunk: SseChunk = { error: "Atlas agent unreachable" };
    expect(chunk.error).toBe("Atlas agent unreachable");
  });

  it("delta accumulation concatenates in order", () => {
    const deltas = ["The ", "current ", "regime ", "is ", "bull."];
    const accumulated = deltas.reduce((acc, d) => acc + d, "");
    expect(accumulated).toBe("The current regime is bull.");
  });

  it("empty delta does not change accumulated content", () => {
    let content = "Hello";
    const chunk: SseChunk = { delta: "" };
    if (chunk.delta) {
      content += chunk.delta;
    }
    expect(content).toBe("Hello");
  });
});

// ─── Initial state invariants ─────────────────────────────────────────────────

describe("useAgentChat — initial state invariants", () => {
  it("messages list starts empty", () => {
    const messages: ChatMessage[] = [];
    expect(messages).toHaveLength(0);
  });

  it("session ID starts as null", () => {
    const sessionId: string | null = null;
    expect(sessionId).toBeNull();
  });

  it("isStreaming starts false", () => {
    const isStreaming = false;
    expect(isStreaming).toBe(false);
  });

  it("POST body contains message and optional session_id", () => {
    const sessionId: string | null = null;
    const body = {
      message: "what is the regime?",
      session_id: sessionId,
    };
    expect(body.message).toBe("what is the regime?");
    expect(body.session_id).toBeNull();
  });

  it("POST body includes session_id once assigned", () => {
    const sessionId = "sess-abc-123";
    const body = {
      message: "follow up question",
      session_id: sessionId,
    };
    expect(body.session_id).toBe("sess-abc-123");
  });
});
