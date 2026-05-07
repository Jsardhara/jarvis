"use client";

/**
 * AgentWorkspaceShell
 *
 * Shared layout shell for all per-agent workspace pages.
 * Phase 3b pages pass their agent-specific widgets via the `widgets` prop.
 *
 * CSS grid layout:
 *   Row 1 (header): full width — AgentHeaderCard
 *   Row 2 (body):
 *     Left col (60%): AgentActivityStream — full remaining height
 *     Right col (40%):
 *       Top: AgentMemoryPanel
 *       Bottom: widgets slot (agent-specific content)
 *   Row 3 (footer): AgentChatPanel — sticky bottom
 *
 * Props:
 *   agentId       — Atlas agent ID (oracle / architect / guardian / trader / sage)
 *   displayName   — Human name shown in header
 *   accentColor   — Per-agent CSS color token or hex (optional, defaults to amber)
 *   widgets       — ReactNode rendered in the right-col bottom slot
 */

import { ReactNode } from "react";
import { useAgentDetail } from "@/hooks/useAgentDetail";
import { useAgentMemory } from "@/hooks/useAgentMemory";
import { AgentHeaderCard } from "./AgentHeaderCard";
import { AgentActivityStream } from "./AgentActivityStream";
import { AgentMemoryPanel } from "./AgentMemoryPanel";
import { AgentChatPanel } from "./AgentChatPanel";

// ─── Props ────────────────────────────────────────────────────────────────────

export interface AgentWorkspaceShellProps {
  agentId: string;
  displayName: string;
  accentColor?: string;
  widgets?: ReactNode;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentWorkspaceShell({
  agentId,
  displayName: _displayName,
  accentColor,
  widgets,
}: AgentWorkspaceShellProps) {
  const { detail, isLoading, error: detailError } = useAgentDetail(agentId);
  const { memory, isLoading: memLoading } = useAgentMemory(agentId);

  return (
    <div
      className="agent-workspace-shell"
      data-agent-id={agentId}
      style={{
        display: "grid",
        gridTemplateRows: "auto 1fr auto",
        gridTemplateColumns: "1fr",
        height: "100%",
        gap: 8,
        padding: 12,
        background: "var(--ops-bg-void)",
        overflow: "hidden",
      }}
    >
      {/* Header row */}
      <div className="agent-workspace-header">
        {detailError && (
          <div
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 10,
              color: "var(--ops-crit)",
              padding: "4px 0",
            }}
          >
            Error loading agent: {detailError.message}
          </div>
        )}
        <AgentHeaderCard
          detail={detail}
          isLoading={isLoading}
          accentColor={accentColor}
        />
      </div>

      {/* Body row: left activity | right (memory + widgets) */}
      <div
        className="agent-workspace-body"
        style={{
          display: "grid",
          gridTemplateColumns: "60% 40%",
          gap: 8,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        {/* Left: activity stream */}
        <div
          className="agent-workspace-activity"
          style={{ minHeight: 0, overflow: "hidden" }}
        >
          <AgentActivityStream events={detail?.recent_activity ?? []} />
        </div>

        {/* Right col: memory + widgets */}
        <div
          className="agent-workspace-right"
          style={{
            display: "grid",
            gridTemplateRows: "1fr 1fr",
            gap: 8,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          {/* Memory panel */}
          <div style={{ minHeight: 0, overflow: "hidden" }}>
            <AgentMemoryPanel memory={memory} isLoading={memLoading} />
          </div>

          {/* Agent-specific widgets slot */}
          <div
            className="agent-workspace-widgets"
            style={{ minHeight: 0, overflow: "auto" }}
          >
            {widgets ?? (
              <div
                style={{
                  height: "100%",
                  border: "1px dashed var(--ops-line-strong)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontFamily: "var(--ops-mono)",
                  fontSize: 10,
                  color: "var(--ops-fg-faint)",
                  letterSpacing: "0.1em",
                }}
              >
                AGENT WIDGETS
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer: chat panel */}
      <div className="agent-workspace-chat">
        <AgentChatPanel agentId={agentId} accentColor={accentColor} />
      </div>
    </div>
  );
}
