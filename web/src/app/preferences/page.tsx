"use client";

/**
 * /preferences — Operator Preferences
 *
 * DISPLAY: density, accent, scanline toggle
 * OPERATOR: important_senders, scholar_lead_time_days, atlas_risk_tolerance
 *   → GET/PUT /api/preferences
 */

import { CSSProperties, useCallback, useEffect, useState } from "react";
import { Panel, SubH, OpsField, OpsInput, OpsTextarea, OpsButton, KV } from "@/components/ops";
import { showSuccess, showError } from "@/lib/toast";
import { apiFetch } from "@/lib/api-client";

// ─── Types ────────────────────────────────────────────────────────────────────

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

type DensityValue = "comfortable" | "compact";
type AccentValue = "amber" | "cyan" | "rose" | "emerald";

const ACCENT_COLORS: Record<AccentValue, string> = {
  amber: "#F2A03D",
  cyan: "#5FD3D3",
  rose: "#E0859E",
  emerald: "#6FCF7F",
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<OperatorPreferences>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form fields
  const [sendersInput, setSendersInput] = useState("");
  const [leadTime, setLeadTime] = useState("");
  const [riskTolerance, setRiskTolerance] = useState("");

  // Display preferences (client-side only)
  const [density, setDensity] = useState<DensityValue>("comfortable");
  const [accent, setAccent] = useState<AccentValue>("amber");
  const [scanline, setScanline] = useState(false);

  // ─── Load ──────────────────────────────────────────────────────────────────

  const loadPrefs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch("/api/preferences");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as OperatorPreferences;
      setPrefs(data);
      setSendersInput(data.important_senders.join(", "));
      setLeadTime(String(data.scholar_lead_time_days));
      setRiskTolerance(String(data.atlas_risk_tolerance));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "load failed";
      showError(`Failed to load preferences: ${msg}`);
      setSendersInput(DEFAULTS.important_senders.join(", "));
      setLeadTime(String(DEFAULTS.scholar_lead_time_days));
      setRiskTolerance(String(DEFAULTS.atlas_risk_tolerance));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPrefs();
  }, [loadPrefs]);

  // ─── Apply display preferences ─────────────────────────────────────────────

  useEffect(() => {
    document.documentElement.setAttribute("data-density", density);
  }, [density]);

  useEffect(() => {
    document.documentElement.style.setProperty(
      "--ops-amber",
      ACCENT_COLORS[accent],
    );
  }, [accent]);

  useEffect(() => {
    if (scanline) {
      document.body.classList.add("ops-scan");
    } else {
      document.body.classList.remove("ops-scan");
    }
  }, [scanline]);

  // ─── Save ──────────────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    const parsedSenders = sendersInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const parsedLeadTime = parseInt(leadTime, 10);
    if (isNaN(parsedLeadTime) || parsedLeadTime < 0) {
      showError("Lead time must be a non-negative integer.");
      return;
    }

    const parsedRisk = parseFloat(riskTolerance);
    if (isNaN(parsedRisk) || parsedRisk < 0 || parsedRisk > 1) {
      showError("Risk tolerance must be between 0 and 1.");
      return;
    }

    const updated: Omit<OperatorPreferences, "updated_at"> = {
      important_senders: parsedSenders,
      scholar_lead_time_days: parsedLeadTime,
      atlas_risk_tolerance: parsedRisk,
    };

    setSaving(true);
    try {
      const res = await apiFetch("/api/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const saved = (await res.json()) as OperatorPreferences;
      setPrefs(saved);
      showSuccess("Preferences saved.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "save failed";
      showError(`Failed to save preferences: ${msg}`);
    } finally {
      setSaving(false);
    }
  }, [sendersInput, leadTime, riskTolerance]);

  // ─── Render ────────────────────────────────────────────────────────────────

  const lastUpdated = prefs.updated_at
    ? new Date(prefs.updated_at).toLocaleString()
    : null;

  return (
    <div
      style={{
        padding: 20,
        display: "flex",
        flexDirection: "column",
        gap: 20,
        maxWidth: 680,
        width: "100%",
      } as CSSProperties}
    >
      {/* title */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 } as CSSProperties}>
        <span
          style={{
            fontFamily: "var(--ops-sans)",
            fontSize: 16,
            fontWeight: 600,
            letterSpacing: "0.08em",
          } as CSSProperties}
        >
          PREFERENCES
        </span>
        {lastUpdated && (
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 9,
              color: "var(--ops-fg-faint)",
              letterSpacing: "0.1em",
              marginLeft: "auto",
            } as CSSProperties}
          >
            LAST SAVED · {lastUpdated}
          </span>
        )}
      </div>

      {loading ? (
        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg-dim)",
            animation: "pulse 1.5s infinite",
          } as CSSProperties}
        >
          Loading preferences…
        </div>
      ) : (
        <>
          {/* ── DISPLAY ────────────────────────────────────────────────────── */}
          <Panel title="DISPLAY">
            {/* Density */}
            <div style={{ marginBottom: 14 } as CSSProperties}>
              <SubH>DENSITY</SubH>
              <div style={{ display: "flex", gap: 6 } as CSSProperties}>
                {(["comfortable", "compact"] as DensityValue[]).map((d) => (
                  <SegButton
                    key={d}
                    active={density === d}
                    onClick={() => setDensity(d)}
                  >
                    {d.toUpperCase()}
                  </SegButton>
                ))}
              </div>
            </div>

            {/* Accent */}
            <div style={{ marginBottom: 14 } as CSSProperties}>
              <SubH>ACCENT</SubH>
              <div style={{ display: "flex", gap: 8, alignItems: "center" } as CSSProperties}>
                {(Object.entries(ACCENT_COLORS) as [AccentValue, string][]).map(([key, hex]) => (
                  <button
                    key={key}
                    onClick={() => setAccent(key)}
                    title={key}
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: 2,
                      background: hex,
                      border: accent === key ? `2px solid var(--ops-fg)` : "2px solid transparent",
                      cursor: "pointer",
                      flexShrink: 0,
                    } as CSSProperties}
                  />
                ))}
                <span
                  style={{
                    fontSize: 9,
                    color: "var(--ops-fg-dim)",
                    fontFamily: "var(--ops-mono)",
                    letterSpacing: "0.1em",
                  } as CSSProperties}
                >
                  {accent.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Scanline */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" } as CSSProperties}>
              <span
                style={{
                  fontSize: 10,
                  letterSpacing: "0.1em",
                  fontFamily: "var(--ops-mono)",
                  color: "var(--ops-fg-dim)",
                } as CSSProperties}
              >
                SCANLINE OVERLAY
              </span>
              <button
                role="switch"
                aria-checked={scanline}
                onClick={() => setScanline((v) => !v)}
                style={{
                  position: "relative",
                  width: 36,
                  height: 20,
                  background: scanline ? "var(--ops-ok)" : "var(--ops-line-strong)",
                  border: "none",
                  borderRadius: 10,
                  cursor: "pointer",
                  transition: "background 150ms",
                } as CSSProperties}
              >
                <span
                  style={{
                    position: "absolute",
                    top: 2,
                    left: scanline ? 17 : 2,
                    width: 16,
                    height: 16,
                    background: "var(--ops-bg-void)",
                    borderRadius: "50%",
                    transition: "left 150ms",
                  } as CSSProperties}
                />
              </button>
            </div>
          </Panel>

          {/* ── OPERATOR ───────────────────────────────────────────────────── */}
          <Panel title="TEMPO / MAIL">
            <OpsField
              label="IMPORTANT_SENDERS"
              hint="Comma-separated email addresses · inbox will surface these first"
            >
              <OpsTextarea
                value={sendersInput}
                onChange={(e) => setSendersInput(e.target.value)}
                placeholder="alice@example.com, bob@example.com"
                rows={3}
              />
            </OpsField>
          </Panel>

          <Panel title="SCHOLAR / ACADEMICS">
            <OpsField
              label="SCHOLAR_LEAD_TIME_DAYS"
              hint="Days before deadline scholar begins preparing material"
            >
              <OpsInput
                type="number"
                min={0}
                max={365}
                value={leadTime}
                onChange={(e) => setLeadTime(e.target.value)}
                style={{ width: 120 } as CSSProperties}
              />
            </OpsField>
          </Panel>

          <Panel title="ATLAS / TRADING">
            <OpsField
              label="ATLAS_RISK_TOLERANCE"
              hint="0 = conservative · 1 = aggressive · affects guardian risk check"
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12 } as CSSProperties}>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value)}
                  style={{ width: 160, accentColor: "var(--ops-amber)" } as CSSProperties}
                />
                <OpsInput
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value)}
                  style={{ width: 80 } as CSSProperties}
                />
              </div>
            </OpsField>
            <div style={{ marginTop: 8 } as CSSProperties}>
              <KV label="CURRENT">{parseFloat(riskTolerance || "0.5").toFixed(2)}</KV>
            </div>
          </Panel>

          {/* ── Actions ────────────────────────────────────────────────────── */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              paddingTop: 4,
              borderTop: "1px solid var(--ops-line)",
            } as CSSProperties}
          >
            <OpsButton
              variant="primary"
              onClick={handleSave}
              disabled={saving || loading}
            >
              {saving ? "SAVING…" : "SAVE PREFERENCES"}
            </OpsButton>
            <OpsButton onClick={loadPrefs} disabled={loading || saving}>
              RESET
            </OpsButton>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Seg button ───────────────────────────────────────────────────────────────

function SegButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? "var(--ops-bg-elevated)" : "transparent",
        border: `1px solid ${active ? "var(--ops-amber)" : "var(--ops-line)"}`,
        color: active ? "var(--ops-amber)" : "var(--ops-fg-mute)",
        padding: "5px 12px",
        fontSize: 10,
        letterSpacing: "0.1em",
        fontFamily: "var(--ops-mono)",
        cursor: "pointer",
        borderRadius: 2,
        transition: "all 100ms",
      } as CSSProperties}
    >
      {children}
    </button>
  );
}
