"use client";

import { CSSProperties, useState } from "react";
import { Bars, Hatch, OpsButton, Panel, Tag } from "@/components/ops";
import type { WeakTopic } from "@/hooks/use-scholar";
import { ApiBanner, fmtTimestamp } from "./shared";

type SortKey = "misses" | "recency" | "concept";

interface WeakTopicsProps {
  topics: WeakTopic[];
  loading: boolean;
  error: string | null;
  onRefetch: () => void;
  onPractice: (concept: string) => void;
}

export function WeakTopics({
  topics,
  loading,
  error,
  onRefetch,
  onPractice,
}: WeakTopicsProps) {
  const [sortBy, setSortBy] = useState<SortKey>("misses");
  const [highlighted, setHighlighted] = useState<string | null>(null);

  const sorted = [...topics].sort((a, b) => {
    if (sortBy === "misses") return b.miss_count - a.miss_count;
    if (sortBy === "recency") {
      return new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime();
    }
    return a.concept.localeCompare(b.concept);
  });

  return (
    <Panel
      title="WEAK TOPICS"
      trailing={
        <Tag kind={topics.length > 0 ? "crit" : "ok"}>
          {loading ? "…" : String(topics.length)}
        </Tag>
      }
      bodyClassName="p-0"
      flushBody
      className="h-full"
    >
      {/* Sort strip */}
      <div
        style={{
          display: "flex",
          gap: 0,
          borderBottom: "1px solid var(--ops-line)",
          background: "var(--ops-bg-deep)",
        } as CSSProperties}
      >
        {(["misses", "recency", "concept"] as SortKey[]).map((key) => (
          <button
            key={key}
            onClick={() => setSortBy(key)}
            style={{
              flex: 1,
              padding: "5px 4px",
              fontFamily: "var(--ops-mono)",
              fontSize: 9,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color:
                sortBy === key ? "var(--ops-fg)" : "var(--ops-fg-faint)",
              background: sortBy === key ? "var(--ops-bg-elevated)" : "transparent",
              borderBottom:
                sortBy === key
                  ? "1px solid var(--ops-amber)"
                  : "1px solid transparent",
              borderRight: key !== "concept" ? "1px solid var(--ops-line)" : "none",
              cursor: "pointer",
              transition: "background 80ms, color 80ms",
            } as CSSProperties}
          >
            {key === "misses" ? "MISSES" : key === "recency" ? "RECENT" : "A–Z"}
          </button>
        ))}
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "calc(100% - 28px)",
          overflowY: "auto",
        } as CSSProperties}
      >
        {error && (
          <div style={{ padding: 14 }}>
            <ApiBanner
              message="Scholar API not ready — retry in a moment"
              onRetry={onRefetch}
            />
          </div>
        )}

        {!error && !loading && topics.length === 0 && (
          <div style={{ padding: 14 }}>
            <Hatch label="NO WEAK TOPICS YET · KEEP SOLVING" height={80} />
          </div>
        )}

        {sorted.map((topic, i) => (
          <TopicRow
            key={topic.concept}
            topic={topic}
            isLast={i === sorted.length - 1}
            isHighlighted={highlighted === topic.concept}
            onPractice={(concept) => {
              setHighlighted(concept);
              onPractice(concept);
            }}
          />
        ))}
      </div>
    </Panel>
  );
}

// ─── Topic row ────────────────────────────────────────────────────────────────

interface TopicRowProps {
  topic: WeakTopic;
  isLast: boolean;
  isHighlighted: boolean;
  onPractice: (concept: string) => void;
}

// Build a 7-bucket bar chart from last_seen (single data point → spike on day)
function buildMissBars(topic: WeakTopic): number[] {
  const bars = Array(7).fill(0) as number[];
  if (!topic.last_seen) return bars;
  const lastSeen = new Date(topic.last_seen);
  const now = Date.now();
  const dayIdx = Math.min(
    6,
    Math.floor((now - lastSeen.getTime()) / (1000 * 60 * 60 * 24)),
  );
  // Place miss_count at the correct bucket (0 = today, 6 = 6 days ago)
  const bucket = Math.max(0, 6 - dayIdx);
  bars[bucket] = topic.miss_count;
  // If we have more than 1 miss, spread a signal across adjacent days
  if (topic.miss_count > 1 && bucket > 0) {
    bars[bucket - 1] = Math.floor(topic.miss_count * 0.4);
  }
  return bars;
}

function TopicRow({ topic, isLast, isHighlighted, onPractice }: TopicRowProps) {
  const bars = buildMissBars(topic);
  const hasBarsData = bars.some((v) => v > 0);

  return (
    <button
      onClick={() => onPractice(topic.concept)}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "10px 14px",
        borderBottom: isLast ? "none" : "1px solid var(--ops-line)",
        background: isHighlighted ? "var(--ops-bg-hover)" : "transparent",
        cursor: "pointer",
        textAlign: "left",
        width: "100%",
        transition: "background 80ms",
        color: "inherit",
        fontFamily: "inherit",
        borderLeft: isHighlighted
          ? "2px solid var(--ops-amber)"
          : "2px solid transparent",
      } as CSSProperties}
      onMouseEnter={(e) => {
        if (!isHighlighted)
          (e.currentTarget as HTMLButtonElement).style.background =
            "var(--ops-bg-hover)";
      }}
      onMouseLeave={(e) => {
        if (!isHighlighted)
          (e.currentTarget as HTMLButtonElement).style.background = "transparent";
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: isHighlighted ? "var(--ops-fg)" : "var(--ops-fg)",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          } as CSSProperties}
        >
          {topic.concept}
        </div>
        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-faint)",
            marginTop: 2,
          } as CSSProperties}
        >
          {fmtTimestamp(topic.last_seen)}
        </div>
      </div>

      {/* Mini bars chart */}
      {hasBarsData && (
        <Bars
          values={bars}
          color="var(--ops-crit)"
          height={20}
        />
      )}

      <Tag kind="crit">{topic.miss_count}×</Tag>
    </button>
  );
}
