"use client";

/**
 * MockModeBanner
 *
 * Renders a sticky amber warning banner when Atlas is in mock mode
 * (JARVIS_ATLAS_MODE=mock). Dismissible per-session via sessionStorage.
 *
 * Accessibility: role="alert" + aria-live="polite" so screen readers
 * announce the state change without interrupting the user.
 */

import { useEffect, useState } from "react";
import { useAtlasMode } from "@/hooks/useAtlasMode";

const SESSION_KEY = "atlas-mock-banner-dismissed";

export function MockModeBanner() {
  const { mode, isLoading } = useAtlasMode();
  const [dismissed, setDismissed] = useState(false);

  // Read dismissal state from sessionStorage on mount
  useEffect(() => {
    try {
      setDismissed(sessionStorage.getItem(SESSION_KEY) === "1");
    } catch {
      // sessionStorage unavailable (SSR / private browsing)
    }
  }, []);

  const handleDismiss = () => {
    setDismissed(true);
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      // sessionStorage unavailable
    }
  };

  if (isLoading || mode !== "mock" || dismissed) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      style={{
        backgroundColor:
          "color-mix(in oklch, var(--ops-amber, oklch(0.72 0.18 70)) 12%, transparent)",
        borderBottom: "2px solid var(--ops-amber, oklch(0.72 0.18 70))",
        color: "var(--ops-amber, oklch(0.72 0.18 70))",
        fontFamily: "var(--ops-mono, 'JetBrains Mono', monospace)",
        fontSize: "0.72rem",
        letterSpacing: "0.05em",
        padding: "0.4rem 1rem",
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        userSelect: "none",
        position: "sticky",
        top: 0,
        zIndex: 50,
        flexShrink: 0,
      }}
    >
      {/* Pulsing amber dot */}
      <span
        aria-hidden="true"
        style={{
          display: "inline-block",
          width: "0.45rem",
          height: "0.45rem",
          borderRadius: "50%",
          backgroundColor: "var(--ops-amber, oklch(0.72 0.18 70))",
          animation: "pipeline-stage-breathe 1.6s ease-in-out infinite",
          flexShrink: 0,
        }}
      />

      <span>
        {"[MOCK] "}
        <strong>Atlas in mock mode</strong>
        {
          " — using mock data, no real prices or pipeline activity. Set "
        }
        <code
          style={{
            fontFamily: "inherit",
            backgroundColor:
              "color-mix(in oklch, var(--ops-amber, oklch(0.72 0.18 70)) 18%, transparent)",
            padding: "0 0.22rem",
          }}
        >
          JARVIS_ATLAS_MODE=live
        </code>
        {" and start ATLAS stack to enable."}
      </span>

      <button
        type="button"
        aria-label="Dismiss mock mode banner"
        onClick={handleDismiss}
        style={{
          marginLeft: "auto",
          background: "none",
          border: "1px solid currentColor",
          color: "inherit",
          fontFamily: "inherit",
          fontSize: "0.65rem",
          letterSpacing: "0.08em",
          padding: "0.1rem 0.5rem",
          cursor: "pointer",
          flexShrink: 0,
          opacity: 0.8,
        }}
      >
        DISMISS
      </button>
    </div>
  );
}
