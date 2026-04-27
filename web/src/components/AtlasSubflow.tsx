"use client";

import { useEffect, useRef, useState } from "react";
import type { VerificationStatus } from "./VerificationPill";

export type AtlasStage = "oracle" | "architect" | "guardian" | "trader" | "sage";
export type AtlasStageStatus = "pending" | "running" | "done" | "error" | "halted";

export type AtlasStageState = {
  status: AtlasStageStatus;
  summary?: string;
  ts?: string;
  verification?: VerificationStatus;
};

interface AtlasSubflowProps {
  stages: Partial<Record<AtlasStage, AtlasStageState>>;
  onDismiss?: () => void;
}

const PIPELINE: AtlasStage[] = ["oracle", "architect", "guardian", "trader", "sage"];
const TERMINAL_STATUSES = new Set<AtlasStageStatus>(["done", "error", "halted"]);
const AUTO_DISMISS_MS = 12_000;

function isTerminal(stages: Partial<Record<AtlasStage, AtlasStageState>>): boolean {
  const last = PIPELINE[PIPELINE.length - 1];
  const lastState = stages[last];
  if (lastState && TERMINAL_STATUSES.has(lastState.status)) return true;
  // Guardian halted stops the pipeline
  const guardian = stages["guardian"];
  if (guardian?.status === "halted") return true;
  return false;
}

function stageStateLabel(s: AtlasStageState | undefined): string {
  if (!s) return "waiting";
  if (s.summary) return s.summary;
  return s.status;
}

export function AtlasSubflow({ stages, onDismiss }: AtlasSubflowProps) {
  const hasAny = Object.keys(stages).length > 0;
  const [visible, setVisible] = useState(false);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (hasAny) {
      setVisible(true);
      if (isTerminal(stages)) {
        dismissTimer.current = setTimeout(() => {
          setVisible(false);
          onDismiss?.();
        }, AUTO_DISMISS_MS);
      }
    }
    return () => {
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
    };
  }, [hasAny, stages, onDismiss]);

  const handleClose = () => {
    setVisible(false);
    onDismiss?.();
  };

  return (
    <div className="atlas-rail" data-active={String(visible)} aria-live="polite">
      <div className="atlas-pipeline">
        {PIPELINE.map((stage, i) => {
          const state = stages[stage];
          const status = state?.status ?? "pending";
          const vrf = state?.verification ?? "unknown";
          return (
            <div key={stage} className="atlas-stage-wrap">
              {i > 0 && <div className="atlas-connector" aria-hidden="true" />}
              <div
                className="atlas-stage"
                data-astatus={status}
                title={stageStateLabel(state)}
              >
                <div className="atlas-stage-top">
                  {status === "running" && (
                    <span className="dot" data-status="running" style={{ width: 6, height: 6 }} />
                  )}
                  {status === "done" && (
                    <span className="dot" data-status="done" style={{ width: 6, height: 6 }} />
                  )}
                  {stage}
                  {status === "halted" && (
                    <span className="atlas-stage-halted-icon">[!]</span>
                  )}
                </div>
                <div className="atlas-stage-state">
                  {stageStateLabel(state)}
                </div>
                <div className="atlas-stage-vrf" data-vstatus={vrf} />
              </div>
            </div>
          );
        })}
      </div>
      <button
        type="button"
        className="atlas-rail-close"
        onClick={handleClose}
        aria-label="Dismiss atlas pipeline"
      >
        ×
      </button>
    </div>
  );
}
