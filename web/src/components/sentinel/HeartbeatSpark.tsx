"use client";

import type { CSSProperties } from "react";
import type { SentinelHeartbeat } from "@/hooks/useSentinelSnapshot";

interface Props {
  heartbeats: SentinelHeartbeat[];
  /** Bars rendered. Older heartbeats than this are dropped. Default 60. */
  width?: number;
}

/**
 * Renders one tick per minute slot — green if a heartbeat landed in that
 * minute, faint if it didn't. Slot 0 = oldest, slot N = current.
 */
export function HeartbeatSpark({ heartbeats, width = 60 }: Props) {
  const now = Date.now();
  const slots: { ts: number; landed: boolean }[] = [];
  for (let i = width - 1; i >= 0; i--) {
    const slotEnd = now - i * 60_000;
    const slotStart = slotEnd - 60_000;
    const landed = heartbeats.some((hb) => {
      const t = new Date(hb.ts).getTime();
      return t >= slotStart && t < slotEnd;
    });
    slots.push({ ts: slotEnd, landed });
  }

  const lastTs =
    heartbeats.length > 0
      ? new Date(heartbeats[heartbeats.length - 1].ts).getTime()
      : null;
  const lastAgeSec = lastTs ? Math.round((now - lastTs) / 1000) : null;
  const live = lastAgeSec !== null && lastAgeSec < 90;

  const wrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    padding: 12,
  };
  const row: CSSProperties = {
    display: "flex",
    alignItems: "flex-end",
    gap: 1,
    height: 28,
  };

  return (
    <div style={wrap}>
      <div style={row}>
        {slots.map((s, i) => (
          <div
            key={i}
            title={new Date(s.ts).toLocaleTimeString()}
            style={{
              flex: 1,
              minWidth: 2,
              height: s.landed ? 24 : 4,
              background: s.landed
                ? "var(--ops-ok)"
                : "var(--ops-line)",
              opacity: s.landed ? 1 : 0.6,
            }}
          />
        ))}
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontFamily: "var(--ops-mono)",
          fontSize: 9,
          color: "var(--ops-fg-mute)",
          letterSpacing: "0.08em",
        }}
      >
        <span>-{width}M</span>
        <span style={{ color: live ? "var(--ops-ok)" : "var(--ops-crit)" }}>
          {lastAgeSec === null ? "OFFLINE" : live ? "LIVE" : `STALE (${lastAgeSec}S)`}
        </span>
        <span>NOW</span>
      </div>
    </div>
  );
}
