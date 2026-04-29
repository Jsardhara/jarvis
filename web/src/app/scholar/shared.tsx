"use client";

/**
 * Shared primitives for the /scholar workspace.
 */

import { CSSProperties } from "react";
import { Dot, OpsButton } from "@/components/ops";

// ─── API-not-ready banner ────────────────────────────────────────────────────

interface ApiBannerProps {
  message: string;
  onRetry: () => void;
}

export function ApiBanner({ message, onRetry }: ApiBannerProps) {
  return (
    <div
      style={{
        border: "1px solid var(--ops-line-strong)",
        borderLeft: "2px solid var(--ops-warn)",
        background: "color-mix(in srgb, var(--ops-warn) 8%, transparent)",
        padding: "8px 12px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        fontFamily: "var(--ops-mono)",
        fontSize: 11,
        color: "var(--ops-warn)",
        letterSpacing: "0.06em",
        borderRadius: 2,
      } as CSSProperties}
    >
      <Dot kind="warn" pulse />
      <span style={{ flex: 1 }}>{message}</span>
      <OpsButton
        style={{ fontSize: 10 } as CSSProperties}
        onClick={onRetry}
      >
        RETRY
      </OpsButton>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function fmtTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function readLS(key: string): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

export function writeLS(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, value);
  } catch {
    // quota exceeded — silently ignore
  }
}
