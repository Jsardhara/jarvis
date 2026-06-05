"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useMissionBus } from "@/hooks/useMissionBus";
import { apiFetch } from "@/lib/api-client";
import { AgentCardRow, type AgentCard } from "./AgentCardRow";
import { CentralOrb } from "./CentralOrb";
import { CommandPanel } from "./CommandPanel";
import { LeftSidebar } from "./LeftSidebar";
import { RightSidebar } from "./RightSidebar";
import { BottomStatusRow } from "./BottomStatusRow";

const JARVIS_API =
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765";

const AGENT_ORDER = ["jarvis", "tempo", "scholar", "lens", "forge", "atlas", "sentinel", "me"] as const;

const AGENT_ACCENTS: Record<string, string> = {
  jarvis: "var(--hud-cyan)",
  tempo: "var(--ops-agent-tempo)",
  scholar: "var(--ops-agent-scholar)",
  lens: "var(--ops-agent-lens)",
  forge: "var(--ops-agent-forge)",
  atlas: "var(--ops-agent-atlas)",
  sentinel: "var(--ops-agent-sentinel)",
  me: "var(--ops-fg)",
};

interface AgentApi {
  id: string;
  name: string;
  status: string;
  role?: string;
  personality?: string;
  capabilities?: string[];
  dashboard?: {
    primary_widgets?: string[];
  };
}

/**
 * JARVIS HUD MK-VII — main mission-control surface.
 *
 *   ┌───────────────────────────────────────────────────────────┐
 *   │  TOP BAR  · jarvis · status · version                     │
 *   ├───────────────────────────────────────────────────────────┤
 *   │  [TEMPO] [SCHOLAR] [LENS] [FORGE] [ATLAS]   agent cards   │
 *   ├──────────┬───────────────────────────────────┬────────────┤
 *   │  LEFT    │           ◉ JARVIS ORB            │  RIGHT     │
 *   │ portfo   │           command panel           │  tasks +   │
 *   │  + news  │                                   │  confirms  │
 *   ├──────────┴───────────────────────────────────┴────────────┤
 *   │  STATUS · SPEND · AGENT RESULTS · PIPELINE                │
 *   └───────────────────────────────────────────────────────────┘
 */
export function HudMissionControl() {
  const bus = useMissionBus();
  const [agentRows, setAgentRows] = useState<AgentCard[]>([]);
  const [activeAgent, setActiveAgent] = useState<string | undefined>(undefined);

  // Fetch Hermes crew manifest first; fall back to the legacy registry if the
  // backend has not been migrated yet.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const toCard = (a: AgentApi): AgentCard => {
        const widgets = a.dashboard?.primary_widgets ?? [];
        const tasks = [a.role, ...widgets, ...(a.capabilities ?? [])]
          .filter((task): task is string => Boolean(task))
          .slice(0, 4)
          .map((task) => task.replaceAll("_", " "));
        return {
          id: a.id,
          name: a.name,
          status: (a.status as AgentCard["status"]) ?? "online",
          tasks: tasks.length ? tasks : [a.personality ?? "awaiting assignment"],
          progress: a.status === "offline" ? 0 : 100,
          accent: AGENT_ACCENTS[a.id] ?? "var(--hud-cyan)",
        };
      };

      const offlineCards = (): AgentCard[] =>
        AGENT_ORDER.map((id) => ({
          id,
          name: id,
          status: "offline" as const,
          tasks: ["awaiting Hermes manifest…"],
          progress: 0,
          accent: AGENT_ACCENTS[id],
        }));

      try {
        let r = await apiFetch(`${JARVIS_API}/api/hermes/agents`);
        let j = (r.ok ? await r.json() : {}) as { data?: AgentApi[]; agents?: AgentApi[] };
        let list = j.data ?? j.agents ?? [];

        if (!list.length) {
          r = await apiFetch(`${JARVIS_API}/api/agents`);
          j = (r.ok ? await r.json() : {}) as { data?: AgentApi[]; agents?: AgentApi[] };
          list = j.data ?? j.agents ?? [];
        }

        if (cancelled) return;
        const ordered = AGENT_ORDER
          .map((id) => list.find((a) => a.id === id))
          .filter(Boolean) as AgentApi[];
        const cards = ordered.length ? ordered : list;
        setAgentRows(cards.length ? cards.map(toCard) : offlineCards());
      } catch {
        // offline — show stub cards
        if (cancelled) return;
        setAgentRows(offlineCards());
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Highlight the most-recent active agent from the bus event stream.
  useEffect(() => {
    if (!bus.events?.length) return;
    const last = bus.events[bus.events.length - 1];
    const id = (last as { agent?: string })?.agent;
    if (!id) return;
    setActiveAgent(id);
    const t = setTimeout(() => setActiveAgent(undefined), 4000);
    return () => clearTimeout(t);
  }, [bus.events]);

  // Map voice state → orb intensity
  const mode = bus.voice?.mode;
  const orbState: "idle" | "listening" | "speaking" | "thinking" =
    mode === "tts"     ? "speaking"
    : mode === "stt"   ? "listening"
    : mode === "routing" ? "thinking"
    : "idle";

  return (
    <div
      className="relative flex h-[calc(100vh-44px)] flex-col gap-3 overflow-hidden p-3"
      style={{ minHeight: 720 }}
    >
      {/* Faint scanline sweep over the whole HUD */}
      <div aria-hidden className="hud-scan-line" />

      <TopBar />

      {/* Agent cards row */}
      <AgentCardRow agents={agentRows} active={activeAgent} />

      {/* Body grid: left | center | right */}
      <div className="grid min-h-0 flex-1 grid-cols-[260px_1fr_260px] gap-3">
        <LeftSidebar />

        <CenterStage orbState={orbState} />

        <RightSidebar />
      </div>

      {/* Bottom status row */}
      <BottomStatusRow />
    </div>
  );
}

