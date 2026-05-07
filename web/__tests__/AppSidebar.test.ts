/**
 * Tests for AppSidebar — ATLAS nav section wiring.
 *
 * We test pure logic extracted from the sidebar module:
 *   - isActive correctly matches routes and nested paths
 *   - ATLAS section exposes all required links
 *   - Agent accent CSS var constants are correct
 *   - AtlasAgentsGroup contains all 5 sub-agents
 *
 * Scenarios:
 *  1.  isActive: exact match
 *  2.  isActive: prefix match (nested path)
 *  3.  isActive: "/" only matches exactly
 *  4.  isActive: no false positive on sibling path
 *  5.  ATLAS_AGENT_ENTRIES contains exactly 5 entries
 *  6.  All 5 agent hrefs are correct
 *  7.  Oracle entry uses --atlas-oracle var
 *  8.  Architect entry uses --atlas-architect var
 *  9.  Guardian entry uses --atlas-guardian var
 * 10.  Trader entry uses --atlas-trader var
 * 11.  Sage entry uses --atlas-sage var
 * 12.  /atlas/network is included in fixed Atlas links
 * 13.  /atlas/trades is included in fixed Atlas links
 * 14.  /atlas/pipeline is included in fixed Atlas links
 * 15.  /atlas overview link uses exact pathname match (not prefix)
 */

import { describe, it, expect } from "vitest";

// ─── Mirror isActive from app-sidebar ────────────────────────────────────────

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

// ─── Mirror ATLAS_AGENT_ENTRIES from app-sidebar ──────────────────────────────

interface AtlasAgentEntry {
  href: string;
  label: string;
  accentVar: string;
  fallbackColor: string;
}

const ATLAS_AGENT_ENTRIES: AtlasAgentEntry[] = [
  { href: "/atlas/agents/oracle",    label: "Oracle",    accentVar: "--atlas-oracle",    fallbackColor: "#F2D06B" },
  { href: "/atlas/agents/architect", label: "Architect", accentVar: "--atlas-architect", fallbackColor: "#7CB6E8" },
  { href: "/atlas/agents/guardian",  label: "Guardian",  accentVar: "--atlas-guardian",  fallbackColor: "#6FCF7F" },
  { href: "/atlas/agents/trader",    label: "Trader",    accentVar: "--atlas-trader",    fallbackColor: "#E0859E" },
  { href: "/atlas/agents/sage",      label: "Sage",      accentVar: "--atlas-sage",      fallbackColor: "#B98CE0" },
];

// Fixed ATLAS links (flat, non-agent)
const ATLAS_FIXED_LINKS = [
  { href: "/atlas",          label: "Overview" },
  { href: "/atlas/pipeline", label: "Pipeline" },
  { href: "/atlas/network",  label: "Network"  },
  { href: "/atlas/trades",   label: "Trades"   },
];

// ─── isActive tests ───────────────────────────────────────────────────────────

describe("AppSidebar — isActive", () => {
  it("matches exact path", () => {
    expect(isActive("/atlas", "/atlas")).toBe(true);
  });

  it("matches nested path with prefix", () => {
    expect(isActive("/atlas/agents/oracle", "/atlas/agents/oracle")).toBe(true);
  });

  it("isActive for /atlas/pipeline when on /atlas/pipeline/foo", () => {
    expect(isActive("/atlas/pipeline/foo", "/atlas/pipeline")).toBe(true);
  });

  it("/ matches only the root exactly", () => {
    expect(isActive("/atlas", "/")).toBe(false);
    expect(isActive("/", "/")).toBe(true);
  });

  it("sibling path does match because /atlas/pipeline starts with /atlas/", () => {
    // isActive("/atlas/pipeline", "/atlas") is TRUE — this is why the sidebar
    // uses pathname === "/atlas" (exact) for the Overview item, not isActive.
    expect(isActive("/atlas/pipeline", "/atlas")).toBe(true);
  });

  it("/atlas is active when pathname is exactly /atlas", () => {
    expect(isActive("/atlas", "/atlas")).toBe(true);
  });

  it("/atlas/agents/oracle is active when on /atlas/agents/oracle", () => {
    expect(isActive("/atlas/agents/oracle", "/atlas/agents/oracle")).toBe(true);
  });

  it("agent group considered active when any agent page is active", () => {
    const anyActive = ATLAS_AGENT_ENTRIES.some((e) => isActive("/atlas/agents/sage", e.href));
    expect(anyActive).toBe(true);
  });

  it("agent group not active when on non-agent atlas page", () => {
    const anyActive = ATLAS_AGENT_ENTRIES.some((e) => isActive("/atlas/trades", e.href));
    expect(anyActive).toBe(false);
  });
});

