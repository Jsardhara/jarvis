"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import type { InboxEvent } from "@/hooks/useInboxStream";

interface DispatchGraphProps {
  events: InboxEvent[];
}

const AGENTS = ["tempo", "scholar", "lens", "forge", "atlas", "sentinel"] as const;
type Agent = (typeof AGENTS)[number];

const HUE: Record<Agent, string> = {
  tempo: "var(--ops-agent-tempo)",
  scholar: "var(--ops-agent-scholar)",
  lens: "var(--ops-agent-lens)",
  forge: "var(--ops-agent-forge)",
  atlas: "var(--ops-agent-atlas)",
  sentinel: "var(--ops-agent-sentinel)",
};

const RADIUS = 180;
const CENTER = { x: 240, y: 200 };

interface NodePos {
  agent: Agent;
  x: number;
  y: number;
}

function nodePositions(): NodePos[] {
  return AGENTS.map((agent, i) => {
    const angle = (Math.PI * 2 * i) / AGENTS.length - Math.PI / 2;
    return {
      agent,
      x: CENTER.x + Math.cos(angle) * RADIUS,
      y: CENTER.y + Math.sin(angle) * RADIUS,
    };
  });
}

interface ActiveEdge {
  id: string;
  agent: Agent;
  state: "fire" | "settle" | "error";
}

const FIRE_DURATION_MS = 220;
const SETTLE_DURATION_MS = 1_400;

export function DispatchGraph({ events }: DispatchGraphProps) {
  const positions = useMemo(nodePositions, []);
  const [active, setActive] = useState<ActiveEdge[]>([]);

  useEffect(() => {
    if (!events.length) return;
    const last = events[events.length - 1];
    const agent = (last.agent ?? "") as Agent;
    if (!AGENTS.includes(agent)) return;
    const sev = (last.payload?.["severity"] as string) ?? "info";
    const state: ActiveEdge["state"] = sev === "alert" ? "error" : "fire";
    const id = `${agent}-${last.ts ?? Date.now()}-${Math.random()}`;
    setActive((prev) => [...prev, { id, agent, state }]);
    const settleTimer = setTimeout(() => {
      setActive((prev) =>
        prev.map((e) =>
          e.id === id && e.state === "fire" ? { ...e, state: "settle" } : e
        )
      );
    }, FIRE_DURATION_MS);
    const removeTimer = setTimeout(() => {
      setActive((prev) => prev.filter((e) => e.id !== id));
    }, FIRE_DURATION_MS + SETTLE_DURATION_MS);
    return () => {
      clearTimeout(settleTimer);
      clearTimeout(removeTimer);
    };
  }, [events]);

  return (
    <div className="ops-panel relative h-[400px] w-full overflow-hidden">
      <svg
        viewBox="0 0 480 400"
        className="absolute inset-0 h-full w-full"
        aria-label="Dispatch graph"
      >
        {/* Static idle edges */}
        {positions.map((p) => (
          <line
            key={`idle-${p.agent}`}
            x1={CENTER.x}
            y1={CENTER.y}
            x2={p.x}
            y2={p.y}
            stroke="var(--ops-line-faint)"
            strokeWidth={1}
          />
        ))}

        {/* Live fanout edges */}
        <AnimatePresence>
          {active.map((edge) => {
            const p = positions.find((n) => n.agent === edge.agent)!;
            const stroke =
              edge.state === "error" ? "var(--ops-crit)" : HUE[edge.agent];
            return (
              <motion.line
                key={edge.id}
                x1={CENTER.x}
                y1={CENTER.y}
                x2={p.x}
                y2={p.y}
                stroke={stroke}
                strokeWidth={2}
                initial={{ pathLength: 0, opacity: 0.2 }}
                animate={{
                  pathLength: 1,
                  opacity: edge.state === "settle" ? 0.45 : 1,
                }}
                exit={{ opacity: 0 }}
                transition={{
                  pathLength: { duration: FIRE_DURATION_MS / 1000 },
                  opacity: { duration: 0.3 },
                }}
              />
            );
          })}
        </AnimatePresence>

        {/* Orchestrator center */}
        <circle
          cx={CENTER.x}
          cy={CENTER.y}
          r={26}
          fill="var(--ops-bg-elevated)"
          stroke="var(--ops-amber)"
          strokeWidth={1.5}
        />
        <text
          x={CENTER.x}
          y={CENTER.y + 4}
          textAnchor="middle"
          fontFamily="var(--ops-mono)"
          fontSize={10}
          fill="var(--ops-amber)"
        >
          JARVIS
        </text>

        {/* Agent nodes */}
        {positions.map((p) => (
          <g key={p.agent}>
            <circle
              cx={p.x}
              cy={p.y}
              r={20}
              fill="var(--ops-bg-elevated)"
              stroke={HUE[p.agent]}
              strokeWidth={1}
            />
            <text
              x={p.x}
              y={p.y + 3}
              textAnchor="middle"
              fontFamily="var(--ops-mono)"
              fontSize={9}
              fill={HUE[p.agent]}
              style={{ textTransform: "uppercase" }}
            >
              {p.agent}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
