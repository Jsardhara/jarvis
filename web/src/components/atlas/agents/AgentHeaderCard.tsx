"use client";

/**
 * AgentHeaderCard
 *
 * Full-width header for a per-agent workspace.
 * Shows: display_name, model badge, state pill, last heartbeat,
 * today's LLM cost ($ + tokens) sourced from /api/cost/rollup.
 */

import { useDailyCost } from "@/hooks/useDailyCost";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import { Dot } from "@/components/ops/Dot";
import type { AgentDetail } from "@/hooks/useAgentDetail";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentHeaderCardProps {
  detail: AgentDetail | null;
  isLoading: boolean;
  accentColor?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  return `${Math.round(diff / 3_600_000)}h ago`;
}

type TagKind = "default" | "amber" | "ok" | "crit" | "info";
type DotKind = "ok" | "warn" | "crit" | "idle";

function stateToKind(state: string): { kind: TagKind; dotKind: DotKind } {
  switch (state?.toLowerCase()) {
    case "running":
    case "active":
      return { kind: "ok", dotKind: "ok" };
    case "paused":
    case "stale":
      return { kind: "amber", dotKind: "warn" };
    case "error":
    case "failed":
      return { kind: "crit", dotKind: "crit" };
    default:
      return { kind: "info", dotKind: "idle" };
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentHeaderCard({ detail, isLoading, accentColor }: AgentHeaderCardProps) {
  const { data: costData } = useDailyCostToday();
  const agentId = detail?.id ?? "";
  const todayCost = costData?.byAgent?.[agentId] ?? 0;
  const todayTokens = costData?.byAgentTokens?.[agentId] ?? 0;

  const { kind, dotKind } = detail?.state
    ? stateToKind(detail.state)
    : { kind: "info" as TagKind, dotKind: "idle" as DotKind };

  return (
    <Panel
      title={detail?.display_name ?? "AGENT"}
      leading={
        detail && (
          <span
            className="agent-header-glyph"
            style={{
              width: 32,
              height: 32,
              border: `1px solid ${accentColor ?? "var(--ops-amber)"}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: "var(--ops-mono)",
              fontSize: 11,
              letterSpacing: "0.08em",
              color: accentColor ?? "var(--ops-amber)",
              flexShrink: 0,
            }}
          >
            {detail.display_name.slice(0, 2).toUpperCase()}
          </span>
        )
      }
      trailing={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {detail && (
            <>
                  <Tag kind="info">
                {detail.model}
              </Tag>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Dot kind={dotKind} pulse={dotKind === "ok"} />
                <Tag kind={kind}>
                  {detail.state?.toUpperCase() ?? "UNKNOWN"}
                </Tag>
              </span>
              <span
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 10,
                  color: "var(--ops-fg-dim)",
                }}
              >
                HB: {relativeTime(detail.last_heartbeat)}
              </span>
            </>
          )}
          {isLoading && (
            <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-faint)" }}>
              LOADING...
            </span>
          )}
          <div
            style={{
              borderLeft: "1px solid var(--ops-line)",
              paddingLeft: 10,
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-end",
              gap: 2,
            }}
          >
            <span style={{ fontFamily: "var(--ops-mono)", fontSize: 11, color: "var(--ops-fg)" }}>
              ${todayCost.toFixed(4)}
            </span>
            <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, color: "var(--ops-fg-dim)" }}>
              {todayTokens > 0 ? `${(todayTokens / 1000).toFixed(1)}k tok` : "0 tok"}
            </span>
          </div>
        </div>
      }
      className="agent-header-card"
    >
      <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
        {detail ? (
          <>
            <KvItem label="ID" value={detail.id} />
            <KvItem label="MODEL" value={detail.model} />
            <KvItem label="STATE" value={detail.state?.toUpperCase() ?? "—"} />
            <KvItem label="LAST HB" value={relativeTime(detail.last_heartbeat)} />
            <KvItem label="TODAY COST" value={`$${todayCost.toFixed(4)}`} />
          </>
        ) : (
          <span style={{ color: "var(--ops-fg-faint)", fontFamily: "var(--ops-mono)", fontSize: 11 }}>
            {isLoading ? "Fetching agent data..." : "No agent data available."}
          </span>
        )}
      </div>
    </Panel>
  );
}

// ─── KV row atom ──────────────────────────────────────────────────────────────

function KvItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontFamily: "var(--ops-mono)", fontSize: 9, letterSpacing: "0.1em", color: "var(--ops-fg-faint)", textTransform: "uppercase" }}>
        {label}
      </span>
      <span style={{ fontFamily: "var(--ops-mono)", fontSize: 12, color: "var(--ops-fg)" }}>
        {value}
      </span>
    </div>
  );
}

// ─── Lightweight today-only cost hook (avoids 14-day fan-out) ─────────────────

interface TodayCostData {
  byAgent: Record<string, number>;
  byAgentTokens: Record<string, number>;
}

function useDailyCostToday(): { data: TodayCostData | null } {
  const state = useDailyCost(1);
  const today = state.data?.[0];
  if (!today) return { data: null };

  const byAgent: Record<string, number> = {};
  const byAgentTokens: Record<string, number> = {};
  for (const ac of today.perAgent) {
    byAgent[ac.agent] = ac.costUsd;
    byAgentTokens[ac.agent] = (ac.inputTokens ?? 0) + (ac.outputTokens ?? 0);
  }
  return { data: { byAgent, byAgentTokens } };
}