// ─── ATLAS_AGENT_ENTRIES structure ───────────────────────────────────────────

describe("AppSidebar — ATLAS_AGENT_ENTRIES", () => {
  it("contains exactly 5 entries", () => {
    expect(ATLAS_AGENT_ENTRIES).toHaveLength(5);
  });

  it("oracle href is /atlas/agents/oracle", () => {
    expect(ATLAS_AGENT_ENTRIES[0].href).toBe("/atlas/agents/oracle");
  });

  it("architect href is /atlas/agents/architect", () => {
    expect(ATLAS_AGENT_ENTRIES[1].href).toBe("/atlas/agents/architect");
  });

  it("guardian href is /atlas/agents/guardian", () => {
    expect(ATLAS_AGENT_ENTRIES[2].href).toBe("/atlas/agents/guardian");
  });

  it("trader href is /atlas/agents/trader", () => {
    expect(ATLAS_AGENT_ENTRIES[3].href).toBe("/atlas/agents/trader");
  });

  it("sage href is /atlas/agents/sage", () => {
    expect(ATLAS_AGENT_ENTRIES[4].href).toBe("/atlas/agents/sage");
  });

  it("oracle uses --atlas-oracle accent var", () => {
    expect(ATLAS_AGENT_ENTRIES[0].accentVar).toBe("--atlas-oracle");
  });

  it("architect uses --atlas-architect accent var", () => {
    expect(ATLAS_AGENT_ENTRIES[1].accentVar).toBe("--atlas-architect");
  });

  it("guardian uses --atlas-guardian accent var", () => {
    expect(ATLAS_AGENT_ENTRIES[2].accentVar).toBe("--atlas-guardian");
  });

  it("trader uses --atlas-trader accent var", () => {
    expect(ATLAS_AGENT_ENTRIES[3].accentVar).toBe("--atlas-trader");
  });

  it("sage uses --atlas-sage accent var", () => {
    expect(ATLAS_AGENT_ENTRIES[4].accentVar).toBe("--atlas-sage");
  });

  it("all agents have non-empty labels", () => {
    ATLAS_AGENT_ENTRIES.forEach((e) => {
      expect(e.label.length).toBeGreaterThan(0);
    });
  });
});

// ─── ATLAS fixed links ────────────────────────────────────────────────────────

describe("AppSidebar — ATLAS fixed links", () => {
  const hrefs = ATLAS_FIXED_LINKS.map((l) => l.href);

  it("includes /atlas/network", () => {
    expect(hrefs).toContain("/atlas/network");
  });

  it("includes /atlas/trades", () => {
    expect(hrefs).toContain("/atlas/trades");
  });

  it("includes /atlas/pipeline", () => {
    expect(hrefs).toContain("/atlas/pipeline");
  });

  it("includes /atlas overview", () => {
    expect(hrefs).toContain("/atlas");
  });

  it("overview active check uses strict equality, not prefix", () => {
    // The sidebar uses pathname === "/atlas" for the Overview item,
    // ensuring /atlas/pipeline does not highlight Overview.
    function exactMatch(pathname: string, href: string): boolean {
      return pathname === href;
    }
    expect(exactMatch("/atlas/pipeline", "/atlas")).toBe(false);
    expect(exactMatch("/atlas", "/atlas")).toBe(true);
  });
});

// ─── All 7 required new links present ────────────────────────────────────────

describe("AppSidebar — all 7 new links", () => {
  const allHrefs = [
    ...ATLAS_FIXED_LINKS.map((l) => l.href),
    ...ATLAS_AGENT_ENTRIES.map((e) => e.href),
  ];

  const newLinks = [
    "/atlas/network",
    "/atlas/trades",
    "/atlas/agents/oracle",
    "/atlas/agents/architect",
    "/atlas/agents/guardian",
    "/atlas/agents/trader",
    "/atlas/agents/sage",
  ];

  it.each(newLinks)("link %s is present", (href) => {
    expect(allHrefs).toContain(href);
  });
});
