"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function AtlasError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[Atlas Error]", error);
  }, [error]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "3rem 1.5rem",
        textAlign: "center",
        background: "var(--ops-bg-void)",
        minHeight: "60vh",
      }}
    >
      <div
        style={{
          background: "rgba(220, 38, 38, 0.12)",
          padding: "0.75rem",
          borderRadius: 999,
          marginBottom: "1rem",
        }}
      >
        <AlertTriangle className="h-6 w-6" style={{ color: "var(--ops-red, #ef4444)" }} />
      </div>
      <h2 style={{ fontSize: 18, fontWeight: 600, fontFamily: "var(--ops-mono)" }}>
        ATLAS PANEL CRASHED
      </h2>
      <p
        style={{
          fontSize: 12,
          color: "var(--ops-fg-dim)",
          marginTop: 6,
          maxWidth: 420,
          fontFamily: "var(--ops-mono)",
        }}
      >
        {error.message || "render error in atlas subtree — other pages still work"}
      </p>
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <Button variant="outline" size="sm" onClick={reset} className="gap-2">
          <RotateCcw className="h-3.5 w-3.5" />
          Retry panel
        </Button>
        <Button variant="ghost" size="sm" asChild className="gap-2">
          <Link href="/">
            <Home className="h-3.5 w-3.5" />
            Dashboard
          </Link>
        </Button>
      </div>
      {error.digest && (
        <p style={{ fontSize: 10, color: "var(--ops-fg-dim)", marginTop: 12, fontFamily: "var(--ops-mono)" }}>
          digest: <code>{error.digest}</code>
        </p>
      )}
    </div>
  );
}
