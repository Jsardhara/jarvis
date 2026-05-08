"use client";

import { useMemo } from "react";
import type { InboxEvent } from "@/hooks/useInboxStream";

interface ActivitySwimlanesProps {
  events: InboxEvent[];
}

const LANES = ["tempo", "scholar", "lens", "forge", "atlas", "sentinel"] as const;
type Lane = (typeof LANES)[number];

const HUE: Record<Lane, string> = {
  tempo: "var(--ops-agent-tempo)",
  scholar: "var(--ops-agent-scholar)",
  lens: "var(--ops-agent-lens)",
  forge: "var(--ops-agent-forge)",
  atlas: "var(--ops-agent-atlas)",
  sentinel: "var(--ops-agent-sentinel)",
};

const PER_LANE_LIMIT = 6;

function lastN<T>(arr: T[], n: number): T[] {
  return arr.length <= n ? arr : arr.slice(arr.length - n);
}

export function ActivitySwimlanes({ events }: ActivitySwimlanesProps) {
  const lanes = useMemo(() => {
    const grouped: Record<Lane, InboxEvent[]> = {
      tempo: [],
      scholar: [],
      lens: [],
      forge: [],
      atlas: [],
      sentinel: [],
    };
    for (const e of events) {
      const a = e.agent as Lane | undefined;
      if (a && LANES.includes(a)) grouped[a].push(e);
    }
    return LANES.map((lane) => ({
      lane,
      events: lastN(grouped[lane], PER_LANE_LIMIT),
    }));
  }, [events]);

  return (
    <section
      aria-label="Activity swimlanes"
      className="ops-panel grid grid-cols-1 gap-2 px-3 py-2 lg:grid-cols-6"
    >
      {lanes.map(({ lane, events: laneEvents }) => (
        <div key={lane} className="flex flex-col gap-1">
          <header
            className="border-b pb-1 text-[10px] font-mono uppercase"
            style={{
              color: HUE[lane],
              borderColor: HUE[lane],
              borderBottomWidth: "1px",
              opacity: laneEvents.length ? 1 : 0.5,
            }}
          >
            {lane}
          </header>
          {laneEvents.length === 0 ? (
            <p className="font-mono text-[9px] text-[var(--ops-fg-faint)]">
              —
            </p>
          ) : (
            laneEvents.map((e, i) => (
              <p
                key={(e.id ?? "") + i}
                className="font-mono text-[10px] text-[var(--ops-fg-mute)]"
              >
                {e.summary ?? (e.payload?.["summary"] as string) ?? "(event)"}
              </p>
            ))
          )}
        </div>
      ))}
    </section>
  );
}
