/**
 * Tests for usePipelineStream — Atlas event parsing (Phase 3b).
 *
 * Covers both event sources:
 *   1. Jarvis-synthesized events (agent=atlas, type=agent.*)
 *   2. Atlas-emitted events (type=atlas.<message_type>)
 *
 * Scenarios:
 *   1. Jarvis-synthesized: oracle stage event → oracle lane
 *   2. Jarvis-synthesized: agent.done without stage → ignored
 *   3. Atlas: atlas.market_signal → oracle lane, state=done
 *   4. Atlas: atlas.strategy_proposed → architect lane
 *   5. Atlas: atlas.trade_approved → guardian lane, state=done
 *   6. Atlas: atlas.trade_rejected → guardian lane, state=error
 *   7. Atlas: atlas.order_placed → trader lane
 *   8. Atlas: atlas.order_filled → trader lane
 *   9. Atlas: atlas.position_opened → trader lane
 *  10. Atlas: atlas.position_closed → trader lane
 *  11. Atlas: atlas.learning_insight → sage lane
 *  12. Atlas: atlas.pipeline_decision with action=block → oracle lane, state=blocked
 *  13. Atlas: atlas.pipeline_decision with action=advance → oracle lane, state=done
 *  14. Atlas: atlas.agent_status → null (not a pipeline event)
 *  15. Correlation_id threading: two events with same correlation_id get different ids
 *  16. Unknown atlas.* type → null
 *  17. Non-atlas event with no agent field → null
 */

import { describe, it, expect } from "vitest";
import type { PipelineLane, PipelineState, TraceEvent } from "@/lib/types";

// ─── Constants mirrored from usePipelineStream ────────────────────────────────

const PIPELINE_LANES: PipelineLane[] = [
  "oracle", "architect", "guardian", "trader", "sage",
];

const ATLAS_EVENT_LANE: Record<string, PipelineLane | null> = {
  "atlas.pipeline_decision":  "oracle",
  "atlas.market_signal":      "oracle",
  "atlas.strategy_proposed":  "architect",
  "atlas.trade_approved":     "guardian",
  "atlas.trade_rejected":     "guardian",
  "atlas.trade_modified":     "guardian",
  "atlas.order_placed":       "trader",
  "atlas.order_filled":       "trader",
  "atlas.position_opened":    "trader",
  "atlas.position_closed":    "trader",
  "atlas.learning_insight":   "sage",
  "atlas.agent_status":       null,
};

// ─── Mirror WS message type ───────────────────────────────────────────────────

interface WsMessage {
  type: string;
  request_id?: string;
  correlation_id?: string;
  agent?: string;
  payload?: {
    stage?: string;
    state?: string;
    duration_ms?: number;
    tier?: number;
    intent?: string;
    needs_confirm?: boolean;
    violations?: string[];
    error?: string;
    pipeline_run?: number;
    signal_id?: string;
    direction?: string;
    action?: string;
    reason?: string;
  };
  ts?: string;
}

// ─── Mirror parsing logic ─────────────────────────────────────────────────────

function fromJarvisEvent(msg: WsMessage): TraceEvent | null {
  if (!msg.agent || msg.agent !== "atlas") return null;
  const payload = msg.payload ?? {};
  const stage = (payload.stage ?? "").toLowerCase() as PipelineLane;
  if (!PIPELINE_LANES.includes(stage)) return null;

  const id = msg.request_id
    ? `${msg.request_id}:${stage}`
    : `${stage}:0`;

  let state: PipelineState = "pending";
  if (msg.type === "agent.start") state = "running";
  else if (msg.type === "agent.done") {
    state = payload.needs_confirm ? "blocked" : "done";
  } else if (msg.type === "agent.error") state = "error";
  else if (payload.state) {
    const raw = payload.state;
    if (["pending", "running", "done", "blocked", "error"].includes(raw)) {
      state = raw as PipelineState;
    }
  }

  return {
    id,
    pipelineRun: payload.pipeline_run ?? 0,
    lane: stage,
    state,
    startedAt: msg.ts ?? new Date().toISOString(),
    durationMs: payload.duration_ms,
    tier: payload.tier as TraceEvent["tier"],
    intent: payload.intent,
    needsConfirm: payload.needs_confirm,
    violations: payload.violations,
    errorMessage: payload.error,
  };
}

