"use client";

/**
 * /atlas/network — Agent Communication Graph
 *
 * Live view of message flow between Atlas sub-agents.
 * Layout: toolbar (top) → graph (fills viewport) → inspector drawer (overlay).
 *
 * Wires useAtlasNetwork → AgentNetworkGraph + AgentInspectorDrawer.
 */

import { CSSProperties, useState, useCallback } from "react";
import { useAtlasNetwork } from "@/hooks/useAtlasNetwork";
import type { MessageKind, KindFilter } from "@/hooks/useAtlasNetwork";
import { AgentNetworkGraph } from "@/components/atlas/network/AgentNetworkGraph";
import { AgentInspectorDrawer } from "@/components/atlas/network/AgentInspectorDrawer";
// MockModeBanner is mounted globally in LayoutShell — see web/src/components/layout-shell.tsx.
import { Dot } from "@/components/ops/Dot";

// ─── Kind filter chips ────────────────────────────────────────────────────────

const ALL_KINDS: MessageKind[] = ["signal", "decision", "order", "insight", "status", "other"];

const KIND_LABELS: Record<MessageKind, string> = {
  signal:   "SIGNAL",
  decision: "DECISION",
  order:    "ORDER",
  insight:  "INSIGHT",
  status:   "STATUS",
  other:    "OTHER",
};

const KIND_COLORS: Record<MessageKind, string> = {
  signal:   "var(--atlas-kind-signal)",
  decision: "var(--atlas-kind-decision)",
  order:    "var(--atlas-kind-order)",
  insight:  "var(--atlas-kind-insight)",
  status:   "var(--atlas-kind-status)",
  other:    "var(--atlas-kind-other)",
};

// ─── Toolbar ──────────────────────────────────────────────────────────────────

interface ToolbarProps {
  paused: boolean;
  onTogglePause: () => void;
  kindFilter: KindFilter;
  onToggleKind: (kind: MessageKind) => void;
  messageCount: number;
}

function NetworkToolbar({
  paused,
  onTogglePause,
  kindFilter,
  onToggleKind,
  messageCount,
}: ToolbarProps) {
  return (
    <div className="atlas-network-toolbar">
      {/* Pause/Resume */}
      <button
        type="button"
        onClick={onTogglePause}
        className={`ops-btn ${paused ? "ops-btn-primary" : ""}`}
        aria-pressed={paused}
        style={{ flexShrink: 0 } as CSSProperties}
      >
        <Dot kind={paused ? "warn" : "ok"} pulse={!paused} />
        {paused ? "RESUME" : "PAUSE"}
      </button>

      {/* Separator */}
      <div
        style={{
          width: 1,
          height: 18,
          background: "var(--ops-line-strong)",
          flexShrink: 0,
        } as CSSProperties}
      />

      {/* ALL toggle */}
      <button
        type="button"
        onClick={() => {
          const allActive = ALL_KINDS.every((k) => kindFilter.has(k));
          // If all active, deactivate all; if any inactive, activate all
          for (const k of ALL_KINDS) {
            if (allActive ? kindFilter.has(k) : !kindFilter.has(k)) {
              onToggleKind(k);
            }
          }
        }}
        className={`atlas-kind-chip ${ALL_KINDS.every((k) => kindFilter.has(k)) ? "atlas-kind-chip-active" : ""}`}
      >
        ALL
      </button>

      {/* Per-kind chips */}
      {ALL_KINDS.map((kind) => (
        <button
          key={kind}
          type="button"
          onClick={() => onToggleKind(kind)}
          className={`atlas-kind-chip ${kindFilter.has(kind) ? "atlas-kind-chip-active" : ""}`}
          style={{
            borderColor: kindFilter.has(kind) ? KIND_COLORS[kind] : undefined,
            color: kindFilter.has(kind) ? KIND_COLORS[kind] : undefined,
          } as CSSProperties}
        >
          {KIND_LABELS[kind]}
        </button>
      ))}

      {/* Message counter */}
      <div
        style={{
          marginLeft: "auto",
          fontFamily: "var(--ops-mono)",
          fontSize: 10,
          color: "var(--ops-fg-dim)",
          letterSpacing: "0.08em",
          flexShrink: 0,
        } as CSSProperties}
      >
        <span style={{ color: "var(--ops-fg-mute)", fontVariantNumeric: "tabular-nums" }}>
          {messageCount}
        </span>
        {" MSG / 60s"}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AtlasNetworkPage() {
  const { inFlight, agentStates, paused, kindFilter, setPaused, setKindFilter } =
    useAtlasNetwork();

  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const handleTogglePause = useCallback(() => {
    setPaused(!paused);
  }, [paused, setPaused]);

  const handleToggleKind = useCallback(
    (kind: MessageKind) => {
      const next = new Set(kindFilter);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
      }
      setKindFilter(next);
    },
    [kindFilter, setKindFilter]
  );

  const handleSelectAgent = useCallback((agentId: string | null) => {
    setSelectedAgent(agentId);
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setSelectedAgent(null);
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
        position: "relative",
        overflow: "hidden",
      } as CSSProperties}
    >
      {/* ── Toolbar ────────────────────────────────────────────────────── */}
      <NetworkToolbar
        paused={paused}
        onTogglePause={handleTogglePause}
        kindFilter={kindFilter}
        onToggleKind={handleToggleKind}
        messageCount={inFlight.length}
      />

      {/* ── Graph ──────────────────────────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          position: "relative",
          overflow: "hidden",
        } as CSSProperties}
      >
        <AgentNetworkGraph
          inFlight={inFlight}
          agentStates={agentStates}
          selectedAgent={selectedAgent}
          onSelectAgent={handleSelectAgent}
        />

        {/* ── Inspector drawer (overlay) ──────────────────────────────── */}
        <AgentInspectorDrawer
          agentId={selectedAgent}
          onClose={handleCloseDrawer}
        />
      </div>
    </div>
  );
}
