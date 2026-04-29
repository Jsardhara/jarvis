"use client";

import { BrandMark } from "./BrandMark";
import { Clock } from "./Clock";
import { Tag } from "./Tag";
import { Dot } from "./Dot";
import { useSidebar } from "@/hooks/use-sidebar";
import { useDailyCost } from "@/hooks/useDailyCost";

/**
 * Topbar — 44px header bar occupying grid-area "topbar".
 *
 * Left:   BrandMark + "JARVIS // OPS" wordmark
 * Center: orchestrator chip
 * Right:  live meta cluster (active tasks / queue / inbox / cost / clock)
 *
 * Counts come from useSidebar (no new API endpoints introduced).
 * Daily cost comes from useDailyCost (today = index 13, last in the 14-day window).
 */
export function Topbar() {
  const { tasks, unreadInbox, pendingDecisions } = useSidebar();
  const costState = useDailyCost(1);
  const costData = costState.data;

  const activeTasks = tasks.filter((t) => t.kanban === "in-progress").length;
  const dailyCostUsd =
    costData.length > 0 ? costData[costData.length - 1].totalUsd : 0;
  const costDisplay =
    dailyCostUsd === 0 ? "$0.00" : `$${dailyCostUsd.toFixed(2)}`;

  return (
    <header className="ops-topbar">
      {/* ── Brand ── */}
      <div className="flex items-center gap-2 shrink-0">
        <BrandMark />
        <span
          style={{
            fontFamily: "var(--ops-sans)",
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--ops-fg)",
          }}
        >
          JARVIS
        </span>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            letterSpacing: "0.16em",
            color: "var(--ops-fg-faint)",
          }}
        >
          {"// OPS"}
        </span>
      </div>

      {/* ── Orchestrator chip ── */}
      <div className="flex-1 flex justify-center">
        <Tag kind="amber">
          ORCHESTRATOR · OPUS-4.7 ·{" "}
          <span style={{ color: "var(--ops-ok)" }}>ONLINE</span>
        </Tag>
      </div>

      {/* ── Meta cluster ── */}
      <div
        className="flex items-center shrink-0"
        style={{
          fontFamily: "var(--ops-mono)",
          fontSize: 11,
          color: "var(--ops-fg-dim)",
          gap: 24,
        }}
      >
        <span className="flex items-center gap-1">
          <Dot kind="ok" pulse />
          ACTIVE <b style={{ color: "var(--ops-fg)" }}>{activeTasks}</b>
        </span>
        <span>
          QUEUE <b style={{ color: "var(--ops-fg)" }}>{pendingDecisions}</b>
        </span>
        <span>
          INBOX <b style={{ color: "var(--ops-fg)" }}>{unreadInbox}</b>
        </span>
        <span>
          COST{" "}
          <b style={{ color: "var(--ops-amber)" }}>{costDisplay}</b>
        </span>
        <Clock />
      </div>
    </header>
  );
}
