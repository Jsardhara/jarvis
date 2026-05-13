"use client";

import { useAtlasSnapshot } from "@/hooks/useAtlasSnapshot";

/**
 * AtlasDegradedBanner
 *
 * Renders an amber terminal-brutalism banner when /api/atlas/snapshot
 * reports degraded=true (ATLAS service cold or unreachable).
 * Renders null when healthy or still loading the first response.
 *
 * Accessibility: role="alert" + aria-live="polite" so screen readers
 * announce the degraded state without interrupting the user.
 */
export function AtlasDegradedBanner() {
  const { degraded, isLoading } = useAtlasSnapshot();

  // Don't flash on initial load — only show once we know the state
  if (isLoading || !degraded) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      style={{
        // Use --warning token from globals.css; fallback to amber for SSR
        backgroundColor: "color-mix(in oklch, var(--warning, oklch(0.60 0.20 80)) 15%, transparent)",
        borderBottom: "2px solid var(--warning, oklch(0.60 0.20 80))",
        color: "var(--warning, oklch(0.60 0.20 80))",
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        fontSize: "0.75rem",
        letterSpacing: "0.04em",
        padding: "0.45rem 1rem",
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        userSelect: "none",
      }}
    >
      {/* Blinking terminal cursor dot */}
      <span
        aria-hidden="true"
        style={{
          display: "inline-block",
          width: "0.5rem",
          height: "0.5rem",
          borderRadius: "50%",
          backgroundColor: "var(--warning, oklch(0.60 0.20 80))",
          animation: "pipeline-stage-breathe 1.6s ease-in-out infinite",
          flexShrink: 0,
        }}
      />
      <span>
        {"> "}
        <strong>ATLAS OFFLINE</strong>
        {" — showing mock data."}
      </span>
      <span
        style={{
          marginLeft: "auto",
          opacity: 0.65,
          fontSize: "0.7rem",
        }}
      >
        {"Start service: "}
        <code
          style={{
            fontFamily: "inherit",
            backgroundColor: "color-mix(in oklch, var(--warning, oklch(0.60 0.20 80)) 20%, transparent)",
            padding: "0 0.25rem",
            borderRadius: "2px",
          }}
        >
          {process.env.NEXT_PUBLIC_ATLAS_PATH ?? "the atlas project"}
        </code>
      </span>
    </div>
  );
}
