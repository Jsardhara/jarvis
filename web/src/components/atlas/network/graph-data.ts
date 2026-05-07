/**
 * Static graph layout data for AgentNetworkGraph.
 * Extracted to keep the component file under 300 lines.
 */

import type { AgentName } from "@/hooks/useAtlasNetwork";

// ─── Canvas ───────────────────────────────────────────────────────────────────

export const W = 700;
export const H = 520;
export const CX = 350;
export const CY = 240;
export const R = 170;

// ─── Pentagon math ────────────────────────────────────────────────────────────

const toRad = (deg: number) => (deg * Math.PI) / 180;

function pt(angle: number): { x: number; y: number } {
  return {
    x: Math.round(CX + R * Math.cos(toRad(angle))),
    y: Math.round(CY + R * Math.sin(toRad(angle))),
  };
}

// ─── Node positions ───────────────────────────────────────────────────────────

export const NODE_POSITIONS: Record<AgentName, { x: number; y: number }> = {
  oracle:       pt(-90),           // top
  architect:    pt(-90 + 72),      // top-right
  trader:       pt(-90 + 144),     // bottom-right
  sage:         pt(-90 + 216),     // bottom-left
  guardian:     pt(-90 + 288),     // top-left
  orchestrator: { x: CX, y: CY }, // center
  kraken:       { x: W - 65, y: 70 },   // top-right external
  postgres:     { x: CX, y: H - 42 },   // bottom external
};

// ─── Node display metadata ────────────────────────────────────────────────────

export interface NodeMeta {
  label: string;
  color: string;
  r: number;
}

export const NODE_META: Record<AgentName, NodeMeta> = {
  oracle:       { label: "ORACLE",    color: "var(--atlas-oracle)",       r: 28 },
  architect:    { label: "ARCHITECT", color: "var(--atlas-architect)",    r: 28 },
  guardian:     { label: "GUARDIAN",  color: "var(--atlas-guardian)",     r: 28 },
  trader:       { label: "TRADER",    color: "var(--atlas-trader)",       r: 28 },
  sage:         { label: "SAGE",      color: "var(--atlas-sage)",         r: 28 },
  orchestrator: { label: "ORCH",      color: "var(--atlas-orchestrator)", r: 32 },
  kraken:       { label: "KRAKEN",    color: "var(--atlas-kraken)",       r: 22 },
  postgres:     { label: "POSTGRES",  color: "var(--atlas-postgres)",     r: 22 },
};

// ─── Edges ────────────────────────────────────────────────────────────────────

export interface Edge {
  source: AgentName;
  target: AgentName;
}

export const EDGES: Edge[] = [
  { source: "oracle",       target: "orchestrator" },
  { source: "architect",    target: "orchestrator" },
  { source: "guardian",     target: "orchestrator" },
  { source: "trader",       target: "orchestrator" },
  { source: "sage",         target: "orchestrator" },
  { source: "oracle",       target: "guardian"     },
  { source: "guardian",     target: "trader"       },
  { source: "trader",       target: "sage"         },
  { source: "trader",       target: "kraken"       },
  { source: "oracle",       target: "kraken"       },
  { source: "oracle",       target: "postgres"     },
  { source: "architect",    target: "postgres"     },
  { source: "guardian",     target: "postgres"     },
  { source: "trader",       target: "postgres"     },
  { source: "sage",         target: "postgres"     },
  { source: "orchestrator", target: "postgres"     },
];

// ─── Utilities ────────────────────────────────────────────────────────────────

export function edgeKey(a: AgentName, b: AgentName): string {
  return [a, b].sort().join("|");
}

export function buildPath(src: AgentName, tgt: AgentName): string {
  const s = NODE_POSITIONS[src];
  const t = NODE_POSITIONS[tgt];
  if (!s || !t) return "";
  return `M ${s.x} ${s.y} L ${t.x} ${t.y}`;
}

export type MessageKind = "signal" | "decision" | "order" | "insight" | "status" | "other";

export function kindColor(kind: MessageKind): string {
  switch (kind) {
    case "signal":   return "var(--atlas-kind-signal)";
    case "decision": return "var(--atlas-kind-decision)";
    case "order":    return "var(--atlas-kind-order)";
    case "insight":  return "var(--atlas-kind-insight)";
    case "status":   return "var(--atlas-kind-status)";
    default:         return "var(--atlas-kind-other)";
  }
}

import type { AgentRunState } from "@/hooks/useAtlasNetwork";

export function stateDotColor(state: AgentRunState | undefined): string {
  if (!state || state === "unknown") return "var(--ops-fg-faint)";
  if (state === "running") return "var(--ops-ok)";
  if (state === "stale")   return "var(--ops-warn)";
  return "var(--ops-crit)";
}
