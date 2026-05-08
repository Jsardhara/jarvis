"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useMemo } from "react";
import type { InboxEvent } from "@/hooks/useInboxStream";

interface AtlasSubFlowRailProps {
  events: InboxEvent[];
}

const STAGES = ["oracle", "architect", "guardian", "trader", "sage"] as const;
type Stage = (typeof STAGES)[number];

const STAGE_HUE: Record<Stage, string> = {
  oracle: "var(--atlas-oracle)",
  architect: "var(--atlas-architect)",
  guardian: "var(--atlas-guardian)",
  trader: "var(--atlas-trader)",
  sage: "var(--atlas-sage)",
};

const ACTIVE_WINDOW_MS = 30_000;

export function AtlasSubFlowRail({ events }: AtlasSubFlowRailProps) {
  const { active, status } = useMemo(() => {
    const now = Date.now();
    const recent = events.filter((e) => {
      if (e.agent !== "atlas") return false;
      const ts = e.ts ? Date.parse(e.ts) : 0;
      return now - ts < ACTIVE_WINDOW_MS;
    });
    const stageStatus = new Map<Stage, "idle" | "active" | "halted">();
    for (const stage of STAGES) stageStatus.set(stage, "idle");
    let anyActive = false;
    for (const e of recent) {
      const stage = (e.payload?.["stage"] as Stage) ?? null;
      if (!stage || !STAGES.includes(stage)) continue;
      anyActive = true;
      const sev = (e.payload?.["severity"] as string) ?? "info";
      stageStatus.set(stage, sev === "alert" ? "halted" : "active");
    }
    return { active: anyActive, status: stageStatus };
  }, [events]);

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          key="atlas-sub-flow"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 64, opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.32, ease: "easeOut" }}
          className="ops-panel flex w-full items-center gap-2 overflow-hidden px-3"
          aria-label="Atlas pipeline"
        >
          {STAGES.map((stage, i) => {
            const s = status.get(stage) ?? "idle";
            const hue = STAGE_HUE[stage];
            return (
              <div key={stage} className="flex flex-1 items-center gap-2">
                <div
                  className="flex flex-1 flex-col items-center justify-center gap-1 border px-2 py-1.5"
                  style={{
                    borderColor:
                      s === "halted"
                        ? "var(--ops-crit)"
                        : s === "active"
                          ? hue
                          : "var(--ops-line-faint)",
                    background:
                      s === "active" ? "var(--ops-bg-elevated)" : "transparent",
                  }}
                >
                  <span
                    className="font-mono text-[10px] uppercase tracking-wide"
                    style={{ color: s === "halted" ? "var(--ops-crit)" : hue }}
                  >
                    {stage}
                  </span>
                  <span
                    className="font-mono text-[9px]"
                    style={{ color: "var(--ops-fg-dim)" }}
                  >
                    {s}
                  </span>
                </div>
                {i < STAGES.length - 1 && (
                  <span
                    aria-hidden
                    className="h-px w-2 bg-[var(--ops-line-faint)]"
                  />
                )}
              </div>
            );
          })}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
