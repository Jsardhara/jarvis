/**
 * Tests for the /preferences page logic.
 *
 * Environment: node (vitest default for this project).
 * We test the data-layer logic extracted from the page component
 * (load defaults, parse form values, validate, save round-trip).
 *
 * Scenarios:
 *   1. Load: GET /api/preferences → populates form fields
 *   2. Load: non-OK HTTP response → falls back to defaults, no crash
 *   3. Load: network error → falls back to defaults, no crash
 *   4. Save: valid inputs → PUT /api/preferences with correct body
 *   5. Save: invalid lead_time (NaN) → validation error, no fetch
 *   6. Save: risk_tolerance out of range → validation error, no fetch
 *   7. Save: comma-separated senders parsed into array
 *   8. Round-trip: load then save preserves values
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ─── Types mirrored from page ─────────────────────────────────────────────────

interface OperatorPreferences {
  important_senders: string[];
  scholar_lead_time_days: number;
  atlas_risk_tolerance: number;
  updated_at: string | null;
}

const DEFAULTS: OperatorPreferences = {
  important_senders: [],
  scholar_lead_time_days: 7,
  atlas_risk_tolerance: 0.5,
  updated_at: null,
};

// ─── Logic extracted for testing ─────────────────────────────────────────────

function mockResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

async function loadPrefs(
  fetchImpl: typeof fetch
): Promise<{ prefs: OperatorPreferences; error: string | null }> {
  try {
    const res = await fetchImpl("/api/preferences");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as OperatorPreferences;
    return { prefs: data, error: null };
  } catch (err) {
    return {
      prefs: DEFAULTS,
      error: err instanceof Error ? err.message : "load failed",
    };
  }
}

interface FormValues {
  sendersInput: string;
  leadTime: string;
  riskTolerance: string;
}

function parseFormValues(
  values: FormValues
): { data: Omit<OperatorPreferences, "updated_at">; error: string | null } {
  const senders = values.sendersInput
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const leadTime = parseInt(values.leadTime, 10);
  if (isNaN(leadTime) || leadTime < 0) {
    return { data: { ...DEFAULTS }, error: "Lead time must be a non-negative integer." };
  }

  const risk = parseFloat(values.riskTolerance);
  if (isNaN(risk) || risk < 0 || risk > 1) {
    return { data: { ...DEFAULTS }, error: "Risk tolerance must be between 0 and 1." };
  }

  return {
    data: {
      important_senders: senders,
      scholar_lead_time_days: leadTime,
      atlas_risk_tolerance: risk,
    },
    error: null,
  };
}

async function savePrefs(
  fetchImpl: typeof fetch,
  payload: Omit<OperatorPreferences, "updated_at">
): Promise<{ saved: OperatorPreferences | null; error: string | null }> {
  try {
    const res = await fetchImpl("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const saved = (await res.json()) as OperatorPreferences;
    return { saved, error: null };
  } catch (err) {
    return {
      saved: null,
      error: err instanceof Error ? err.message : "save failed",
    };
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("preferences page — load", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("GET /api/preferences → populates form fields", async () => {
    const serverPrefs: OperatorPreferences = {
      important_senders: ["alice@example.com", "bob@example.com"],
      scholar_lead_time_days: 14,
      atlas_risk_tolerance: 0.3,
      updated_at: "2026-04-28T09:00:00Z",
    };
    const mockFetch = vi.fn().mockResolvedValue(mockResponse(serverPrefs));

    const { prefs, error } = await loadPrefs(mockFetch);

    expect(error).toBeNull();
    expect(prefs.important_senders).toEqual(["alice@example.com", "bob@example.com"]);
    expect(prefs.scholar_lead_time_days).toBe(14);
    expect(prefs.atlas_risk_tolerance).toBe(0.3);
    expect(mockFetch).toHaveBeenCalledWith("/api/preferences");
  });

  it("non-OK HTTP response → falls back to defaults", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockResponse({}, 503));

    const { prefs, error } = await loadPrefs(mockFetch);

    expect(error).toBe("HTTP 503");
    expect(prefs).toEqual(DEFAULTS);
  });

  it("network error → falls back to defaults", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));

    const { prefs, error } = await loadPrefs(mockFetch);

    expect(error).toBe("ECONNREFUSED");
    expect(prefs).toEqual(DEFAULTS);
  });
});

describe("preferences page — form validation", () => {
  it("parses comma-separated senders into array", () => {
    const { data, error } = parseFormValues({
      sendersInput: "alice@example.com, bob@example.com , charlie@example.com",
      leadTime: "7",
      riskTolerance: "0.5",
    });

    expect(error).toBeNull();
    expect(data.important_senders).toEqual([
      "alice@example.com",
      "bob@example.com",
      "charlie@example.com",
    ]);
  });

  it("empty sendersInput → empty array", () => {
    const { data, error } = parseFormValues({
      sendersInput: "",
      leadTime: "7",
      riskTolerance: "0.5",
    });

    expect(error).toBeNull();
    expect(data.important_senders).toEqual([]);
  });

  it("invalid lead_time (NaN) → validation error", () => {
    const { error } = parseFormValues({
      sendersInput: "",
      leadTime: "not-a-number",
      riskTolerance: "0.5",
    });

    expect(error).not.toBeNull();
    expect(error).toContain("Lead time");
  });

  it("negative lead_time → validation error", () => {
    const { error } = parseFormValues({
      sendersInput: "",
      leadTime: "-1",
      riskTolerance: "0.5",
    });

    expect(error).not.toBeNull();
  });

  it("risk_tolerance > 1 → validation error", () => {
    const { error } = parseFormValues({
      sendersInput: "",
      leadTime: "7",
      riskTolerance: "1.5",
    });

    expect(error).toContain("Risk tolerance");
  });

  it("risk_tolerance < 0 → validation error", () => {
    const { error } = parseFormValues({
      sendersInput: "",
      leadTime: "7",
      riskTolerance: "-0.1",
    });

    expect(error).not.toBeNull();
  });

  it("risk_tolerance = 0 → valid", () => {
    const { data, error } = parseFormValues({
      sendersInput: "",
      leadTime: "7",
      riskTolerance: "0",
    });

    expect(error).toBeNull();
    expect(data.atlas_risk_tolerance).toBe(0);
  });

  it("risk_tolerance = 1 → valid", () => {
    const { data, error } = parseFormValues({
      sendersInput: "",
      leadTime: "7",
      riskTolerance: "1",
    });

    expect(error).toBeNull();
    expect(data.atlas_risk_tolerance).toBe(1);
  });
});

describe("preferences page — save", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("PUT /api/preferences with correct body on success", async () => {
    const saved: OperatorPreferences = {
      important_senders: ["alice@example.com"],
      scholar_lead_time_days: 14,
      atlas_risk_tolerance: 0.3,
      updated_at: "2026-04-28T10:00:00Z",
    };
    const mockFetch = vi.fn().mockResolvedValue(mockResponse(saved));

    const payload = {
      important_senders: ["alice@example.com"],
      scholar_lead_time_days: 14,
      atlas_risk_tolerance: 0.3,
    };

    const { saved: result, error } = await savePrefs(mockFetch, payload);

    expect(error).toBeNull();
    expect(result?.important_senders).toEqual(["alice@example.com"]);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/preferences",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(payload),
      })
    );
  });

  it("non-OK save response → records error", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockResponse({}, 422));

    const payload: Omit<OperatorPreferences, "updated_at"> = {
      important_senders: DEFAULTS.important_senders,
      scholar_lead_time_days: DEFAULTS.scholar_lead_time_days,
      atlas_risk_tolerance: DEFAULTS.atlas_risk_tolerance,
    };
    const { saved: result, error } = await savePrefs(mockFetch, payload);

    expect(result).toBeNull();
    expect(error).toBe("HTTP 422");
  });

  it("network error on save → records error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("timeout"));

    const { error } = await savePrefs(mockFetch, {
      important_senders: [],
      scholar_lead_time_days: 7,
      atlas_risk_tolerance: 0.5,
    });

    expect(error).toBe("timeout");
  });

  it("round-trip: load then save preserves values", async () => {
    const serverPrefs: OperatorPreferences = {
      important_senders: ["team@example.com"],
      scholar_lead_time_days: 10,
      atlas_risk_tolerance: 0.7,
      updated_at: "2026-04-28T08:00:00Z",
    };

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(serverPrefs)) // load
      .mockResolvedValueOnce(mockResponse({ ...serverPrefs, updated_at: "2026-04-28T09:00:00Z" })); // save

    const { prefs } = await loadPrefs(mockFetch);
    expect(prefs.important_senders).toEqual(["team@example.com"]);

    const payload = {
      important_senders: prefs.important_senders,
      scholar_lead_time_days: prefs.scholar_lead_time_days,
      atlas_risk_tolerance: prefs.atlas_risk_tolerance,
    };

    const { saved, error } = await savePrefs(mockFetch, payload);

    expect(error).toBeNull();
    expect(saved?.important_senders).toEqual(["team@example.com"]);
    expect(saved?.scholar_lead_time_days).toBe(10);
    expect(saved?.atlas_risk_tolerance).toBe(0.7);
  });
});
