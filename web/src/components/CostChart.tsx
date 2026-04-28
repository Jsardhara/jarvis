"use client";

/**
 * CostChart
 *
 * Pure presentational stacked bar chart for daily agent costs.
 * Renders hand-rolled SVG — terminal brutalism = pixel-sharp axis lines,
 * no rounded corners, no heavy charting library.
 *
 * Spec: docs/design/swimlane.md §6
 */

import { useCallback, useId, useMemo, useRef, useState } from "react";
import type { CostAgent, DailyRollup } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Constants ────────────────────────────────────────────────────────────────

// Stack order: high-cost at bottom (sits on axis), low overhead at top
const STACK_ORDER: CostAgent[] = [
  "atlas",
  "forge",
  "lens",
  "scholar",
  "tempo",
  "jarvis",
  "sentinel",
];

const AGENT_LABELS: Record<CostAgent, string> = {
  atlas:    "Atlas",
  forge:    "Forge",
  lens:     "Lens",
  scholar:  "Scholar",
  tempo:    "Tempo",
  jarvis:   "Jarvis",
  sentinel: "Sentinel",
};

const AGENT_CSS_VARS: Record<CostAgent, string> = {
  atlas:    "var(--chart-bar-atlas)",
  forge:    "var(--chart-bar-forge)",
  lens:     "var(--chart-bar-lens)",
  scholar:  "var(--chart-bar-scholar)",
  tempo:    "var(--chart-bar-tempo)",
  jarvis:   "var(--chart-bar-jarvis)",
  sentinel: "var(--chart-bar-sentinel)",
};

const CHART_HEIGHT = 340;
const BAR_PADDING_TOP = 24;      // space above tallest bar
const X_AXIS_HEIGHT = 32;
const LEGEND_HEIGHT = 0;         // legend is below chart, not inside SVG
const MARGIN_LEFT = 56;
const MARGIN_RIGHT = 16;
const BAR_GAP_RATIO = 0.3;       // 30% gap between bars

// ─── Props ────────────────────────────────────────────────────────────────────

