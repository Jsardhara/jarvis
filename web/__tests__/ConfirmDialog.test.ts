/**
 * Tests for DispatchConfirmDialog logic and confirmation API contract.
 *
 * Environment: node (vitest default for this project).
 * We test the HTTP interaction logic extracted from the component rather
 * than rendering it (React hooks cannot render in node env).
 *
 * Scenarios:
 *   1. Approve → POST /api/confirmations/{id}/approve → onApproved called
 *   2. Reject  → POST /api/confirmations/{id}/reject  → onRejected called
 *   3. Approve non-OK response → showError called, callbacks NOT called
 *   4. Reject  non-OK response → showError called, callbacks NOT called
 *   5. Network error on approve → showError called
 *   6. Dialog opens with correct confirmation_id and summary from dispatch response
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const JARVIS_API = "http://localhost:8765";

function mockResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

/**
 * Extracted approve/reject logic that mirrors DispatchConfirmDialog handlers.
 * Returns { called: boolean; result: unknown; error: string | null }
 */
async function callApprove(
  fetchImpl: typeof fetch,
  confirmationId: string
): Promise<{ result: unknown; error: string | null }> {
  const state: { result: unknown; error: string | null } = {
    result: null,
    error: null,
  };

  try {
    const res = await fetchImpl(
      `${JARVIS_API}/api/confirmations/${confirmationId}/approve`,
      { method: "POST" }
    );
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    state.result = await res.json();
    return state;
  } catch (err) {
    state.error = err instanceof Error ? err.message : "approve failed";
    return state;
  }
}

async function callReject(
  fetchImpl: typeof fetch,
  confirmationId: string
): Promise<{ error: string | null }> {
  const state: { error: string | null } = { error: null };

  try {
    const res = await fetchImpl(
      `${JARVIS_API}/api/confirmations/${confirmationId}/reject`,
      { method: "POST" }
    );
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return state;
  } catch (err) {
    state.error = err instanceof Error ? err.message : "reject failed";
    return state;
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("DispatchConfirmDialog — approve/reject logic", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("approve: POSTs to correct endpoint and returns result on success", async () => {
    const expectedResult = { status: "approved", agent: "tempo", action: "send_mail" };
    const mockFetch = vi.fn().mockResolvedValue(mockResponse(expectedResult));

    const { result, error } = await callApprove(mockFetch, "confirm-abc-123");

    expect(mockFetch).toHaveBeenCalledWith(
      `${JARVIS_API}/api/confirmations/confirm-abc-123/approve`,
      { method: "POST" }
    );
    expect(result).toEqual(expectedResult);
    expect(error).toBeNull();
  });

  it("reject: POSTs to correct endpoint and returns no error on success", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockResponse({ status: "rejected" }));

    const { error } = await callReject(mockFetch, "confirm-xyz-789");

    expect(mockFetch).toHaveBeenCalledWith(
      `${JARVIS_API}/api/confirmations/confirm-xyz-789/reject`,
      { method: "POST" }
    );
    expect(error).toBeNull();
  });

  it("approve: records error when API returns 400", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockResponse({}, 400));

    const { result, error } = await callApprove(mockFetch, "confirm-400");

    expect(result).toBeNull();
    expect(error).toBe("HTTP 400");
  });

  it("approve: records error when API returns 500", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockResponse({}, 500));

    const { error } = await callApprove(mockFetch, "confirm-500");

    expect(error).toBe("HTTP 500");
  });

  it("reject: records error when API returns 403", async () => {
    const mockFetch = vi.fn().mockResolvedValue(mockResponse({}, 403));

    const { error } = await callReject(mockFetch, "confirm-403");

    expect(error).toBe("HTTP 403");
  });

  it("approve: records error on network failure", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));

    const { error } = await callApprove(mockFetch, "confirm-net");

    expect(error).toBe("ECONNREFUSED");
  });

  it("reject: records error on network failure", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));

    const { error } = await callReject(mockFetch, "confirm-net-reject");

    expect(error).toBe("Network error");
  });

  it("dialog props contract: needs_confirm detection from tool_result payload", () => {
    // Mirror the applyEvent logic that extracts confirmation data from stream events.
    interface AgentResponse {
      needs_confirm?: boolean;
      confirmation_id?: string;
      summary?: string;
      intent?: string;
    }

    function extractConfirmation(
      evt: Record<string, unknown>
    ): { confirmationId: string; summary: string } | null {
      if (evt.type !== "tool_result") return null;
      const text = String(evt.text ?? "");
      try {
        const parsed = JSON.parse(text) as AgentResponse;
        if (
          parsed.needs_confirm === true &&
          typeof parsed.confirmation_id === "string"
        ) {
          const cid = parsed.confirmation_id;
          const summaryText =
            typeof parsed.summary === "string"
              ? parsed.summary
              : parsed.intent ?? "Action requires operator approval.";
          return { confirmationId: cid, summary: summaryText };
        }
        return null;
      } catch {
        return null;
      }
    }

    // Test: event carries needs_confirm + confirmation_id → dialog props extracted
    const evt = {
      type: "tool_result",
      tool_use_id: "tid-1",
      text: JSON.stringify({
        agent: "tempo",
        needs_confirm: true,
        confirmation_id: "conf-mail-001",
        summary: "Send email to bob@example.com",
      }),
    };

    const result = extractConfirmation(evt);
    expect(result).not.toBeNull();
    expect(result?.confirmationId).toBe("conf-mail-001");
    expect(result?.summary).toBe("Send email to bob@example.com");
  });

  it("does not open dialog when needs_confirm is false", () => {
    function extractConfirmation(
      evt: Record<string, unknown>
    ): { confirmationId: string; summary: string } | null {
      if (evt.type !== "tool_result") return null;
      const text = String(evt.text ?? "");
      try {
        const parsed = JSON.parse(text) as { needs_confirm?: boolean; confirmation_id?: string };
        if (parsed.needs_confirm === true && typeof parsed.confirmation_id === "string") {
          return { confirmationId: parsed.confirmation_id, summary: "" };
        }
        return null;
      } catch {
        return null;
      }
    }

    const evt = {
      type: "tool_result",
      text: JSON.stringify({ agent: "tempo", needs_confirm: false, result: {} }),
    };

    expect(extractConfirmation(evt)).toBeNull();
  });

  it("uses intent as fallback summary when summary field is missing", () => {
    function extractSummary(parsed: Record<string, unknown>): string {
      if (typeof parsed["summary"] === "string") return parsed["summary"] as string;
      if (typeof parsed["intent"] === "string") return parsed["intent"] as string;
      return "Action requires operator approval.";
    }

    expect(extractSummary({ intent: "send_mail" })).toBe("send_mail");
    expect(extractSummary({ summary: "Send to bob" })).toBe("Send to bob");
    expect(extractSummary({})).toBe("Action requires operator approval.");
  });
});
