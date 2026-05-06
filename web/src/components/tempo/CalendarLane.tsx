"use client";

import type { CSSProperties } from "react";
import type { TempoEvent } from "@/hooks/useTempo";
import { Hatch } from "@/components/ops";

interface Props {
  events: TempoEvent[];
}

const HOUR_PX = 56;
const START_HOUR = 7;
const END_HOUR = 22;

function ymdHour(iso: string): { hour: number; minute: number } {
  const d = new Date(iso);
  return { hour: d.getHours(), minute: d.getMinutes() };
}

function rowOffset(iso: string): number {
  const { hour, minute } = ymdHour(iso);
  return (hour - START_HOUR + minute / 60) * HOUR_PX;
}

function durationPx(startIso: string, endIso: string): number {
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  const hrs = Math.max(0.25, ms / 3_600_000);
  return hrs * HOUR_PX;
}

export function CalendarLane({ events }: Props) {
  const totalHours = END_HOUR - START_HOUR + 1;
  const totalPx = totalHours * HOUR_PX;

  const filteredEvents = events.filter((ev) => {
    const startH = ymdHour(ev.start).hour;
    return startH >= START_HOUR - 1 && startH <= END_HOUR;
  });

  const containerStyle: CSSProperties = {
    position: "relative",
    height: totalPx,
    paddingLeft: 56,
  };

  return (
    <div style={{ overflowY: "auto", maxHeight: 460 }}>
      {filteredEvents.length === 0 && events.length === 0 && (
        <Hatch label="NO EVENTS TODAY" height={120} />
      )}
      <div style={containerStyle}>
        {Array.from({ length: totalHours }).map((_, i) => {
          const hour = START_HOUR + i;
          return (
            <div
              key={hour}
              style={{
                position: "absolute",
                top: i * HOUR_PX,
                left: 0,
                right: 0,
                borderTop: "1px dashed var(--ops-line)",
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: -7,
                  left: 8,
                  fontFamily: "var(--ops-mono)",
                  fontSize: 9,
                  color: "var(--ops-fg-mute)",
                  letterSpacing: "0.08em",
                  background: "var(--ops-bg-deep)",
                  padding: "0 4px",
                }}
              >
                {String(hour).padStart(2, "0")}:00
              </span>
            </div>
          );
        })}

        {filteredEvents.map((ev) => {
          const top = rowOffset(ev.start);
          const height = Math.min(totalPx - top, durationPx(ev.start, ev.end));
          return (
            <div
              key={ev.id}
              title={`${ev.summary} · ${new Date(ev.start).toLocaleTimeString()}`}
              style={{
                position: "absolute",
                top,
                left: 60,
                right: 12,
                height,
                background: "rgba(124, 182, 232, 0.16)",
                border: "1px solid #7CB6E8",
                padding: "6px 10px",
                fontFamily: "var(--ops-mono)",
                fontSize: 11,
                color: "var(--ops-fg)",
                lineHeight: 1.3,
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
                gap: 2,
              }}
            >
              <span
                style={{
                  fontSize: 10,
                  color: "#7CB6E8",
                  letterSpacing: "0.06em",
                }}
              >
                {new Date(ev.start).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                {" → "}
                {new Date(ev.end).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <span
                style={{
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {ev.summary}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
