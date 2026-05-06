"use client";

/**
 * /tempo — time-sliced day view
 *
 * Left lane: vertical calendar timeline (today)
 * Right lane: triage feed + KPI strip + todo strip
 */

import type { CSSProperties } from "react";
import { useTempoToday, useTempoTriage, useTempoTasks } from "@/hooks/useTempo";
import { Panel, AgentGlyph, Tag, getAgentIdentity } from "@/components/ops";
import { CalendarLane } from "@/components/tempo/CalendarLane";
import { TriageFeed } from "@/components/tempo/TriageFeed";
import { TodoStrip } from "@/components/tempo/TodoStrip";

const tempo = getAgentIdentity("tempo")!;

export default function TempoPage() {
  const calendar = useTempoToday();
  const triage = useTempoTriage();
  const todos = useTempoTasks();

  const headerStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 16px",
    borderBottom: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
  };

  const counts = triage.data?.counts ?? { action_required: 0, info_only: 0, noise: 0 };
  const meetingsToday = calendar.events.length;
  const openTasks = todos.tasks.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <header style={headerStyle}>
        <AgentGlyph agent={tempo} size={22} />
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 13,
              letterSpacing: "0.12em",
              color: tempo.colorHex,
            }}
          >
            TEMPO · {tempo.role}
          </span>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 10,
              color: "var(--ops-fg-mute)",
              letterSpacing: "0.06em",
            }}
          >
            {tempo.tagline}
          </span>
        </div>
        <span style={{ marginLeft: "auto" }}>
          <Tag kind="ok">ACTION · {counts.action_required}</Tag>
        </span>
        <Tag kind="info">MEETINGS · {meetingsToday}</Tag>
        <Tag kind="default">TASKS · {openTasks}</Tag>
      </header>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          display: "grid",
          gridTemplateColumns: "1fr 380px",
          gap: 12,
          padding: 12,
        }}
      >
        <Panel
          title={`CALENDAR · ${new Date().toLocaleDateString([], {
            weekday: "long",
            month: "short",
            day: "numeric",
          })}`}
          flushBody
        >
          {calendar.error ? (
            <div
              style={{
                padding: 16,
                fontFamily: "var(--ops-mono)",
                fontSize: 11,
                color: "var(--ops-crit)",
              }}
            >
              {calendar.error}
            </div>
          ) : (
            <CalendarLane events={calendar.events} />
          )}
        </Panel>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Panel title="MAIL · TRIAGE" flushBody>
            <TriageFeed
              data={triage.data}
              loading={triage.loading}
              onRefresh={() => void triage.refresh()}
            />
          </Panel>

          <Panel title="TASKS · TO DO" flushBody>
            <TodoStrip
              tasks={todos.tasks}
              onAdd={todos.add}
              onComplete={todos.complete}
              loading={todos.loading}
            />
          </Panel>
        </div>
      </div>
    </div>
  );
}
