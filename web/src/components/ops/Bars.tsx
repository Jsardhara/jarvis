"use client";

import { CSSProperties } from "react";

interface BarsProps {
  values: number[];
  /** CSS color (hex or var). */
  color?: string;
  height?: number;
  className?: string;
}

/**
 * Mini sparkline — 1px gap stacked bars, height-encoded. No chart lib;
 * keeps bundle lean. Pair with useStreamBars (TODO) for live stream.
 */
export function Bars({
  values,
  color = "var(--ops-fg-faint)",
  height = 18,
  className,
}: BarsProps) {
  const max = Math.max(...values, 1);
  return (
    <div
      className={`ops-bars ${className ?? ""}`}
      style={{ height }}
      role="img"
      aria-label="activity bars"
    >
      {values.map((v, i) => {
        const style: CSSProperties = {
          height: `${(v / max) * 100}%`,
          background: color,
        };
        return <span key={i} style={style} />;
      })}
    </div>
  );
}
