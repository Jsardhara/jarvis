/**
 * Tests for AgentNetworkGraph — pure logic layer.
 *
 * Imports the real implementations from graph-data.ts (extracted module),
 * mirroring the test pattern used by AgentStatusRow.test.ts.
 *
 * Scenarios:
 *   1.  All 8 nodes have defined positions in NODE_POSITIONS
 *   2.  Pentagon agents form a valid ring (all distinct from center)
 *   3.  Oracle is at the top (minimum Y among pentagon agents)
 *   4.  Orchestrator is at CX, CY (center)
 *   5.  Kraken is in the top-right quadrant (x > CX, y < CY)
 *   6.  Postgres is at the bottom (maximum Y among all nodes)
 *   7.  edgeKey produces the same key regardless of argument order
 *   8.  EDGES contains oracle → orchestrator edge
 *   9.  EDGES contains trader → kraken edge
 *  10.  EDGES contains all 5 pentagon → orchestrator connections
 *  11.  EDGES contains all 5 pentagon → postgres connections
 *  12.  buildPath returns non-empty SVG path string for valid node pair
 *  13.  buildPath path starts at source node
 *  14.  buildPath path ends at target node
 *  15.  kindColor maps signal → atlas-kind-signal
 *  16.  kindColor maps decision → atlas-kind-decision
 *  17.  kindColor maps order → atlas-kind-order
 *  18.  kindColor maps insight → atlas-kind-insight
 *  19.  kindColor maps status → atlas-kind-status
 *  20.  kindColor maps other → atlas-kind-other
 *  21.  stateDotColor: running → ops-ok
 *  22.  stateDotColor: stale → ops-warn
 *  23.  stateDotColor: error → ops-crit
 *  24.  stateDotColor: unknown → ops-fg-faint
 *  25.  stateDotColor: undefined → ops-fg-faint
 */

import { describe, it, expect } from "vitest";
import type { AgentName } from "@/hooks/useAtlasNetwork";
import {
  W, H, CX, CY, R,
  NODE_POSITIONS, EDGES,
  edgeKey, buildPath, kindColor, stateDotColor,
} from "@/components/atlas/network/graph-data";

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AgentNetworkGraph — node positions", () => {
  const ALL_NODES: AgentName[] = [
    "oracle", "architect", "guardian", "trader", "sage",
    "orchestrator", "kraken", "postgres",
  ];

  it("defines positions for all 8 nodes", () => {
    for (const node of ALL_NODES) {
      const pos = NODE_POSITIONS[node];
      expect(pos).toBeDefined();
      expect(typeof pos.x).toBe("number");
      expect(typeof pos.y).toBe("number");
    }
  });

  it("pentagon agents are all ~R distance from orchestrator center", () => {
    const pentagon: AgentName[] = ["oracle", "architect", "guardian", "trader", "sage"];
    const center = NODE_POSITIONS.orchestrator;
    for (const a of pentagon) {
      const pos = NODE_POSITIONS[a];
      const dist = Math.sqrt((pos.x - center.x) ** 2 + (pos.y - center.y) ** 2);
      expect(dist).toBeGreaterThan(R * 0.9);
      expect(dist).toBeLessThan(R * 1.1);
    }
  });

  it("oracle has minimum Y among pentagon agents (top of pentagon)", () => {
    const pentagon: AgentName[] = ["oracle", "architect", "guardian", "trader", "sage"];
    const oracleY = NODE_POSITIONS.oracle.y;
    for (const a of pentagon) {
      if (a !== "oracle") expect(oracleY).toBeLessThanOrEqual(NODE_POSITIONS[a].y);
    }
  });

  it("orchestrator is at CX, CY (center)", () => {
    expect(NODE_POSITIONS.orchestrator.x).toBe(CX);
    expect(NODE_POSITIONS.orchestrator.y).toBe(CY);
  });

  it("kraken is in top-right quadrant (x > CX, y < CY)", () => {
    const k = NODE_POSITIONS.kraken;
    expect(k.x).toBeGreaterThan(CX);
    expect(k.y).toBeLessThan(CY);
  });

  it("postgres has maximum Y among all nodes (bottom)", () => {
    const pgY = NODE_POSITIONS.postgres.y;
    for (const node of (Object.keys(NODE_POSITIONS) as AgentName[])) {
      expect(pgY).toBeGreaterThanOrEqual(NODE_POSITIONS[node].y);
    }
  });

  it("H constant equals 520 (canvas height)", () => {
    expect(H).toBe(520);
  });

  it("W constant equals 700 (canvas width)", () => {
    expect(W).toBe(700);
  });
});

