"use client";

import { motion } from "framer-motion";
import type { VoiceState } from "@/hooks/useVoiceState";
import { VoiceWaveform } from "./VoiceWaveform";

interface VoicePanelProps {
  voice: VoiceState;
  samples: number[];
}

const TIER_LABEL: Record<NonNullable<VoiceState["tier"]> | "idle", string> = {
  local: "LOCAL",
  haiku: "HAIKU",
  sonnet: "SONNET",
  orchestrator: "DISPATCH",
  idle: "—",
};

const TIER_HUE: Record<NonNullable<VoiceState["tier"]> | "idle", string> = {
  local: "var(--ops-fg-mute)",
  haiku: "var(--ops-info)",
  sonnet: "var(--ops-amber)",
  orchestrator: "var(--ops-crit)",
  idle: "var(--ops-fg-faint)",
};

export function VoicePanel({ voice, samples }: VoicePanelProps) {
  const tier = voice.tier ?? "idle";
  const idle = voice.mode === "idle" || voice.mode === "offline";
  const offline = voice.mode === "offline";

  return (
    <section
      aria-label="Voice panel"
      className="ops-panel grid grid-cols-[140px_1fr_120px] items-center gap-3 px-3 py-2"
    >
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[10px] uppercase text-[var(--ops-fg-dim)]">
          voice
        </span>
        <span
          className="font-mono text-[12px] uppercase"
          style={{ color: offline ? "var(--ops-crit)" : "var(--ops-fg)" }}
        >
          {voice.mode}
        </span>
        <motion.span
          key={tier}
          initial={{ scale: 1.0, opacity: 0.6 }}
          animate={{ scale: 1.0, opacity: 1 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
          className="font-mono text-[10px]"
          style={{ color: TIER_HUE[tier] }}
        >
          tier · {TIER_LABEL[tier]}
        </motion.span>
      </div>

      <div className="flex flex-col gap-1">
        <VoiceWaveform samples={samples} idle={idle} color={TIER_HUE[tier]} />
        <p
          className="truncate font-mono text-[11px] text-[var(--ops-fg-mute)]"
          aria-live="polite"
        >
          {voice.last_text || (offline ? "voice offline — chat still works" : "listening…")}
        </p>
      </div>

      <div className="flex flex-col items-end gap-0.5 font-mono text-[10px] text-[var(--ops-fg-dim)]">
        <span>{voice.latency_ms || 0} ms</span>
        <span>${voice.cost_usd.toFixed(3)}</span>
      </div>
    </section>
  );
}
