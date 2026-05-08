"use client";

import Link from "next/link";
import { CornerTicks } from "@/components/ops/CornerTicks";
import { Dot } from "@/components/ops/Dot";
import { cn } from "@/lib/utils";

type AgentStatus = "idle" | "active" | "error";

export interface AgentFleetCardProps {
  /** Agent slug — drives identity hue + deep-link target. */
  slug: "tempo" | "scholar" | "lens" | "forge" | "atlas" | "sentinel";
  label: string;
  status: AgentStatus;
  /** Last-hour dispatch counts; max 24 entries. */
  sparkline: number[];
  /** Median latency over recent dispatches (ms). */
  latencyMs: number;
  /** Open queue / in-flight task count. */
  queueDepth?: number;
}

const HUE: Record<AgentFleetCardProps["slug"], string> = {
  tempo: "var(--ops-agent-tempo)",
  scholar: "var(--ops-agent-scholar)",
  lens: "var(--ops-agent-lens)",
  forge: "var(--ops-agent-forge)",
  atlas: "var(--ops-agent-atlas)",
  sentinel: "var(--ops-agent-sentinel)",
};

const HREF: Record<AgentFleetCardProps["slug"], string> = {
  tempo: "/tempo",
  scholar: "/scholar",
  lens: "/lens",
  forge: "/forge",
  atlas: "/atlas",
  sentinel: "/sentinel",
};

function statusKind(status: AgentStatus): "ok" | "crit" | "idle" {
  if (status === "error") return "crit";
  if (status === "active") return "ok";
  return "idle";
}

export function AgentFleetCard({
  slug,
  label,
  status,
  sparkline,
  latencyMs,
  queueDepth = 0,
}: AgentFleetCardProps) {
  const hue = HUE[slug];
  const max = Math.max(1, ...sparkline);
  const padded = sparkline.slice(-24);
  while (padded.length < 24) padded.unshift(0);

  return (
    <Link
      href={HREF[slug]}
      className={cn(
        "ops-panel relative flex flex-col gap-2 px-3 py-2.5",
        "transition-colors hover:bg-[var(--ops-bg-elevated)]"
      )}
      style={{ borderLeftColor: hue, borderLeftWidth: "2px" }}
    >
      <CornerTicks />
      <header className="flex items-center justify-between text-[11px] tracking-wide">
        <span className="font-mono uppercase" style={{ color: hue }}>
          {label}
        </span>
        <Dot kind={statusKind(status)} pulse={status === "active"} />
      </header>

      <svg
        viewBox="0 0 96 24"
        preserveAspectRatio="none"
        className="h-6 w-full"
        aria-hidden
      >
        {padded.map((v, i) => {
          const h = Math.max(1, (v / max) * 22);
          return (
            <rect
              key={i}
              x={i * 4}
              y={24 - h}
              width={3}
              height={h}
              fill={hue}
              opacity={status === "idle" ? 0.55 : 0.95}
            />
          );
        })}
      </svg>

      <footer className="grid grid-cols-2 gap-x-2 text-[10px] text-[var(--ops-fg-dim)]">
        <span className="font-mono">queue {queueDepth}</span>
        <span className="font-mono text-right">{latencyMs}ms</span>
      </footer>
    </Link>
  );
}
