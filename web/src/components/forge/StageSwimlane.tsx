"use client";

import type { CSSProperties } from "react";
import { Tag } from "@/components/ops";

const STAGES = ["plan", "tdd", "implement", "review", "security", "open_pr"] as const;
const STAGE_OWNERS: Record<(typeof STAGES)[number], string> = {
  plan: "PLANNER",
  tdd: "TDD-GUIDE",
  implement: "PRP-IMPLEMENT",
  review: "CODE-REVIEWER",
  security: "SECURITY-REVIEWER",
  open_pr: "GITHUB-OPS",
};

export type StageStatus = "done" | "active" | "blocked" | "pending";

interface Props {
  /**
   * Status of each stage. Missing keys default to "pending".
   * No active job → all pending → renders as a static skeleton.
   */
  statuses?: Partial<Record<(typeof STAGES)[number], StageStatus>>;
  /** Headline label for the swimlane. */
  jobTitle?: string;
}

const STATUS_KIND: Record<StageStatus, "ok" | "amber" | "crit" | "default"> = {
  done: "ok",
  active: "amber",
  blocked: "crit",
  pending: "default",
};

export function StageSwimlane({ statuses = {}, jobTitle }: Props) {
  const wrap: CSSProperties = {
    display: "grid",
    gridTemplateColumns: `repeat(${STAGES.length}, 1fr)`,
    gap: 0,
    border: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
  };

  const cell: CSSProperties = {
    padding: "12px 10px",
    borderRight: "1px solid var(--ops-line)",
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 6,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {jobTitle && (
        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg-mute)",
            letterSpacing: "0.08em",
            padding: "0 4px",
          }}
        >
          {jobTitle}
        </div>
      )}
      <div style={wrap}>
        {STAGES.map((s, i) => {
          const status = statuses[s] ?? "pending";
          const isLast = i === STAGES.length - 1;
          const arrow = !isLast ? (
            <span
              style={{
                position: "absolute",
                right: -7,
                top: "50%",
                transform: "translateY(-50%)",
                fontFamily: "var(--ops-mono)",
                fontSize: 14,
                color: "var(--ops-line-bright)",
                background: "var(--ops-bg-deep)",
                padding: "0 2px",
                zIndex: 1,
              }}
            >
              →
            </span>
          ) : null;
          return (
            <div
              key={s}
              style={{
                ...cell,
                position: "relative",
                borderRight: isLast ? "none" : cell.borderRight,
              }}
            >
              <Tag kind={STATUS_KIND[status]}>{s.toUpperCase()}</Tag>
              <span
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: "var(--ops-fg-mute)",
                  letterSpacing: "0.06em",
                }}
              >
                {STAGE_OWNERS[s]}
              </span>
              <span
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: status === "active" ? "var(--ops-amber)" : "var(--ops-fg-dim)",
                  letterSpacing: "0.06em",
                }}
              >
                {status.toUpperCase()}
              </span>
              {arrow}
            </div>
          );
        })}
      </div>
    </div>
  );
}
