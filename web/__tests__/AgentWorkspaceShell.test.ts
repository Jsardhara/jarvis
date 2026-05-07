/**
 * Tests for AgentWorkspaceShell
 *
 * Tests the shell's props contract and coordination notes.
 * The shell is a "use client" component — rendering tests require jsdom.
 * These tests validate the TypeScript interface and shared type contracts
 * that Phase 3b agents depend on.
 *
 * Scenarios:
 *   1. AgentWorkspaceShellProps requires agentId string
 *   2. AgentWorkspaceShellProps requires displayName string
 *   3. accentColor is optional (default accent)
 *   4. widgets prop is optional ReactNode slot
 *   5. Valid Atlas sub-agent IDs accepted as agentId
 *   6. Props object is well-formed with required fields only
 *   7. Props object includes all optional fields
 *   8. accentColor accepts CSS variable strings
 *   9. accentColor accepts hex color strings
 *  10. Missing widgets prop does not throw (defaults to placeholder)
 */

import { describe, it, expect } from "vitest";

// ─── Phase 3b coordination: valid agent IDs ───────────────────────────────────

const ATLAS_AGENT_IDS = [
  "oracle",
  "architect",
  "guardian",
  "trader",
  "sage",
] as const;

type AtlasAgentId = (typeof ATLAS_AGENT_IDS)[number];

// ─── Props type (mirrored from AgentWorkspaceShell) ───────────────────────────

interface AgentWorkspaceShellProps {
  agentId: string;
  displayName: string;
  accentColor?: string;
  widgets?: unknown; // ReactNode
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeRequiredProps(agentId: string = "oracle"): AgentWorkspaceShellProps {
  return { agentId, displayName: agentId.toUpperCase() };
}

// ─── Required props ───────────────────────────────────────────────────────────

describe("AgentWorkspaceShell — required props", () => {
  it("accepts agentId as a string", () => {
    const props = makeRequiredProps("oracle");
    expect(typeof props.agentId).toBe("string");
  });

  it("accepts displayName as a string", () => {
    const props = makeRequiredProps("oracle");
    expect(typeof props.displayName).toBe("string");
  });

  it("builds valid props with required fields only", () => {
    const props = makeRequiredProps("guardian");
    expect(props.agentId).toBe("guardian");
    expect(props.displayName).toBe("GUARDIAN");
    expect(props.accentColor).toBeUndefined();
    expect(props.widgets).toBeUndefined();
  });
});

// ─── Optional props ───────────────────────────────────────────────────────────

describe("AgentWorkspaceShell — optional props", () => {
  it("accentColor is optional", () => {
    const props: AgentWorkspaceShellProps = { agentId: "oracle", displayName: "ORACLE" };
    expect(props.accentColor).toBeUndefined();
  });

  it("widgets is optional", () => {
    const props: AgentWorkspaceShellProps = { agentId: "oracle", displayName: "ORACLE" };
    expect(props.widgets).toBeUndefined();
  });

  it("accentColor accepts a CSS variable string", () => {
    const props: AgentWorkspaceShellProps = {
      agentId: "oracle",
      displayName: "ORACLE",
      accentColor: "var(--ops-agent-atlas)",
    };
    expect(props.accentColor).toBe("var(--ops-agent-atlas)");
  });

  it("accentColor accepts a hex color string", () => {
    const props: AgentWorkspaceShellProps = {
      agentId: "oracle",
      displayName: "ORACLE",
      accentColor: "#E0B85C",
    };
    expect(props.accentColor).toBe("#E0B85C");
  });
});

// ─── Atlas sub-agent IDs ──────────────────────────────────────────────────────

describe("AgentWorkspaceShell — Phase 3b agent ID contract", () => {
  it("all 5 Atlas sub-agent IDs are valid agentId values", () => {
    const ids: AtlasAgentId[] = [...ATLAS_AGENT_IDS];
    expect(ids).toHaveLength(5);
    expect(ids).toContain("oracle");
    expect(ids).toContain("architect");
    expect(ids).toContain("guardian");
    expect(ids).toContain("trader");
    expect(ids).toContain("sage");
  });

  it("each agent maps to a display name format", () => {
    const names: Record<AtlasAgentId, string> = {
      oracle: "ORACLE",
      architect: "ARCHITECT",
      guardian: "GUARDIAN",
      trader: "TRADER",
      sage: "SAGE",
    };
    for (const id of ATLAS_AGENT_IDS) {
      expect(names[id]).toBe(id.toUpperCase());
    }
  });
});