export interface CostChartProps {
  data: DailyRollup[];
  selectedAgent?: string;
  hiddenAgents?: string[];
  onSegmentClick?: (agent: string, date: string) => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatUsd(val: number): string {
  if (val === 0) return "$0";
  if (val < 0.01) return `<$0.01`;
  return `$${val.toFixed(2)}`;
}

function dayLabel(isoDate: string): string {
  const d = new Date(isoDate + "T12:00:00Z");
  return d.toLocaleDateString("en-US", { weekday: "short", day: "numeric", timeZone: "UTC" });
}

function isToday(isoDate: string): boolean {
  return isoDate === new Date().toISOString().slice(0, 10);
}

// ─── Tooltip ──────────────────────────────────────────────────────────────────

interface TooltipData {
  agent: CostAgent | null;  // null = whole-bar hover
  date: string;
  costUsd: number;
  calls: number;
  totalUsd?: number;
  totalCalls?: number;
  x: number;
  y: number;
}

function Tooltip({ data }: { data: TooltipData }) {
  const { agent, date, costUsd, calls, totalUsd, totalCalls, x, y } = data;
  const lines: string[] = [];
  if (agent) {
    lines.push(`${AGENT_LABELS[agent]} · ${dayLabel(date)}`);
    lines.push(`${formatUsd(costUsd)} · ${calls} call${calls !== 1 ? "s" : ""}`);
  } else {
    lines.push(dayLabel(date));
    lines.push(`${formatUsd(totalUsd ?? costUsd)} total`);
    if (totalCalls) lines.push(`${totalCalls} calls`);
  }

  // Measure approximate width
  const maxLen = Math.max(...lines.map((l) => l.length));
  const tw = maxLen * 7 + 16;
  const th = lines.length * 18 + 12;

  return (
    <g
      transform={`translate(${x},${y})`}
      style={{ pointerEvents: "none" }}
      aria-hidden="true"
    >
      <rect
        x={0}
        y={-th}
        width={tw}
        height={th}
        fill="var(--chart-tooltip-bg)"
        rx={0}
      />
      {lines.map((line, i) => (
        <text
          key={i}
          x={8}
          y={-th + 14 + i * 18}
          fill="var(--chart-tooltip-fg)"
          fontFamily="'JetBrains Mono', 'Courier New', monospace"
          fontSize={11}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function CostChart({
  data,
  hiddenAgents = [],
  onSegmentClick,
}: CostChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [containerWidth, setContainerWidth] = useState(800);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const clipId = useId();

  // Observe container width for responsive rendering
  const resizeRef = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setContainerWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const visibleAgents = STACK_ORDER.filter((a) => !hiddenAgents.includes(a));

  // Compute per-bar stacks
  const bars = useMemo(() => {
    return data.map((day) => {
      const agentMap: Record<string, number> = {};
      for (const ac of day.perAgent) {
        agentMap[ac.agent] = ac.costUsd;
      }
      const stacks = visibleAgents.map((agent) => ({
        agent,
        costUsd: agentMap[agent] ?? 0,
        calls: day.perAgent.find((a) => a.agent === agent)?.calls ?? 0,
      }));
      return { date: day.date, totalUsd: day.totalUsd, stacks };
    });
  }, [data, visibleAgents]);

  const maxTotal = Math.max(...bars.map((b) => b.totalUsd), 0.01);

  const innerW = containerWidth - MARGIN_LEFT - MARGIN_RIGHT;
  const innerH = CHART_HEIGHT - X_AXIS_HEIGHT - BAR_PADDING_TOP;

  const barCount = bars.length || 1;
  const barSlotW = innerW / barCount;
  const barW = barSlotW * (1 - BAR_GAP_RATIO);

  // Y grid lines
  const gridSteps = 4;
  const gridValues = Array.from({ length: gridSteps + 1 }, (_, i) =>
    (maxTotal * i) / gridSteps
  );

  function toY(usd: number): number {
    return BAR_PADDING_TOP + innerH - (usd / maxTotal) * innerH;
  }

  function barX(i: number): number {
    return MARGIN_LEFT + i * barSlotW + (barSlotW - barW) / 2;
  }

  return (
    <div className="w-full font-mono text-xs">
      {/* Chart SVG */}
      <div
        ref={resizeRef}
        className="w-full"
        style={{ height: CHART_HEIGHT + LEGEND_HEIGHT }}
      >
        <svg
          ref={svgRef}
          width="100%"
          height={CHART_HEIGHT}
          aria-label="Daily agent cost chart"
          role="img"
          style={{ display: "block", overflow: "visible" }}
        >
          <defs>
            <clipPath id={clipId}>
              <rect
                x={MARGIN_LEFT}
                y={0}
                width={innerW}
                height={CHART_HEIGHT - X_AXIS_HEIGHT}
              />
            </clipPath>
          </defs>

          {/* Y-axis grid lines + labels */}
          {gridValues.map((val, i) => {
            const y = toY(val);
            return (
              <g key={i}>
                <line
                  x1={MARGIN_LEFT}
                  y1={y}
                  x2={MARGIN_LEFT + innerW}
                  y2={y}
                  stroke="var(--chart-grid)"
                  strokeWidth={0.5}
                />
                <text
                  x={MARGIN_LEFT - 4}
                  y={y + 4}
                  textAnchor="end"
                  fill="var(--chart-axis)"
                  fontFamily="'JetBrains Mono', 'Courier New', monospace"
                  fontSize={10}
                >
                  {formatUsd(val)}
                </text>
              </g>
            );
          })}

          {/* Y axis line */}
          <line
            x1={MARGIN_LEFT}
            y1={BAR_PADDING_TOP}
            x2={MARGIN_LEFT}
            y2={CHART_HEIGHT - X_AXIS_HEIGHT}
            stroke="var(--chart-axis)"
            strokeWidth={1}
          />

          {/* X axis line */}
          <line
            x1={MARGIN_LEFT}
            y1={CHART_HEIGHT - X_AXIS_HEIGHT}
            x2={MARGIN_LEFT + innerW}
            y2={CHART_HEIGHT - X_AXIS_HEIGHT}
            stroke="var(--chart-axis)"
            strokeWidth={1}
          />

          {/* Bars */}
          <g clipPath={`url(#${clipId})`}>
            {bars.map((bar, i) => {
              const x = barX(i);
              const today = isToday(bar.date);

              // Build stacked segments bottom-up
              let cumulativeUsd = 0;
              const segments = [...bar.stacks].reverse().map((seg) => {
                const h = (seg.costUsd / maxTotal) * innerH;
                const segY = toY(cumulativeUsd + seg.costUsd);
                cumulativeUsd += seg.costUsd;
                return { ...seg, h, segY };
              });
              segments.reverse(); // back to bottom-up order

              return (
                <g key={bar.date}>
                  {/* Today's bar emphasis outline */}
                  {today && (
                    <rect
                      x={x - 1}
                      y={BAR_PADDING_TOP}
                      width={barW + 2}
                      height={innerH}
                      fill="none"
                      stroke="var(--foreground)"
                      strokeWidth={2}
                    />
                  )}

                  {/* Segments (rendered bottom to top in DOM, so aria-label is on each) */}
                  {segments.map((seg) => {
                    if (seg.h < 0.5) return null;
                    return (
                      <rect
                        key={seg.agent}
                        x={x}
                        y={seg.segY}
                        width={barW}
                        height={seg.h}
                        fill={AGENT_CSS_VARS[seg.agent]}
                        role="button"
                        tabIndex={0}
                        aria-label={`${AGENT_LABELS[seg.agent]}, ${dayLabel(bar.date)}, ${formatUsd(seg.costUsd)}, ${seg.calls} call${seg.calls !== 1 ? "s" : ""}`}
                        style={{ cursor: "pointer", outline: "none" }}
                        onMouseEnter={(e) => {
                          const svgEl = svgRef.current;
                          if (!svgEl) return;
                          const rect = svgEl.getBoundingClientRect();
                          const svgX = e.clientX - rect.left;
                          const svgY = e.clientY - rect.top;
                          setTooltip({
                            agent: seg.agent,
                            date: bar.date,
                            costUsd: seg.costUsd,
                            calls: seg.calls,
                            x: svgX,
                            y: svgY,
                          });
                        }}
                        onMouseLeave={() => setTooltip(null)}
                        onClick={() => onSegmentClick?.(seg.agent, bar.date)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ")
                            onSegmentClick?.(seg.agent, bar.date);
                        }}
                      />
                    );
                  })}

                  {/* X-axis label */}
                  <text
                    x={x + barW / 2}
                    y={CHART_HEIGHT - X_AXIS_HEIGHT + 14}
                    textAnchor="middle"
                    fill="var(--chart-axis)"
                    fontFamily="'JetBrains Mono', 'Courier New', monospace"
                    fontSize={10}
                    fontWeight={today ? "bold" : "normal"}
                  >
                    {dayLabel(bar.date)}
                  </text>
                </g>
              );
            })}
          </g>

          {/* Tooltip */}
          {tooltip && <Tooltip data={tooltip} />}
        </svg>
      </div>
    </div>
  );
}

// ─── CostLegend ───────────────────────────────────────────────────────────────

interface CostLegendProps {
  hiddenAgents: string[];
  onToggle: (agent: string) => void;
  totals: Record<string, number>;
}

export function CostLegend({ hiddenAgents, onToggle, totals }: CostLegendProps) {
  return (
    <div className="flex flex-wrap gap-3 font-mono text-xs mt-3" role="group" aria-label="Agent legend">
      {STACK_ORDER.map((agent) => {
        const hidden = hiddenAgents.includes(agent);
        const total = totals[agent] ?? 0;
        return (
          <button
            key={agent}
            type="button"
            onClick={() => onToggle(agent)}
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 border transition-opacity",
              "rounded-none focus-visible:outline-2 focus-visible:outline-offset-1",
              hidden ? "opacity-40 border-[color:var(--border)]" : "border-[color:var(--border)]"
            )}
            aria-pressed={!hidden}
            aria-label={`${AGENT_LABELS[agent]}: ${formatUsd(total)}, ${hidden ? "hidden" : "visible"}`}
          >
            <span
              aria-hidden="true"
              style={{
                display: "inline-block",
                width: 10,
                height: 10,
                backgroundColor: AGENT_CSS_VARS[agent],
                flexShrink: 0,
              }}
            />
            <span className="text-muted-foreground">{AGENT_LABELS[agent]}</span>
            <span className="text-foreground tabular-nums">{formatUsd(total)}</span>
          </button>
        );
      })}
    </div>
  );
}

// ─── CostTable ────────────────────────────────────────────────────────────────

export interface CostTableRow {
  agent: CostAgent;
  calls: number;
  inputTokens: number;
  outputTokens: number;
  totalUsd: number;
}

type SortKey = keyof CostTableRow;

interface CostTableProps {
  rows: CostTableRow[];
}

export function CostTable({ rows }: CostTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("totalUsd");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => {
      const av = a[sortKey] as number | string;
      const bv = b[sortKey] as number | string;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [rows, sortKey, sortDir]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const cols: { key: SortKey; label: string }[] = [
    { key: "agent",        label: "agent"       },
    { key: "calls",        label: "calls"       },
    { key: "inputTokens",  label: "in_tokens"   },
    { key: "outputTokens", label: "out_tokens"  },
    { key: "totalUsd",     label: "$"           },
  ];

  return (
    <table className="w-full font-mono text-xs mt-4 border-collapse" aria-label="Per-agent cost table">
      <thead>
        <tr className="border-b border-[color:var(--pipeline-lane-divider)]">
          {cols.map(({ key, label }) => (
            <th
              key={key}
              scope="col"
              className={cn(
                "text-left py-1.5 px-2 text-muted-foreground font-medium cursor-pointer",
                "hover:text-foreground transition-colors select-none",
                "uppercase tracking-widest text-[10px]"
              )}
              onClick={() => handleSort(key)}
              aria-sort={
                sortKey === key
                  ? sortDir === "asc"
                    ? "ascending"
                    : "descending"
                  : "none"
              }
            >
              {label}
              {sortKey === key && (
                <span aria-hidden="true" className="ml-1">
                  {sortDir === "asc" ? "↑" : "↓"}
                </span>
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => (
          <tr
            key={row.agent}
            className="border-b border-[color:var(--pipeline-lane-divider)]/40 hover:bg-accent/30 transition-colors"
          >
            <td className="py-1.5 px-2">
              <span className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    backgroundColor: AGENT_CSS_VARS[row.agent],
                    flexShrink: 0,
                  }}
                />
                {AGENT_LABELS[row.agent]}
              </span>
            </td>
            <td className="py-1.5 px-2 tabular-nums text-muted-foreground">
              {row.calls.toLocaleString()}
            </td>
            <td className="py-1.5 px-2 tabular-nums text-muted-foreground">
              {row.inputTokens >= 1_000_000
                ? `${(row.inputTokens / 1_000_000).toFixed(1)}M`
                : row.inputTokens >= 1_000
                ? `${(row.inputTokens / 1_000).toFixed(0)}k`
                : row.inputTokens}
            </td>
            <td className="py-1.5 px-2 tabular-nums text-muted-foreground">
              {row.outputTokens >= 1_000_000
                ? `${(row.outputTokens / 1_000_000).toFixed(1)}M`
                : row.outputTokens >= 1_000
                ? `${(row.outputTokens / 1_000).toFixed(0)}k`
                : row.outputTokens}
            </td>
            <td className="py-1.5 px-2 tabular-nums text-foreground font-semibold">
              {formatUsd(row.totalUsd)}
            </td>
          </tr>
        ))}
        {sorted.length === 0 && (
          <tr>
            <td colSpan={5} className="py-4 text-center text-muted-foreground">
              no data
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
