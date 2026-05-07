"use client";

/**
 * /cost — Daily agent cost chart
 *
 * Fetches 14 daily rollups from /api/cost/rollup and renders a stacked bar
 * chart with per-agent breakdown, legend, and sortable table.
 *
 * useSearchParams() requires a Suspense boundary in Next.js 15 App Router.
 * CostPageInner is wrapped in <Suspense> from the default export.
 *
 * Spec: docs/design/swimlane.md §6
 */

import { Suspense, useCallback, useMemo, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { BreadcrumbNav } from "@/components/breadcrumb-nav";
import { CostChart, CostLegend, CostTable } from "@/components/CostChart";
import type { CostTableRow } from "@/components/CostChart";
import { useDailyCost } from "@/hooks/useDailyCost";
import type { CostAgent } from "@/lib/types";

function formatUsd(val: number): string {
  if (val === 0) return "$0.00";
  return `$${val.toFixed(2)}`;
}

function projectMonth(total14d: number): number {
  return (total14d / 14) * 30;
}

// ─── Inner component (uses useSearchParams — must be inside Suspense) ─────────

function CostPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data, loading, error } = useDailyCost(14);

  const selectedAgent = searchParams.get("agent") ?? undefined;
  const selectedDay = searchParams.get("day") ?? undefined;
  const hideParam: string = searchParams.get("hide") ?? "";
  const hiddenFromUrl = useMemo(
    () => (hideParam ? hideParam.split(",").filter(Boolean) : []),
    [hideParam]
  );

  const [localHidden, setLocalHidden] = useState<string[]>(hiddenFromUrl);

  const handleToggleAgent = useCallback(
    (agent: string) => {
      const next = localHidden.includes(agent)
        ? localHidden.filter((a) => a !== agent)
        : [...localHidden, agent];
      setLocalHidden(next);
      const params = new URLSearchParams(searchParams.toString());
      if (next.length > 0) {
        params.set("hide", next.join(","));
      } else {
        params.delete("hide");
      }
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [localHidden, router, searchParams]
  );

  const handleSegmentClick = useCallback(
    (agent: string, date: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("agent", agent);
      params.set("day", date);
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const agentTotals = useMemo(() => {
    const t: Record<string, number> = {};
    for (const day of data) {
      for (const ac of day.perAgent) {
        t[ac.agent] = (t[ac.agent] ?? 0) + ac.costUsd;
      }
    }
    return t;
  }, [data]);

  const grandTotal = useMemo(
    () => data.reduce((sum, d) => sum + d.totalUsd, 0),
    [data]
  );

  const tableRows = useMemo<CostTableRow[]>(() => {
    const filtered = selectedDay
      ? data.filter((d) => d.date === selectedDay)
      : data;

    const buckets: Record<CostAgent, CostTableRow> = {} as Record<CostAgent, CostTableRow>;
    for (const day of filtered) {
      for (const ac of day.perAgent) {
        if (selectedAgent && ac.agent !== selectedAgent) continue;
        const existing = buckets[ac.agent as CostAgent];
        if (existing) {
          buckets[ac.agent as CostAgent] = {
            ...existing,
            calls: existing.calls + ac.calls,
            inputTokens: existing.inputTokens + ac.inputTokens,
            outputTokens: existing.outputTokens + ac.outputTokens,
            totalUsd: existing.totalUsd + ac.costUsd,
          };
        } else {
          buckets[ac.agent as CostAgent] = {
            agent: ac.agent as CostAgent,
            calls: ac.calls,
            inputTokens: ac.inputTokens,
            outputTokens: ac.outputTokens,
            totalUsd: ac.costUsd,
          };
        }
      }
    }
    return Object.values(buckets);
  }, [data, selectedAgent, selectedDay]);

  return (
    <div className="space-y-4 p-5 font-mono">
      <BreadcrumbNav items={[{ label: "Cost" }]} />

      {/* Summary strip */}
      <div className="flex flex-wrap items-center gap-2 text-sm text-foreground border-b border-[color:var(--pipeline-lane-divider)] pb-3">
        <span>daily cost · last 14d</span>
        <span className="text-muted-foreground">·</span>
        <span>
          total{" "}
          <strong className="tabular-nums">{formatUsd(grandTotal)}</strong>
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">
          proj month{" "}
          <span className="tabular-nums text-foreground">
            {formatUsd(projectMonth(grandTotal))}
          </span>
        </span>
        {selectedAgent && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground">
              filtered:{" "}
              <button
                type="button"
                className="text-foreground hover:underline"
                onClick={() => {
                  const params = new URLSearchParams(searchParams.toString());
                  params.delete("agent");
                  params.delete("day");
                  router.replace(`?${params.toString()}`, { scroll: false });
                }}
              >
                {selectedAgent}
                {selectedDay ? ` · ${selectedDay}` : ""}
                {" ×"}
              </button>
            </span>
          </>
        )}
      </div>

      {loading && (
        <p className="text-sm text-muted-foreground">loading cost data…</p>
      )}
      {error && (
        <p className="text-sm text-[color:var(--pipeline-stage-error)]">
          error: {error}
        </p>
      )}

      {!loading && !error && (
        <>
          <CostChart
            data={data}
            selectedAgent={selectedAgent}
            hiddenAgents={localHidden}
            onSegmentClick={handleSegmentClick}
          />

          <CostLegend
            hiddenAgents={localHidden}
            onToggle={handleToggleAgent}
            totals={agentTotals}
          />

          <div className="border-t border-[color:var(--pipeline-lane-divider)] pt-4">
            <CostTable rows={tableRows} />
          </div>
        </>
      )}
    </div>
  );
}

// ─── Default export wraps in Suspense (required by useSearchParams) ───────────

export default function CostPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4 p-5 font-mono">
          <p className="text-sm text-muted-foreground">loading…</p>
        </div>
      }
    >
      <CostPageInner />
    </Suspense>
  );
}
