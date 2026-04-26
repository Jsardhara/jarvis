"use client";

import { useMemo } from "react";

export type DispatchSnapshot = {
  request: string;
  primary: string | null;
  parallel: string[];
  ts: string;
} | null;

interface DispatchGraphProps {
  snapshot: DispatchSnapshot;
}

const NODE_W = 96;
const NODE_H = 28;

export function DispatchGraph({ snapshot }: DispatchGraphProps) {
  const layout = useMemo(() => {
    if (!snapshot) return null;
    const targets = [snapshot.primary, ...snapshot.parallel].filter(
      (n): n is string => Boolean(n)
    );
    const seen = new Set<string>();
    const ordered = targets.filter((t) => {
      if (seen.has(t)) return false;
      seen.add(t);
      return true;
    });
    return ordered;
  }, [snapshot]);

  if (!snapshot || !layout) {
    return (
      <div className="muted" style={{ padding: "1rem" }}>
        no dispatch yet — type a request below or click an agent
      </div>
    );
  }

  const userX = 12;
  const routerX = 160;
  const agentX = 320;
  const baseY = 40;
  const stepY = 44;
  const rows = layout.length;
  const totalH = baseY + Math.max(rows, 1) * stepY + 12;
  const routerY = baseY + ((rows - 1) * stepY) / 2;

  return (
    <svg
      className="graph-svg"
      viewBox={`0 0 ${agentX + NODE_W + 80} ${totalH}`}
      preserveAspectRatio="xMidYMid meet"
      key={snapshot.ts}
    >
      <Node x={userX} y={routerY} w={120} label="user" />
      <Edge from={[userX + 120, routerY + NODE_H / 2]} to={[routerX, routerY + NODE_H / 2]} primary />
      <Node x={routerX} y={routerY} w={104} label="router" />
      {layout.map((agent, i) => {
        const y = baseY + i * stepY;
        const isPrimary = agent === snapshot.primary;
        return (
          <g key={agent}>
            <Edge
              from={[routerX + 104, routerY + NODE_H / 2]}
              to={[agentX, y + NODE_H / 2]}
              primary={isPrimary}
            />
            <Node x={agentX} y={y} w={NODE_W} label={agent} primary={isPrimary} />
          </g>
        );
      })}
    </svg>
  );
}

function Node({
  x,
  y,
  w,
  label,
  primary,
}: {
  x: number;
  y: number;
  w: number;
  label: string;
  primary?: boolean;
}) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={NODE_H}
        rx={2}
        className={`node-bg ${primary ? "primary" : ""}`}
      />
      <text
        x={x + w / 2}
        y={y + NODE_H / 2 + 4}
        textAnchor="middle"
        className={`node-text ${primary ? "primary" : ""}`}
      >
        {label.toUpperCase()}
      </text>
    </g>
  );
}

function Edge({
  from,
  to,
  primary,
}: {
  from: [number, number];
  to: [number, number];
  primary?: boolean;
}) {
  const [x1, y1] = from;
  const [x2, y2] = to;
  const cx = (x1 + x2) / 2;
  const d = `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
  return <path d={d} className={`edge ${primary ? "primary" : ""}`} />;
}
