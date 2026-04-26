"use client";

export type SwimlaneEvent = {
  id: string;
  agent: string;
  action: string;
  status: "running" | "done" | "error" | "proposed";
  ts: string;
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
        return (
          <div className="swimlane-row" key={agent}>
            <span className="swimlane-label">{agent}</span>
            <div className="swimlane-track">
              {lane.length === 0 ? (
                <span className="muted" style={{ fontSize: "0.72rem" }}>—</span>
              ) : (
                lane.map((e) => (
                  <span
                    key={e.id}
                    className="swimlane-block"
                    data-status={e.status}
                    title={`${e.action} • ${new Date(e.ts).toLocaleTimeString()}`}
                  >
                    {e.action}
                  </span>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
