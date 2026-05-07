"use client";

import type { CSSProperties } from "react";
import { useSentinelSnapshot } from "@/hooks/useSentinelSnapshot";

const TICKER_AGENTS = new Set(["atlas", "ledger", "sage"]);

/** Slim 1-line ticker showing the latest atlas/ledger/sage event. */
export function AtlasEventTicker() {
  const { snapshot } = useSentinelSnapshot({ eventsLimit: 30, heartbeatLimit: 5 });
  const recent = snapshot.events
    .filter((e) => TICKER_AGENTS.has(e.agent))
    .slice(-1)[0];

  const wrap: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 16px",
    borderBottom: "1px solid var(--ops-line)",
    fontFamily: "var(--ops-mono)",
    fontSize: 10,
    color: "var(--ops-fg-dim)",
    background: "var(--ops-bg-deep)",
    letterSpacing: "0.06em",
  };

  if (!recent) {
    return (
      <div style={wrap}>
        <span style={{ color: "var(--ops-fg-mute)" }}>SENTINEL · idle — no atlas events yet</span>
      </div>
    );
  }

  const time = new Date(recent.ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div style={wrap}>
      <span style={{ color: "var(--ops-amber)" }}>{time}</span>
      <span style={{ color: "#5FD3D3" }}>SENTINEL ·</span>
      <span style={{ color: "var(--ops-agent-atlas)", letterSpacing: "0.08em" }}>
        {recent.agent.toUpperCase()}
      </span>
      <span
        style={{
          color: "var(--ops-fg)",
          flex: 1,
          minWidth: 0,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
        title={recent.summary}
      >
        {recent.summary}
      </span>
    </div>
  );
}