function fromAtlasEvent(msg: WsMessage): TraceEvent | null {
  const lane = ATLAS_EVENT_LANE[msg.type];
  if (lane === undefined) return null;
  if (lane === null) return null;

  const payload = msg.payload ?? {};

  const correlationBase =
    msg.correlation_id ??
    payload.signal_id ??
    msg.request_id ??
    `${msg.type}:0`;

  const typeSuffix = msg.type.replace(/^atlas\./, "");
  const id = `${correlationBase}:${typeSuffix}`;

  let state: PipelineState = "done";
  if (msg.type === "atlas.trade_rejected") state = "error";
  else if (msg.type === "atlas.pipeline_decision") {
    const decision = (payload.action ?? payload.direction ?? "").toString().toLowerCase();
    if (decision === "block" || decision === "halt") state = "blocked";
    else state = "done";
  }

  const intent =
    (payload.intent as string | undefined) ??
    (payload.direction as string | undefined) ??
    (payload.action as string | undefined) ??
    (payload.reason as string | undefined);

  return {
    id,
    pipelineRun: (payload.pipeline_run as number | undefined) ?? 0,
    lane,
    state,
    startedAt: msg.ts ?? new Date().toISOString(),
    intent,
    errorMessage:
      msg.type === "atlas.trade_rejected"
        ? ((payload.reason as string | undefined) ?? "trade rejected")
        : undefined,
  };
}

