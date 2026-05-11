"use client";

import { motion } from "framer-motion";

type AgentStatus = "online" | "pending" | "offline" | "error";

export interface AgentCard {
  id: string;
  name: string;
  status: AgentStatus;
  tasks: string[];
  progress?: number; // 0-100
  accent?: string;   // CSS color, falls back to cyan
}

interface AgentCardRowProps {
  agents: AgentCard[];
  active?: string;
}

const STATUS_PILL: Record<AgentStatus, { color: string; label: string }> = {
  online:  { color: "var(--ops-ok)",   label: "ONLINE"  },
  pending: { color: "var(--ops-crit)", label: "PENDING" },
  offline: { color: "var(--ops-fg-faint)", label: "OFFLINE" },
  error:   { color: "var(--ops-crit)", label: "ERROR" },
};

export function AgentCardRow({ agents, active }: AgentCardRowProps) {
  return (
    <div className="grid grid-flow-col auto-cols-fr gap-3">
      {agents.map((a) => (
        <AgentCardItem key={a.id} agent={a} active={active === a.id} />
      ))}
    </div>
  );
}

function AgentCardItem({ agent, active }: { agent: AgentCard; active: boolean }) {
  const pill = STATUS_PILL[agent.status];
  const accent = agent.accent ?? "var(--hud-cyan)";

  return (
    <motion.div
      className={`hud-panel hud-corners relative flex flex-col gap-2 px-3 py-2.5 ${
        active ? "hud-panel-active" : ""
      }`}
      animate={
        active
          ? {
              boxShadow: [
                "0 0 6px rgba(0, 229, 255, 0.30)",
                "0 0 14px rgba(0, 229, 255, 0.55)",
                "0 0 6px rgba(0, 229, 255, 0.30)",
              ],
            }
          : { boxShadow: "0 0 0 rgba(0,0,0,0)" }
      }
      transition={{
        duration: 1.6,
        repeat: active ? Infinity : 0,
        ease: "easeInOut",
      }}
      style={{ minHeight: 100 }}
    >
      {/* Header — name + status pill */}
      <div className="flex items-center justify-between">
        <span
          className="hud-display"
          style={{ color: accent, fontSize: 11 }}
        >
          {agent.name.toUpperCase()}
        </span>
        <span
          className="hud-pill"
          style={{ color: pill.color }}
        >
          <span
            aria-hidden
            className="h-1 w-1 rounded-full"
            style={{ background: pill.color, boxShadow: `0 0 4px ${pill.color}` }}
          />
          {pill.label}
        </span>
      </div>

      {/* Tasks */}
      <ul className="flex flex-1 flex-col gap-0.5">
        {agent.tasks.slice(0, 4).map((t, i) => (
          <li
            key={i}
            className="truncate font-mono text-[9px] leading-relaxed text-[var(--ops-fg-mute)]"
          >
            <span className="mr-1 text-[var(--hud-cyan)]">›</span>
            {t}
          </li>
        ))}
      </ul>

      {/* Progress bar */}
      <div className="hud-bar-track">
        <div
          className="hud-bar-fill"
          style={{ width: `${Math.max(0, Math.min(100, agent.progress ?? 0))}%` }}
        />
      </div>
    </motion.div>
  );
}
