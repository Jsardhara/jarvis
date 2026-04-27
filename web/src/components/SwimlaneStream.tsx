"use client";

import { TierBadge, type Tier } from "./TierBadge";
import type { VerificationStatus } from "./VerificationPill";

export type SwimlaneEvent = {
  id: string;
  agent: string;
  action: string;
  status: "running" | "done" | "error" | "proposed";
  ts: string;
  tier?: Tier;
  verification?: VerificationStatus;
};

interface SwimlaneStreamProps {
  agents: string[];
  events: SwimlaneEvent[];
  maxPerLane?: number;
}

export function SwimlaneStream({ agents, events, maxPerLane = 16 }: SwimlaneStreamProps) {
  const grouped = new Map<string, SwimlaneEvent[]>();
  for (const a of agents) grouped.set(a, []);
  for (const e of events) {
    if (!grouped.has(e.agent)) grouped.set(e.agent, []);
    grouped.get(e.agent)!.push(e);
  }

  return (
    <div>
      {agents.map((agent) => {
        const lane = (grouped.get(agent) ?? []).slice(-maxPerLane);
        // Use the most recent event's tier for the label underline color
        const latestTier = lane.length > 0 ? lane[lane.length - 1].tier : undefined;
        return (
          <div
            className="swimlane-row"
            key={agent}
            data-tier={latestTier}
          >
            <span className="swimlane-label">
              {agent}
              <span className="swimlane-label-underline" />
            </span>
            <div className="swimlane-track">
              {lane.length === 0 ? (
                <span className="muted" style={{ fontSize: "0.72rem" }}>—</span>
              ) : (
                lane.map((e) => (
                  <div
                    key={e.id}
                    className="swimlane-block"
                    data-status={e.status}
                  >
                    <div
                      className="swimlane-block-body"
                      title={`${e.action} • ${new Date(e.ts).toLocaleTimeString()}`}
                    >
                      {e.tier !== undefined && <TierBadge tier={e.tier} />}
                      {e.action}
                    </div>
                    <div
                      className="swimlane-vrf-bar"
                      data-vstatus={e.verification ?? "unknown"}
                    />
                  </div>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