// ─── Top bar ─────────────────────────────────────────────────────────────────

function TopBar() {
  return (
    <header className="hud-panel hud-corners flex items-center justify-between px-4 py-2">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="h-1.5 w-1.5 rounded-full"
          style={{
            background: "var(--ops-ok)",
            boxShadow: "0 0 6px var(--ops-ok)",
          }}
        />
        <span
          className="hud-display hud-text-glow"
          style={{ color: "var(--hud-cyan)", fontSize: 16 }}
        >
          JARVIS
        </span>
        <span
          className="font-mono text-[9px] tracking-[0.2em]"
          style={{ color: "var(--ops-fg-faint)" }}
        >
          MK-VII · ONLINE
        </span>
      </div>
      <div className="flex items-center gap-4">
        <span
          className="font-mono text-[9px] tracking-widest"
          style={{ color: "var(--ops-fg-mute)" }}
        >
          {new Date().toISOString().slice(0, 16).replace("T", " ")} UTC
        </span>
        <span
          className="hud-pill"
          style={{ color: "var(--ops-ok)" }}
        >
          ALL SYSTEMS
        </span>
      </div>
    </header>
  );
}

// ─── Center stage ────────────────────────────────────────────────────────────

interface CenterStageProps {
  orbState: "idle" | "listening" | "speaking" | "thinking";
}

function CenterStage({ orbState }: CenterStageProps) {
  return (
    <div className="relative flex flex-col items-center justify-between gap-4 px-4">
      {/* Faint circular HUD chrome behind orb */}
      <div className="relative flex flex-1 items-center justify-center">
        <CircularChrome />
        <motion.div
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        >
          <CentralOrb state={orbState} size={96} label="J.A.R.V.I.S" />
        </motion.div>
      </div>

      <CommandPanel />
    </div>
  );
}

function CircularChrome() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 320 320"
      className="absolute inset-0 m-auto"
      style={{ width: 320, height: 320, opacity: 0.45 }}
    >
      <defs>
        <radialGradient id="hud-chrome-glow" cx="50%" cy="50%" r="50%">
          <stop offset="60%" stopColor="rgba(0,229,255,0)" />
          <stop offset="100%" stopColor="rgba(0,229,255,0.18)" />
        </radialGradient>
      </defs>
      <circle cx="160" cy="160" r="140" fill="url(#hud-chrome-glow)" />
      <circle
        cx="160"
        cy="160"
        r="140"
        fill="none"
        stroke="var(--hud-cyan)"
        strokeWidth="0.8"
        strokeDasharray="2 6"
        opacity="0.55"
      />
      <circle
        cx="160"
        cy="160"
        r="105"
        fill="none"
        stroke="var(--hud-cyan)"
        strokeWidth="0.6"
        strokeDasharray="1 4"
        opacity="0.40"
      />
      <circle
        cx="160"
        cy="160"
        r="70"
        fill="none"
        stroke="var(--hud-cyan)"
        strokeWidth="0.6"
        opacity="0.30"
      />
      {/* Tick marks */}
      {Array.from({ length: 60 }).map((_, i) => {
        const angle = (i / 60) * Math.PI * 2;
        const x1 = 160 + Math.cos(angle) * 142;
        const y1 = 160 + Math.sin(angle) * 142;
        const x2 = 160 + Math.cos(angle) * (i % 5 === 0 ? 132 : 138);
        const y2 = 160 + Math.sin(angle) * (i % 5 === 0 ? 132 : 138);
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="var(--hud-cyan)"
            strokeWidth={i % 5 === 0 ? 1 : 0.5}
            opacity={i % 5 === 0 ? 0.7 : 0.4}
          />
        );
      })}
    </svg>
  );
}
