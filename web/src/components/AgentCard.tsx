"use client";

import type { AgentDescriptor } from "@/lib/api";

export type AgentRuntimeState = {
  status: "idle" | "running" | "done" | "error" | "warn";
  action: string;
  confidence: number;
  lastTs?: string;
};

interface AgentCardProps {
  descriptor: AgentDescriptor;
  state: AgentRuntimeState;
  onOpen: (name: string) => void;
}

const CONF_DOTS = 5;

export function AgentCard({ descriptor, state, onOpen }: AgentCardProps) {
  const filled = Math.round(state.confidence * CONF_DOTS);
  return (
    <button
      type="button"
      className="agent-card"
      data-status={state.status}
      onClick={() => onOpen(descriptor.name)}
    >
      <span className="dot" data-status={state.status} />
      <div style={{ minWidth: 0 }}>
        <div className="a-name">{descriptor.name}</div>
        <div className="a-action">{state.action || descriptor.description}</div>
      </div>
      <div className="a-meta">
        <div className="conf-dots" aria-label={`confidence ${filled}/${CONF_DOTS}`}>
          {Array.from({ length: CONF_DOTS }).map((_, i) => (
            <span key={i} data-on={i < filled ? "1" : "0"} />
          ))}
        </div>
      </div>
    </button>
  );
}
