"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function InboxError({ error, reset }: ErrorProps) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <AlertTriangle className="h-6 w-6" style={{ color: "var(--ops-red, #ef4444)" }} />
      <h2 className="mt-3 text-base font-semibold" style={{ fontFamily: "var(--ops-mono)" }}>
        INBOX PANEL CRASHED
      </h2>
      <p className="mt-1 max-w-md text-xs" style={{ color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)" }}>
        {error.message || "render error in inbox subtree"}
      </p>
      <Button variant="outline" size="sm" onClick={reset} className="mt-4 gap-2">
        <RotateCcw className="h-3.5 w-3.5" />
        Retry
      </Button>
    </div>
  );
}
