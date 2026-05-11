"use client";

import { motion } from "framer-motion";

/**
 * 3-tier hierarchical architecture diagram of the Jarvis fleet.
 *
 *   TIER 0  master orchestrator     [JARVIS]
 *   TIER 1  routing + research      [FORGE] [ATLAS] [SCHOLAR] [LENS]
 *   TIER 2  execution + utility     [TEMPO] [ORACLE] [GUARDIAN] [TRADER] [SAGE] [SENTINEL]
 *
 * 1px cyan right-angle connectors (no diagonals).
 */
export function ArchitectureTree() {
  return (
    <div className="relative flex h-[calc(100vh-44px)] flex-col gap-3 overflow-hidden p-4">
      <div aria-hidden className="hud-scan-line" />

      <header className="flex items-center justify-between border-b border-[var(--ops-line-faint)] pb-2">
        <div className="flex items-center gap-3">
          <span
            className="hud-display hud-text-glow"
            style={{ color: "var(--hud-cyan)", fontSize: 14 }}
          >
            JARVIS // FLEET ARCHITECTURE
          </span>
          <span
            className="font-mono text-[9px] tracking-widest"
            style={{ color: "var(--ops-fg-faint)" }}
          >
            3-TIER · OPUS / SONNET / HAIKU
          </span>
        </div>
        <span className="hud-pill" style={{ color: "var(--ops-ok)" }}>
          ALL NODES UP
        </span>
      </header>

      <div className="relative flex-1 overflow-auto">
        <div className="grid min-h-full grid-rows-[auto_auto_auto_auto_auto] gap-12 px-8 pt-4">
          {/* Tier label row */}
          <TierLabel
            tier="TIER 0"
            label="MASTER ORCHESTRATOR"
            sub="Routes intent to subsystems · Confirms gates"
          />

          {/* Orchestrator node */}
          <div className="flex justify-center">
            <Node
              id="jarvis"
              name="JARVIS"
              role="ORCHESTRATOR"
              tasks={[
                "intent routing",
                "confirm gates",
                "memory + persona",
                "voice + chat brain",
              ]}
              accent="var(--hud-cyan)"
              highlight
              wide
            />
          </div>

          {/* Connector down + tier 1 */}
          <Connector targets={4} />

          <TierLabel
            tier="TIER 1"
            label="STRATEGY LAYER"
            sub="Owns the work · Sonnet-class"
          />
          <div className="grid grid-cols-4 gap-4">
            {TIER1.map((n) => (
              <Node key={n.id} {...n} />
            ))}
          </div>

          {/* Connector + tier 2 */}
          <Connector targets={6} />

          <TierLabel
            tier="TIER 2"
            label="EXECUTION LAYER"
            sub="High-frequency utility · Haiku + Atlas internals"
          />
          <div className="grid grid-cols-6 gap-3">
            {TIER2.map((n) => (
              <Node key={n.id} {...n} compact />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Data ────────────────────────────────────────────────────────────────────

interface NodeData {
  id: string;
  name: string;
  role: string;
  tasks: string[];
  accent: string;
  highlight?: boolean;
  wide?: boolean;
  compact?: boolean;
  status?: "online" | "pending" | "offline";
}

const TIER1: NodeData[] = [
  {
    id: "forge",
    name: "FORGE",
    role: "CODE WORK",
    tasks: ["plan + TDD", "code review", "open PRs"],
    accent: "var(--ops-agent-forge)",
    status: "online",
  },
  {
    id: "atlas",
    name: "ATLAS",
    role: "TRADING",
    tasks: ["scan + rank", "guardian veto", "alpaca exec"],
    accent: "var(--ops-agent-atlas)",
    status: "online",
  },
  {
    id: "scholar",
    name: "SCHOLAR",
    role: "ACADEMICS",
    tasks: ["assignments", "study plans", "summarize"],
    accent: "var(--ops-agent-scholar)",
    status: "online",
  },
  {
    id: "lens",
    name: "LENS",
    role: "RESEARCH",
    tasks: ["web search", "monitor", "synthesize"],
    accent: "var(--ops-agent-lens)",
    status: "online",
  },
];

const TIER2: NodeData[] = [
  {
    id: "tempo",
    name: "TEMPO",
    role: "MAIL+CAL",
    tasks: ["mail", "calendar", "tasks"],
    accent: "var(--ops-agent-tempo)",
    status: "online",
  },
  {
    id: "oracle",
    name: "ORACLE",
    role: "ATLAS·SCAN",
    tasks: ["market scan"],
    accent: "var(--hud-cyan)",
    status: "online",
  },
  {
    id: "architect",
    name: "ARCHITECT",
    role: "ATLAS·RANK",
    tasks: ["rank candidates"],
    accent: "var(--hud-cyan)",
    status: "online",
  },
  {
    id: "guardian",
    name: "GUARDIAN",
    role: "ATLAS·RISK",
    tasks: ["risk veto"],
    accent: "var(--ops-warn)",
    status: "online",
  },
  {
    id: "trader",
    name: "TRADER",
    role: "ATLAS·EXEC",
    tasks: ["alpaca order"],
    accent: "var(--ops-ok)",
    status: "online",
  },
  {
    id: "sentinel",
    name: "SENTINEL",
    role: "DAEMON",
    tasks: ["heartbeat", "alerts"],
    accent: "var(--ops-agent-sentinel)",
    status: "online",
  },
];

// ─── Subcomponents ───────────────────────────────────────────────────────────

function TierLabel({
  tier,
  label,
  sub,
}: {
  tier: string;
  label: string;
  sub?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="hud-pill"
        style={{
          color: "var(--hud-cyan)",
          background: "rgba(0, 229, 255, 0.10)",
        }}
      >
        {tier}
      </span>
      <span className="hud-display" style={{ color: "var(--hud-cyan-bright)", fontSize: 12 }}>
        {label}
      </span>
      {sub && (
        <span
          className="font-mono text-[9px] tracking-widest"
          style={{ color: "var(--ops-fg-faint)" }}
        >
          {sub}
        </span>
      )}
      <div className="h-px flex-1 bg-[var(--ops-line)]" />
    </div>
  );
}

function Connector({ targets }: { targets: number }) {
  return (
    <div className="relative flex h-12 items-center justify-center">
      <svg
        aria-hidden
        viewBox="0 0 1000 60"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
      >
        {/* Vertical from parent */}
        <line
          x1="500"
          y1="0"
          x2="500"
          y2="30"
          stroke="var(--hud-cyan)"
          strokeWidth="0.8"
          opacity="0.7"
        />
        {/* Horizontal trunk */}
        <line
          x1={500 - (targets - 1) * 80}
          y1="30"
          x2={500 + (targets - 1) * 80}
          y2="30"
          stroke="var(--hud-cyan)"
          strokeWidth="0.8"
          opacity="0.7"
        />
        {/* Drops to children */}
        {Array.from({ length: targets }).map((_, i) => {
          const x = 500 + (i - (targets - 1) / 2) * 160;
          return (
            <line
              key={i}
              x1={x}
              y1="30"
              x2={x}
              y2="60"
              stroke="var(--hud-cyan)"
              strokeWidth="0.8"
              opacity="0.7"
            />
          );
        })}
      </svg>
    </div>
  );
}

function Node({
  name,
  role,
  tasks,
  accent,
  highlight,
  wide,
  compact,
  status = "online",
}: NodeData) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className={`hud-panel hud-corners flex flex-col gap-1.5 px-3 py-2 ${
        highlight ? "hud-panel-active" : ""
      } ${wide ? "min-w-[280px]" : ""}`}
      style={{
        borderColor: highlight ? "var(--hud-cyan)" : undefined,
        boxShadow: highlight
          ? "0 0 18px rgba(0, 229, 255, 0.40)"
          : undefined,
      }}
    >
      {/* Header strip */}
      <div
        className="-mx-3 -mt-2 mb-1 flex items-center justify-between px-3 py-1"
        style={{
          background: highlight
            ? "rgba(0, 229, 255, 0.16)"
            : `linear-gradient(90deg, ${accent}26, transparent)`,
        }}
      >
        <span
          className="hud-display"
          style={{ color: accent, fontSize: compact ? 9 : 11 }}
        >
          {name}
        </span>
        <span
          className="font-mono text-[8px] uppercase tracking-widest"
          style={{ color: "var(--ops-fg-mute)" }}
        >
          {role}
        </span>
      </div>

      {/* Tasks */}
      <ul className="flex flex-col gap-0.5">
        {tasks.slice(0, compact ? 1 : 4).map((t, i) => (
          <li
            key={i}
            className="truncate font-mono text-[8.5px] leading-snug text-[var(--ops-fg-mute)]"
          >
            <span className="mr-1" style={{ color: accent }}>›</span>
            {t}
          </li>
        ))}
      </ul>

      {/* Status footer */}
      <div className="flex items-center justify-between pt-0.5">
        <div className="hud-bar-track flex-1">
          <div
            className="hud-bar-fill"
            style={{
              width: status === "online" ? "100%" : "30%",
              background: accent,
              boxShadow: `0 0 6px ${accent}80`,
            }}
          />
        </div>
        <span
          className="hud-pill ml-2"
          style={{
            color: status === "online" ? "var(--ops-ok)" : "var(--ops-warn)",
          }}
        >
          {status === "online" ? "UP" : "STBY"}
        </span>
      </div>
    </motion.div>
  );
}
