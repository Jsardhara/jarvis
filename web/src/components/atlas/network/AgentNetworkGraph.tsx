"use client";

/**
 * AgentNetworkGraph
 *
 * Hand-rolled SVG network graph — 8 fixed nodes (5 sub-agents + orchestrator
 * + external Kraken + Postgres). In-flight messages animate as packets along
 * precomputed straight-line edges via <animateMotion>. Node click fires
 * onSelectAgent(agentId); selected node gets a thicker ring + glow.
 *
 * Color coding:
 *   signal=gold, decision=blue, order=green, insight=violet,
 *   status=grey, other=faint
 *
 * No framer-motion — CSS keyframe atlas-packet-fade + SVG animateMotion only.
 */

import { CSSProperties, memo } from "react";
import type { InFlightMessage, AgentName, AgentStates } from "@/hooks/useAtlasNetwork";
import {
  W, H,
  NODE_POSITIONS, NODE_META, EDGES,
  edgeKey, buildPath, kindColor, stateDotColor,
} from "./graph-data";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentNetworkGraphProps {
  inFlight: InFlightMessage[];
  agentStates: AgentStates;
  selectedAgent: string | null;
  onSelectAgent: (agentId: string | null) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export const AgentNetworkGraph = memo(function AgentNetworkGraph({
  inFlight,
  agentStates,
  selectedAgent,
  onSelectAgent,
}: AgentNetworkGraphProps) {
  const edgeSet = new Set(EDGES.map((e) => edgeKey(e.source, e.target)));

  return (
    <div className="atlas-network-graph" aria-label="Atlas agent communication graph">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height="100%"
        style={{ display: "block" } as CSSProperties}
        aria-hidden="true"
      >
        <defs>
          <pattern id="ng-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="0.5" />
          </pattern>
          <filter id="ng-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <rect width={W} height={H} fill="url(#ng-grid)" />

        {/* ── Edges ─────────────────────────────────────────────────────── */}
        {EDGES.map((edge) => {
          const s = NODE_POSITIONS[edge.source];
          const t = NODE_POSITIONS[edge.target];
          if (!s || !t) return null;
          const key = edgeKey(edge.source, edge.target);
          const active = inFlight.some(
            (m) => edgeKey(m.source, m.target) === key
          );
          return (
            <line
              key={key}
              x1={s.x} y1={s.y} x2={t.x} y2={t.y}
              stroke="var(--ops-line-bright)"
              strokeWidth={active ? 1.5 : 1}
              strokeDasharray={active ? "none" : "4 4"}
              opacity={active ? 0.55 : 0.25}
              style={{ transition: "opacity 300ms, stroke-width 300ms" } as CSSProperties}
            />
          );
        })}

        {/* ── In-flight packets ──────────────────────────────────────────── */}
        {inFlight.map((msg) => {
          const path = buildPath(msg.source, msg.target);
          if (!path) return null;
          return (
            <g key={msg.id} filter="url(#ng-glow)">
              <circle
                r={5}
                fill={kindColor(msg.kind)}
                opacity={0}
                style={{ animation: "atlas-packet-fade var(--atlas-packet-dur) ease-in-out both" } as CSSProperties}
              >
                <animateMotion dur="var(--atlas-packet-dur)" fill="freeze" path={path} />
              </circle>
            </g>
          );
        })}

        {/* ── Nodes ─────────────────────────────────────────────────────── */}
        {(Object.keys(NODE_POSITIONS) as AgentName[]).map((agentId) => {
          const pos = NODE_POSITIONS[agentId];
          const meta = NODE_META[agentId];
          if (!pos || !meta) return null;

          const isSelected = selectedAgent === agentId;
          const dotColor = stateDotColor(agentStates[agentId]);
          const ringWidth = isSelected ? 3 : 1.5;
          const isExternal = agentId === "kraken" || agentId === "postgres";

          return (
            <g
              key={agentId}
              role="button"
              tabIndex={0}
              aria-label={`${meta.label} node`}
              aria-pressed={isSelected}
              style={{ cursor: "pointer" } as CSSProperties}
              onClick={() => onSelectAgent(isSelected ? null : agentId)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onSelectAgent(isSelected ? null : agentId);
              }}
            >
              {isSelected && (
                <circle cx={pos.x} cy={pos.y} r={meta.r + 8} fill="none" stroke={meta.color} strokeWidth={1} opacity={0.3} />
              )}
              <circle
                cx={pos.x} cy={pos.y} r={meta.r}
                fill="var(--ops-bg-panel)"
                stroke={meta.color}
                strokeWidth={ringWidth}
                opacity={isExternal ? 0.7 : 1}
              />
              <text
                x={pos.x} y={pos.y + 1}
                textAnchor="middle" dominantBaseline="middle"
                fill={meta.color} fontSize={8} fontFamily="var(--ops-mono)"
                letterSpacing="0.06em" fontWeight="700"
                style={{ pointerEvents: "none" } as CSSProperties}
              >
                {meta.label.slice(0, 5)}
              </text>
              <text
                x={pos.x} y={pos.y + meta.r + 12}
                textAnchor="middle" dominantBaseline="middle"
                fill="var(--ops-fg-dim)" fontSize={9} fontFamily="var(--ops-mono)"
                letterSpacing="0.08em"
                style={{ pointerEvents: "none" } as CSSProperties}
              >
                {meta.label}
              </text>
              <circle cx={pos.x + meta.r - 4} cy={pos.y - meta.r + 4} r={4} fill={dotColor} />
            </g>
          );
        })}
      </svg>
    </div>
  );
});
