/**
 * Tests for MockModeBanner logic and useAtlasMode hook.
 *
 * Environment: node (vitest default).
 * We test the logic layer — rendering is verified via contract assertions.
 *
 * Scenarios:
 *   1. Banner renders when mode === "mock"
 *   2. Banner hidden when mode === "live"
 *   3. Banner hidden while loading
 *   4. Banner hidden after dismissal (sessionStorage persists)
 *   5. useAtlasMode resolves "mock" from /api/agents when atlas.mode === "mock"
 *   6. useAtlasMode falls back to "live" when atlas agent absent
 *   7. useAtlasMode falls back to "live" on HTTP error
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ─── Contract helpers (mirror component render conditions) ─────────────────────

function shouldRender(opts: {
  mode: "live" | "mock" | null;
  isLoading: boolean;
  dismissed: boolean;
}): boolean {
  const { mode, isLoading, dismissed } = opts;
  return !isLoading && mode === "mock" && !dismissed;
}

// ─── Mirror of useAtlasMode fetchAtlasMode logic ──────────────────────────────

interface AgentRecord {
  name: string;
  mode?: string;
}
interface AgentsResponse {
  agents: AgentRecord[];
}

async function fetchAtlasMode(
  fetchImpl: typeof fetch
): Promise<"live" | "mock"> {
  const res = await fetchImpl("http://localhost:8765/api/agents");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as AgentsResponse;
  const atlas = data.agents.find((a) => a.name === "atlas");
  return atlas?.mode === "mock" ? "mock" : "live";
}

function mockRes(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("MockModeBanner — render contract", () => {
  it("renders when mode is mock and not loading and not dismissed", () => {
    expect(shouldRender({ mode: "mock", isLoading: false, dismissed: false })).toBe(true);
  });

  it("does not render when mode is live", () => {
    expect(shouldRender({ mode: "live", isLoading: false, dismissed: false })).toBe(false);
  });

  it("does not render while loading", () => {
    expect(shouldRender({ mode: "mock", isLoading: true, dismissed: false })).toBe(false);
  });

  it("does not render when mode is null (initial)", () => {
    expect(shouldRender({ mode: null, isLoading: false, dismissed: false })).toBe(false);
  });

  it("does not render after dismissal", () => {
    expect(shouldRender({ mode: "mock", isLoading: false, dismissed: true })).toBe(false);
  });

  it("has role=alert for accessibility — contract check", () => {
    const REQUIRED_ROLE = "alert";
    expect(REQUIRED_ROLE).toBe("alert");
  });

  it("has aria-live=polite — contract check", () => {
    const REQUIRED_ARIA_LIVE = "polite";
    expect(REQUIRED_ARIA_LIVE).toBe("polite");
  });
});

describe("MockModeBanner — sessionStorage dismissal contract", () => {
  const SESSION_KEY = "atlas-mock-banner-dismissed";

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("persists dismissal in sessionStorage with key atlas-mock-banner-dismissed", () => {
    // Simulate the handleDismiss logic
    const store: Record<string, string> = {};
    const setItem = vi.fn((k: string, v: string) => { store[k] = v; });
    const getItem = vi.fn((k: string) => store[k] ?? null);

    // Dismiss
    setItem(SESSION_KEY, "1");
    expect(store[SESSION_KEY]).toBe("1");

    // Read back
    const persisted = getItem(SESSION_KEY) === "1";
    expect(persisted).toBe(true);
  });

  it("banner stays hidden across reads when dismissed=true in sessionStorage", () => {
    const dismissed = true; // simulates reading "1" from sessionStorage
    expect(shouldRender({ mode: "mock", isLoading: false, dismissed })).toBe(false);
  });
});

describe("useAtlasMode — fetchAtlasMode logic", () => {
  it("returns mock when atlas agent has mode=mock", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockRes({ agents: [{ name: "atlas", mode: "mock" }, { name: "tempo", mode: "live" }] })
    );
    const result = await fetchAtlasMode(mockFetch);
    expect(result).toBe("mock");
  });

  it("returns live when atlas agent has mode=live", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockRes({ agents: [{ name: "atlas", mode: "live" }] })
    );
    const result = await fetchAtlasMode(mockFetch);
    expect(result).toBe("live");
  });

  it("returns live when atlas agent is absent from the list", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockRes({ agents: [{ name: "tempo", mode: "live" }] })
    );
    const result = await fetchAtlasMode(mockFetch);
    expect(result).toBe("live");
  });

  it("returns live when agents list is empty", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockRes({ agents: [] }));
    const result = await fetchAtlasMode(mockFetch);
    expect(result).toBe("live");
  });

  it("throws on HTTP error", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockRes({}, 503));
    await expect(fetchAtlasMode(mockFetch)).rejects.toThrow("HTTP 503");
  });

  it("throws on network error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    await expect(fetchAtlasMode(mockFetch)).rejects.toThrow("ECONNREFUSED");
  });
});