describe("AgentNetworkGraph — edge utilities", () => {
  it("edgeKey is symmetric (order independent)", () => {
    expect(edgeKey("oracle", "orchestrator")).toBe(edgeKey("orchestrator", "oracle"));
    expect(edgeKey("trader", "kraken")).toBe(edgeKey("kraken", "trader"));
  });

  it("EDGES contains oracle → orchestrator", () => {
    const key = edgeKey("oracle", "orchestrator");
    expect(EDGES.map((e) => edgeKey(e.source, e.target))).toContain(key);
  });

  it("EDGES contains trader → kraken", () => {
    expect(EDGES.map((e) => edgeKey(e.source, e.target))).toContain(edgeKey("trader", "kraken"));
  });

  it("EDGES contains all 5 pentagon → orchestrator connections", () => {
    const pentagon: AgentName[] = ["oracle", "architect", "guardian", "trader", "sage"];
    const edgeKeys = EDGES.map((e) => edgeKey(e.source, e.target));
    for (const agent of pentagon) {
      expect(edgeKeys).toContain(edgeKey(agent, "orchestrator"));
    }
  });

  it("EDGES contains all 5 pentagon → postgres connections", () => {
    const pentagon: AgentName[] = ["oracle", "architect", "guardian", "trader", "sage"];
    const edgeKeys = EDGES.map((e) => edgeKey(e.source, e.target));
    for (const agent of pentagon) {
      expect(edgeKeys).toContain(edgeKey(agent, "postgres"));
    }
  });
});

describe("AgentNetworkGraph — buildPath", () => {
  it("returns a non-empty SVG path for a valid edge", () => {
    const path = buildPath("oracle", "orchestrator");
    expect(path).not.toBe("");
    expect(path).toMatch(/^M \d+ \d+ L \d+ \d+$/);
  });

  it("path starts at oracle position", () => {
    const pos = NODE_POSITIONS.oracle;
    expect(buildPath("oracle", "orchestrator").startsWith(`M ${pos.x} ${pos.y}`)).toBe(true);
  });

  it("path ends at orchestrator position", () => {
    const pos = NODE_POSITIONS.orchestrator;
    expect(buildPath("oracle", "orchestrator").endsWith(`L ${pos.x} ${pos.y}`)).toBe(true);
  });
});

describe("AgentNetworkGraph — kindColor", () => {
  it("signal → var(--atlas-kind-signal)", () => {
    expect(kindColor("signal")).toBe("var(--atlas-kind-signal)");
  });

  it("decision → var(--atlas-kind-decision)", () => {
    expect(kindColor("decision")).toBe("var(--atlas-kind-decision)");
  });

  it("order → var(--atlas-kind-order)", () => {
    expect(kindColor("order")).toBe("var(--atlas-kind-order)");
  });

  it("insight → var(--atlas-kind-insight)", () => {
    expect(kindColor("insight")).toBe("var(--atlas-kind-insight)");
  });

  it("status → var(--atlas-kind-status)", () => {
    expect(kindColor("status")).toBe("var(--atlas-kind-status)");
  });

  it("other → var(--atlas-kind-other)", () => {
    expect(kindColor("other")).toBe("var(--atlas-kind-other)");
  });
});

describe("AgentNetworkGraph — stateDotColor", () => {
  it("running → var(--ops-ok)", () => {
    expect(stateDotColor("running")).toBe("var(--ops-ok)");
  });

  it("stale → var(--ops-warn)", () => {
    expect(stateDotColor("stale")).toBe("var(--ops-warn)");
  });

  it("error → var(--ops-crit)", () => {
    expect(stateDotColor("error")).toBe("var(--ops-crit)");
  });

  it("unknown → var(--ops-fg-faint)", () => {
    expect(stateDotColor("unknown")).toBe("var(--ops-fg-faint)");
  });

  it("undefined → var(--ops-fg-faint)", () => {
    expect(stateDotColor(undefined)).toBe("var(--ops-fg-faint)");
  });
});
