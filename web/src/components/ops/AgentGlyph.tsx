import { CSSProperties } from "react";
import type { AgentIdentity } from "./agent-identity";

interface AgentGlyphProps {
  agent: AgentIdentity;
  /** Outer square pixel size; glyph type scales accordingly. */
  size?: number;
  className?: string;
}

/**
 * Bordered monogram badge — the small square with the agent's
 * 2-letter glyph. Hue comes from agent.colorHex, never hardcoded.
 */
export function AgentGlyph({ agent, size = 18, className }: AgentGlyphProps) {
  const style: CSSProperties = {
    width: size,
    height: size,
    border: `1px solid ${agent.colorHex}`,
    color: agent.colorHex,
    fontSize: size < 20 ? 8 : 10,
    fontWeight: 700,
    letterSpacing: "-0.04em",
    fontFamily: "var(--ops-mono)",
  };
  return (
    <span
      className={`inline-grid place-items-center shrink-0 ${className ?? ""}`}
      style={style}
      aria-label={`${agent.name} glyph`}
    >
      {agent.glyph}
    </span>
  );
}
