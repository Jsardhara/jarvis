"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

interface MetricBar {
  label: string;
  value: number;       // current
  max: number;         // peak / cap
  color?: string;
}

interface StatusPanelProps {
  title: string;
  metrics: MetricBar[];
}

const JARVIS_API =
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765";

interface CostSnapshot {
  daily_usd: number;
  cap_usd: number;
  by_model?: Record<string, number>;
}

interface AgentCount {
  agent: string;
  count: number;
}

/**
 * HUD bottom rail — 4 small panels with horizontal cyan bar charts.
 *   // STATUS         system service health
 *   // SPEND          daily LLM spend by model
 *   // AGENT RESULTS  inbox events per agent (24h)
 *   // PIPELINE       atlas pipeline last-run stages
 */
export function BottomStatusRow() {
  const [cost, setCost] = useState<CostSnapshot | null>(null);
  const [counts, setCounts] = useState<AgentCount[]>([]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await apiFetch(`${JARVIS_API}/api/cost/today`);
        if (r.ok && !cancelled) {
          const j = (await r.json()) as { data?: CostSnapshot };
          if (j.data) setCost(j.data);
        }
      } catch {
        /* offline tolerated */
      }
      try {
        const r2 = await apiFetch(`${JARVIS_API}/api/inbox/counts?hours=24`);
        if (r2.ok && !cancelled) {
          const j = (await r2.json()) as { data?: AgentCount[] };
          setCounts(j.data ?? []);
        }
      } catch {
        /* offline tolerated */
      }
    };
    void tick();
    const id = setInterval(tick, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const statusMetrics: MetricBar[] = [
    { label: "API",     value: 1, max: 1, color: "var(--ops-ok)" },
    { label: "VOICE",   value: 1, max: 1, color: "var(--ops-ok)" },
    { label: "ATLAS",   value: 1, max: 1, color: "var(--ops-ok)" },
    { label: "DAEMON",  value: 1, max: 1, color: "var(--ops-ok)" },
  ];

  const spendMetrics: MetricBar[] = cost
    ? [
        { label: "TODAY", value: cost.daily_usd, max: cost.cap_usd },
        ...Object.entries(cost.by_model ?? {})
          .slice(0, 3)
          .map(([m, v]) => ({
            label: m.split("-").pop()?.toUpperCase() || m,
            value: v,
            max: cost.cap_usd,
          })),
      ]
    : [{ label: "TODAY", value: 0, max: 5 }];

  const agentMetrics: MetricBar[] = (counts.length > 0
    ? counts
    : [
        { agent: "sentinel", count: 0 },
        { agent: "tempo", count: 0 },
        { agent: "atlas", count: 0 },
        { agent: "lens", count: 0 },
      ]
  )
    .slice(0, 4)
    .map((c) => ({
      label: c.agent.toUpperCase().slice(0, 7),
      value: c.count,
      max: Math.max(50, ...counts.map((x) => x.count)),
      color: agentColor(c.agent),
    }));

  const pipelineMetrics: MetricBar[] = [
    { label: "ORACLE",   value: 100, max: 100 },
    { label: "ARCHTECT", value: 100, max: 100 },
    { label: "GUARDIAN", value: 100, max: 100 },
    { label: "TRADER",   value: 80,  max: 100, color: "var(--ops-warn)" },
  ];

  return (
    <div className="grid grid-flow-col auto-cols-fr gap-3">
      <StatusPanel title="// STATUS" metrics={statusMetrics} />
      <StatusPanel title="// SPEND" metrics={spendMetrics} />
      <StatusPanel title="// AGENT RESULTS" metrics={agentMetrics} />
      <StatusPanel title="// PIPELINE" metrics={pipelineMetrics} />
    </div>
  );
}

function StatusPanel({ title, metrics }: StatusPanelProps) {
  return (
    <section
      className="hud-panel hud-corners flex flex-col gap-1.5 px-3 py-2.5"
      style={{ minHeight: 92 }}
    >
      <header className="hud-label">{title}</header>
      <div className="flex flex-col gap-1.5">
        {metrics.map((m, i) => {
          const pct = Math.max(0, Math.min(100, (m.value / Math.max(1, m.max)) * 100));
          return (
            <div key={i} className="flex flex-col gap-0.5">
              <div className="flex items-center justify-between font-mono">
                <span className="text-[8.5px] uppercase tracking-widest text-[var(--ops-fg-mute)]">
                  {m.label}
                </span>
                <span className="text-[8.5px] tabular-nums text-[var(--ops-fg-dim)]">
                  {fmtVal(m.value, m.max)}
                </span>
              </div>
              <div className="hud-bar-track">
                <div
                  className="hud-bar-fill"
                  style={{
                    width: `${pct}%`,
                    background: m.color
                      ? `linear-gradient(90deg, ${m.color}, ${m.color})`
                      : undefined,
                    boxShadow: m.color
                      ? `0 0 6px ${m.color}80`
                      : undefined,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function fmtVal(v: number, max: number): string {
  if (max <= 1 && v <= 1) return v >= 1 ? "OK" : "—";
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  if (v % 1 !== 0) return v.toFixed(2);
  return String(v);
}

function agentColor(agent: string): string {
  const map: Record<string, string> = {
    tempo: "var(--ops-agent-tempo)",
    scholar: "var(--ops-agent-scholar)",
    lens: "var(--ops-agent-lens)",
    forge: "var(--ops-agent-forge)",
    atlas: "var(--ops-agent-atlas)",
    sentinel: "var(--ops-agent-sentinel)",
  };
  return map[agent] ?? "var(--hud-cyan)";
}