function toTraceEvent(msg: WsMessage): TraceEvent | null {
  if (msg.type?.startsWith("atlas.")) return fromAtlasEvent(msg);
  return fromJarvisEvent(msg);
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("usePipelineStream — Jarvis-synthesized events", () => {
  it("oracle stage event maps to oracle lane with running state", () => {
    const ev = toTraceEvent({
      type: "agent.start",
      agent: "atlas",
      request_id: "req-001",
      payload: { stage: "oracle", pipeline_run: 5 },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("oracle");
    expect(ev!.state).toBe("running");
    expect(ev!.id).toBe("req-001:oracle");
    expect(ev!.pipelineRun).toBe(5);
  });

  it("agent.done with needs_confirm → blocked state", () => {
    const ev = toTraceEvent({
      type: "agent.done",
      agent: "atlas",
      request_id: "req-002",
      payload: { stage: "guardian", needs_confirm: true },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("guardian");
    expect(ev!.state).toBe("blocked");
    expect(ev!.needsConfirm).toBe(true);
  });

  it("agent.done without needs_confirm → done state", () => {
    const ev = toTraceEvent({
      type: "agent.done",
      agent: "atlas",
      payload: { stage: "sage" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.state).toBe("done");
  });

  it("agent.error → error state", () => {
    const ev = toTraceEvent({
      type: "agent.error",
      agent: "atlas",
      payload: { stage: "trader", error: "timeout" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.state).toBe("error");
    expect(ev!.errorMessage).toBe("timeout");
  });

  it("event without stage → null", () => {
    const ev = toTraceEvent({
      type: "agent.done",
      agent: "atlas",
      payload: {},
    });
    expect(ev).toBeNull();
  });

  it("non-atlas agent → null", () => {
    const ev = toTraceEvent({
      type: "agent.start",
      agent: "tempo",
      payload: { stage: "oracle" },
    });
    expect(ev).toBeNull();
  });
});

describe("usePipelineStream — Atlas-emitted events: oracle lane", () => {
  it("atlas.market_signal → oracle lane, state=done", () => {
    const ev = toTraceEvent({
      type: "atlas.market_signal",
      payload: { direction: "LONG", signal_id: "sig-1" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("oracle");
    expect(ev!.state).toBe("done");
    expect(ev!.intent).toBe("LONG");
  });

  it("atlas.pipeline_decision with action=advance → oracle lane, state=done", () => {
    const ev = toTraceEvent({
      type: "atlas.pipeline_decision",
      correlation_id: "corr-1",
      payload: { action: "advance" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("oracle");
    expect(ev!.state).toBe("done");
  });

  it("atlas.pipeline_decision with action=block → oracle lane, state=blocked", () => {
    const ev = toTraceEvent({
      type: "atlas.pipeline_decision",
      correlation_id: "corr-2",
      payload: { action: "block" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("oracle");
    expect(ev!.state).toBe("blocked");
  });

  it("atlas.pipeline_decision with action=halt → blocked", () => {
    const ev = toTraceEvent({
      type: "atlas.pipeline_decision",
      payload: { action: "halt" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.state).toBe("blocked");
  });
});

describe("usePipelineStream — Atlas-emitted events: architect lane", () => {
  it("atlas.strategy_proposed → architect lane, state=done", () => {
    const ev = toTraceEvent({
      type: "atlas.strategy_proposed",
      payload: { intent: "momentum_reversal" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("architect");
    expect(ev!.state).toBe("done");
    expect(ev!.intent).toBe("momentum_reversal");
  });
});

describe("usePipelineStream — Atlas-emitted events: guardian lane", () => {
  it("atlas.trade_approved → guardian lane, state=done", () => {
    const ev = toTraceEvent({ type: "atlas.trade_approved", payload: {} });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("guardian");
    expect(ev!.state).toBe("done");
  });

  it("atlas.trade_rejected → guardian lane, state=error, errorMessage set", () => {
    const ev = toTraceEvent({
      type: "atlas.trade_rejected",
      payload: { reason: "drawdown_limit" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("guardian");
    expect(ev!.state).toBe("error");
    expect(ev!.errorMessage).toBe("drawdown_limit");
  });

  it("atlas.trade_rejected with no reason → default error message", () => {
    const ev = toTraceEvent({ type: "atlas.trade_rejected", payload: {} });
    expect(ev).not.toBeNull();
    expect(ev!.errorMessage).toBe("trade rejected");
  });

  it("atlas.trade_modified → guardian lane, state=done", () => {
    const ev = toTraceEvent({ type: "atlas.trade_modified", payload: {} });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("guardian");
    expect(ev!.state).toBe("done");
  });
});

describe("usePipelineStream — Atlas-emitted events: trader lane", () => {
  it("atlas.order_placed → trader lane", () => {
    const ev = toTraceEvent({ type: "atlas.order_placed", payload: {} });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("trader");
  });

  it("atlas.order_filled → trader lane", () => {
    const ev = toTraceEvent({ type: "atlas.order_filled", payload: {} });
    expect(ev!.lane).toBe("trader");
  });

  it("atlas.position_opened → trader lane", () => {
    const ev = toTraceEvent({ type: "atlas.position_opened", payload: {} });
    expect(ev!.lane).toBe("trader");
  });

  it("atlas.position_closed → trader lane", () => {
    const ev = toTraceEvent({ type: "atlas.position_closed", payload: {} });
    expect(ev!.lane).toBe("trader");
  });
});

describe("usePipelineStream — Atlas-emitted events: sage lane", () => {
  it("atlas.learning_insight → sage lane", () => {
    const ev = toTraceEvent({
      type: "atlas.learning_insight",
      payload: { intent: "adjusted momentum weight" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.lane).toBe("sage");
    expect(ev!.intent).toBe("adjusted momentum weight");
  });
});

describe("usePipelineStream — Atlas-emitted events: skipped", () => {
  it("atlas.agent_status → null (handled by AgentStatusRow)", () => {
    const ev = toTraceEvent({
      type: "atlas.agent_status",
      payload: {},
    });
    expect(ev).toBeNull();
  });
});

describe("usePipelineStream — Correlation id threading", () => {
  it("two atlas events with the same correlation_id get different ids via type suffix", () => {
    const base = { correlation_id: "corr-99" };
    const ev1 = toTraceEvent({ ...base, type: "atlas.market_signal", payload: {} });
    const ev2 = toTraceEvent({ ...base, type: "atlas.pipeline_decision", payload: { action: "advance" } });

    expect(ev1).not.toBeNull();
    expect(ev2).not.toBeNull();
    expect(ev1!.id).not.toBe(ev2!.id);
    expect(ev1!.id).toBe("corr-99:market_signal");
    expect(ev2!.id).toBe("corr-99:pipeline_decision");
  });

  it("falls back to signal_id from payload when correlation_id absent", () => {
    const ev = toTraceEvent({
      type: "atlas.market_signal",
      payload: { signal_id: "sig-abc" },
    });
    expect(ev).not.toBeNull();
    expect(ev!.id).toBe("sig-abc:market_signal");
  });
});

describe("usePipelineStream — unknown event types", () => {
  it("unknown atlas.* type → null", () => {
    const ev = toTraceEvent({ type: "atlas.unknown_future_type", payload: {} });
    expect(ev).toBeNull();
  });

  it("non-atlas type with no agent → null", () => {
    const ev = toTraceEvent({ type: "system.ping", payload: {} });
    expect(ev).toBeNull();
  });
});
