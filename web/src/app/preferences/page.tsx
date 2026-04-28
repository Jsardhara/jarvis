"use client";

/**
 * /preferences — Operator Preferences
 *
 * GET  /api/preferences  → populate form
 * PUT  /api/preferences  → save changes, toast on success/error
 *
 * OperatorPreferences dataclass:
 *   important_senders: string[]
 *   scholar_lead_time_days: number
 *   atlas_risk_tolerance: number  (0–1)
 *   updated_at: string | null
 */

import { useCallback, useEffect, useState } from "react";
import { Settings2 } from "lucide-react";
import { BreadcrumbNav } from "@/components/breadcrumb-nav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<OperatorPreferences>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form-level string buffers (important_senders is comma-separated)
  const [sendersInput, setSendersInput] = useState("");
  const [leadTime, setLeadTime] = useState("");
  const [riskTolerance, setRiskTolerance] = useState("");

  // ─── Load ───────────────────────────────────────────────────────────────────

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
      // Fall back to defaults so form is still usable
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

  // ─── Save ────────────────────────────────────────────────────────────────────

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

  // ─── Render ──────────────────────────────────────────────────────────────────

  const lastUpdated = prefs.updated_at
    ? new Date(prefs.updated_at).toLocaleString()
    : null;

  return (
    <div className="space-y-6">
      <BreadcrumbNav items={[{ label: "Preferences" }]} />

      <div className="flex items-center gap-2">
        <Settings2 className="h-5 w-5 text-primary" />
        <h1 className="text-xl font-bold">Operator Preferences</h1>
        {lastUpdated && (
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">
            last saved: {lastUpdated}
          </span>
        )}
      </div>

      {loading ? (
        <div className="font-mono text-sm text-muted-foreground animate-pulse">
          loading preferences…
        </div>
      ) : (
        <div className="max-w-xl space-y-8 border border-border bg-card p-6">

          {/* ── Tempo: important senders ────────────────────────────────────── */}
          <fieldset className="space-y-3">
            <legend className="font-mono text-xs uppercase tracking-widest text-muted-foreground border-b border-border pb-1 w-full">
              tempo / mail
            </legend>
            <div className="space-y-1.5">
              <Label htmlFor="important-senders" className="font-mono text-xs">
                important_senders
              </Label>
              <Input
                id="important-senders"
                value={sendersInput}
                onChange={(e) => setSendersInput(e.target.value)}
                placeholder="alice@example.com, bob@example.com"
                className="font-mono text-sm"
              />
              <p className="text-[11px] text-muted-foreground font-mono">
                comma-separated email addresses · inbox will surface these first
              </p>
            </div>
          </fieldset>

          {/* ── Scholar: lead time ──────────────────────────────────────────── */}
          <fieldset className="space-y-3">
            <legend className="font-mono text-xs uppercase tracking-widest text-muted-foreground border-b border-border pb-1 w-full">
              scholar / academics
            </legend>
            <div className="space-y-1.5">
              <Label htmlFor="lead-time" className="font-mono text-xs">
                scholar_lead_time_days
              </Label>
              <Input
                id="lead-time"
                type="number"
                min={0}
                max={365}
                value={leadTime}
                onChange={(e) => setLeadTime(e.target.value)}
                className="font-mono text-sm w-32"
              />
              <p className="text-[11px] text-muted-foreground font-mono">
                days before deadline scholar begins preparing material
              </p>
            </div>
          </fieldset>

          {/* ── Atlas: risk tolerance ────────────────────────────────────────── */}
          <fieldset className="space-y-3">
            <legend className="font-mono text-xs uppercase tracking-widest text-muted-foreground border-b border-border pb-1 w-full">
              atlas / trading
            </legend>
            <div className="space-y-1.5">
              <Label htmlFor="risk-tolerance" className="font-mono text-xs">
                atlas_risk_tolerance
                <span className="ml-2 text-muted-foreground">0.0 → 1.0</span>
              </Label>
              <div className="flex items-center gap-3">
                <input
                  id="risk-tolerance"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value)}
                  className="w-48 accent-primary"
                />
                <Input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value)}
                  className="font-mono text-sm w-24"
                />
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">
                0 = conservative · 1 = aggressive · affects guardian risk check
              </p>
            </div>
          </fieldset>

          {/* ── Submit ───────────────────────────────────────────────────────── */}
          <div className="flex items-center gap-3 pt-2 border-t border-border">
            <Button
              onClick={handleSave}
              disabled={saving || loading}
              className="font-mono"
            >
              {saving ? "saving…" : "save preferences"}
            </Button>
            <Button
              variant="outline"
              onClick={loadPrefs}
              disabled={loading || saving}
              className="font-mono"
            >
              reset
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
