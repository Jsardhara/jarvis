"use client";

/**
 * DispatchConfirmDialog
 *
 * Opens when POST /api/dispatch returns needs_confirm: true.
 * Approves via POST /api/confirmations/{id}/approve.
 * Rejects via  POST /api/confirmations/{id}/reject.
 *
 * Terminal-prompt aesthetic: dark surface, monospace summary text,
 * green-bordered approve / red-bordered reject buttons.
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { showError } from "@/lib/toast";
import { apiFetch } from "@/lib/api-client";

// Confirmation approve/reject calls now go through the Next.js proxy
// (`/api/confirmations/[id]/[decision]/route.ts`) so the same auth-token /
// MC_API_TOKEN policy enforced by `web/src/middleware.ts` applies. The
// previous direct `${JARVIS_API}:8765` bypass left the FastAPI port wide
// open if exposed on a LAN.

export interface DispatchConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  confirmationId: string;
  summary: string;
  onApproved: (result: unknown) => void;
  onRejected: () => void;
}

export function DispatchConfirmDialog({
  open,
  onOpenChange,
  confirmationId,
  summary,
  onApproved,
  onRejected,
}: DispatchConfirmDialogProps) {
  const [inflight, setInflight] = useState<"approve" | "reject" | null>(null);

  const busy = inflight !== null;

  async function handleApprove() {
    setInflight("approve");
    try {
      const res = await apiFetch(
        `/api/confirmations/${confirmationId}/approve`,
        { method: "POST" }
      );
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const result: unknown = await res.json();
      onOpenChange(false);
      onApproved(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "approve failed";
      showError(`Confirmation approve failed: ${msg}`);
    } finally {
      setInflight(null);
    }
  }

  async function handleReject() {
    setInflight("reject");
    try {
      const res = await apiFetch(
        `/api/confirmations/${confirmationId}/reject`,
        { method: "POST" }
      );
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      onOpenChange(false);
      onRejected();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "reject failed";
      showError(`Confirmation reject failed: ${msg}`);
    } finally {
      setInflight(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent className="sm:max-w-lg border border-amber-500/40 bg-background p-0 overflow-hidden">
        <DialogHeader className="border-b border-border px-4 pt-4 pb-3">
          <DialogTitle className="flex items-center gap-2 font-mono text-sm text-amber-400 uppercase tracking-widest">
            <span className="text-amber-500">$</span>
            awaiting operator
          </DialogTitle>
        </DialogHeader>

        {/* Terminal body */}
        <div className="bg-black/60 px-4 py-3 font-mono text-xs text-green-400">
          <span className="text-muted-foreground select-none">&gt;&gt; </span>
          {summary}
        </div>

        {/* Confirmation ID badge */}
        <div className="px-4 pb-1 pt-0">
          <span className="font-mono text-[10px] text-muted-foreground/60 uppercase tracking-wider">
            id: {confirmationId}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-4 py-3">
          <Button
            variant="outline"
            size="sm"
            className="border-red-500/60 text-red-500 hover:bg-red-500/10 hover:text-red-400 font-mono"
            onClick={() => void handleReject()}
            disabled={busy}
          >
            {inflight === "reject" ? (
              <span className="inline-block h-3 w-1.5 animate-pulse bg-red-500 align-middle" />
            ) : null}
            reject
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-emerald-500/60 text-emerald-500 hover:bg-emerald-500/10 hover:text-emerald-400 font-mono"
            onClick={() => void handleApprove()}
            disabled={busy}
          >
            {inflight === "approve" ? (
              <span className="inline-block h-3 w-1.5 animate-pulse bg-emerald-500 align-middle" />
            ) : null}
            approve
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
