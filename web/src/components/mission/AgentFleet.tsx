"use client";

import { useMemo } from "react";
import { AgentFleetCard, type AgentFleetCardProps } from "./AgentFleetCard";
import type { InboxEvent } from "@/hooks/useInboxStream";

interface AgentFleetProps {
  events: InboxEvent[];
}

const SLUGS: AgentFleetCardProps["slug"][] = [
  "tempo",
  "scholar",
  "lens",
  "forge",
  "atlas",
  "sentinel",
];

const LABEL: Record<AgentFleetCardProps["slug"], string> = {
  tempo: "TEMPO",
  scholar: "SCHOLAR",
  lens: "LENS",
  forge: "FORGE",
  atlas: "ATLAS",
  sentinel: "SENTINEL",
};

const BUCKET_COUNT = 24; // last hour @ 2.5 min per bucket
const BUCKET_MS = 150_000;

interface PerAgentStats {
  sparkline: number[];
  status: AgentFleetCardProps["status"];
  latencyMs: number;
  queueDepth: number;
}

function computeStats(slug: string, events: InboxEvent[]): PerAgentStats {
  const now = Date.now();
  const buckets = new Array<number>(BUCKET_COUNT).fill(0);
  let lastError = false;
  let lastActiveTs = 0;
  for (const e of events) {
    if (e.agent !== slug) continue;
    const tsRaw =
      typeof e.payload?.["ts"] === "string"
        ? Date.parse(e.payload["ts"] as string)
        : e.ts
          ? Date.parse(e.ts)
          : now;
    const ageMs = now - tsRaw;
    if (ageMs < 0 || ageMs > BUCKET_COUNT * BUCKET_MS) continue;
    const idx = BUCKET_COUNT - 1 - Math.floor(ageMs / BUCKET_MS);
    if (idx >= 0 && idx < BUCKET_COUNT) buckets[idx] += 1;
    const sev = (e.payload?.["severity"] as string) ?? "info";
    if (sev === "alert" || sev === "crit") lastError = true;
    if (tsRaw > lastActiveTs) lastActiveTs = tsRaw;
  }
  const status: AgentFleetCardProps["status"] = lastError
    ? "error"
    : now - lastActiveTs < 30_000
      ? "active"
      : "idle";
  return { sparkline: buckets, status, latencyMs: 0, queueDepth: 0 };
}

export function AgentFleet({ events }: AgentFleetProps) {
  const cards = useMemo(
    () =>
      SLUGS.map((slug) => ({
        slug,
        label: LABEL[slug],
        ...computeStats(slug, events),
      })),
    [events]
  );

  return (
    <aside
      aria-label="Agent fleet"
      className="flex w-full flex-col gap-2 lg:w-[280px]"
    >
      {cards.map((c) => (
        <AgentFleetCard key={c.slug} {...c} />
      ))}
    </aside>
  );
}
