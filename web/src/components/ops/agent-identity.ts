/**
 * Agent identity registry — Operations Black aesthetic.
 *
 * Locked subsystem set: tempo · scholar · lens · forge · atlas
 * Plus daemon: sentinel
 *
 * Each agent owns a hue (matched to globals.css --ops-agent-* tokens) and
 * a 2-character glyph shown in nav + workspace headers.
 */

export type AgentId =
  | "jarvis"
  | "tempo"
  | "scholar"
  | "lens"
  | "forge"
  | "atlas"
  | "sentinel";

export interface AgentIdentity {
  id: AgentId;
  name: string;
  /** 2-char monogram for the bordered glyph badge. */
  glyph: string;
  /** Subsystem domain — short, uppercase. */
  role: string;
  /** One-line description. */
  tagline: string;
  /** Resolved hex (mirrors --ops-agent-*). */
  colorHex: string;
  /** CSS var reference for runtime use. */
  colorVar: string;
  /** Default model routing per CLAUDE.md. */
  model: string;
}

export const AGENT_IDENTITIES: Record<AgentId, AgentIdentity> = {
  jarvis: {
    id: "jarvis",
    name: "JARVIS",
    glyph: "JV",
    role: "ORCHESTRATOR",
    tagline: "Routes intents, dispatches the fleet",
    colorHex: "#F2A03D",
    colorVar: "var(--ops-amber)",
    model: "claude-opus-4.7",
  },
  tempo: {
    id: "tempo",
    name: "TEMPO",
    glyph: "TM",
    role: "TIME OPS",
    tagline: "Outlook · mail · calendar · tasks",
    colorHex: "#7CB6E8",
    colorVar: "var(--ops-agent-tempo)",
    model: "claude-sonnet-4.6",
  },
  scholar: {
    id: "scholar",
    name: "SCHOLAR",
    glyph: "SC",
    role: "ACADEMICS",
    tagline: "Coursework · study planning · summaries",
    colorHex: "#B98CE0",
    colorVar: "var(--ops-agent-scholar)",
    model: "claude-sonnet-4.6",
  },
  lens: {
    id: "lens",
    name: "LENS",
    glyph: "LN",
    role: "RESEARCH",
    tagline: "Web research · monitoring · synthesis",
    colorHex: "#E0859E",
    colorVar: "var(--ops-agent-lens)",
    model: "claude-sonnet-4.6",
  },
  forge: {
    id: "forge",
    name: "FORGE",
    glyph: "FG",
    role: "CODE OPS",
    tagline: "Repo work · refactor · PRs",
    colorHex: "#6FCF7F",
    colorVar: "var(--ops-agent-forge)",
    model: "claude-opus-4.7",
  },
  atlas: {
    id: "atlas",
    name: "ATLAS",
    glyph: "AT",
    role: "TRADING",
    tagline: "Oracle → Architect → Guardian → Trader",
    colorHex: "#E0B85C",
    colorVar: "var(--ops-agent-atlas)",
    model: "claude-opus-4.7",
  },
  sentinel: {
    id: "sentinel",
    name: "SENTINEL",
    glyph: "SN",
    role: "DAEMON",
    tagline: "Background scheduler · APScheduler",
    colorHex: "#5FD3D3",
    colorVar: "var(--ops-agent-sentinel)",
    model: "claude-haiku-4.5",
  },
};

export const SUBSYSTEM_AGENTS: AgentId[] = [
  "tempo",
  "scholar",
  "lens",
  "forge",
  "atlas",
];

export function getAgentIdentity(id: string | null | undefined): AgentIdentity | null {
  if (!id) return null;
  return (AGENT_IDENTITIES as Record<string, AgentIdentity>)[id.toLowerCase()] ?? null;
}
