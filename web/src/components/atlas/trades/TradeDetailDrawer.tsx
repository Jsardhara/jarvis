"use client";

/**
 * TradeDetailDrawer
 *
 * Right-side slide-in drawer showing full trade lifecycle details.
 * Timeline section extracted to TradeTimeline.tsx.
 *
 * Sections: Header · Order · Risk · P&L · Timeline
 */

import { CSSProperties, useEffect, useState } from "react";
import { Tag } from "@/components/ops/Tag";
import { Panel } from "@/components/ops/Panel";
import { KV } from "@/components/ops/KV";
import { TradeTimeline } from "./TradeTimeline";
import type { SignalData } from "./TradeTimeline";
import type { Trade, TradeStatus } from "@/hooks/useTradeBlotter";

// ─── Constants ────────────────────────────────────────────────────────────────

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

// ─── Signal fetch ─────────────────────────────────────────────────────────────

async function fetchSignal(signalId: string): Promise<SignalData> {
  const res = await fetch(`${JARVIS_API}/api/atlas/signals/${signalId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as SignalData;
}

// ─── Formatting ───────────────────────────────────────────────────────────────

function formatDateTime(iso: string | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  } as Intl.DateTimeFormatOptions);
}

function formatPrice(val: number | undefined): string {
  if (val === undefined) return "—";
  if (val >= 1000)
    return `$${val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `$${val.toFixed(4)}`;
}

function formatPnl(val: number | undefined): string {
  if (val === undefined) return "—";
  return `${val >= 0 ? "+" : ""}$${val.toFixed(2)}`;
}

function formatPct(val: number | undefined): string {
  if (val === undefined) return "—";
  return `${val >= 0 ? "+" : ""}${(val * 100).toFixed(2)}%`;
}

function pnlAccent(val: number | undefined): string | undefined {
  if (val === undefined) return undefined;
  return val >= 0 ? "var(--ops-ok)" : "var(--ops-crit)";
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_TAG: Record<TradeStatus, "ok" | "info" | "crit" | "default" | "amber"> = {
  open: "ok",
  placed: "info",
  closed: "default",
  cancelled: "crit",
};

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div style={{
      height: 12,
      borderRadius: 2,
      background: "var(--ops-bg-elevated)",
      marginBottom: "0.5rem",
      animation: "pipeline-stage-breathe 1.4s ease-in-out infinite",
    } as CSSProperties} />
  );
}

// ─── Drawer ───────────────────────────────────────────────────────────────────

interface TradeDetailDrawerProps {
  trade: Trade | null;
  onClose: () => void;
}

export function TradeDetailDrawer({ trade, onClose }: TradeDetailDrawerProps) {
  const [signal, setSignal] = useState<SignalData | null>(null);
  const [signalLoading, setSignalLoading] = useState(false);
  const [signalError, setSignalError] = useState<string | null>(null);

  useEffect(() => {
    if (!trade?.signal_id) { setSignal(null); return; }
    setSignalLoading(true);
    setSignalError(null);
    fetchSignal(trade.signal_id)
      .then((data) => { setSignal(data); setSignalLoading(false); })
      .catch((err: unknown) => {
        setSignalError(err instanceof Error ? err.message : "Failed to load signal");
        setSignalLoading(false);
      });
  }, [trade?.signal_id]);

  const isOpen = trade !== null;

  return (
    <>
      {isOpen && (
        <div
          onClick={onClose}
          style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(7, 8, 9, 0.6)" } as CSSProperties}
          aria-hidden="true"
        />
      )}

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Trade detail"
        style={{
          position: "fixed",
          top: 0, right: 0, bottom: 0,
          width: 400,
          zIndex: 50,
          background: "var(--ops-bg-panel)",
          borderLeft: "1px solid var(--ops-line-strong)",
          display: "flex",
          flexDirection: "column",
          transform: isOpen ? "translateX(0)" : "translateX(100%)",
          transition: "transform 220ms var(--ease-out-expo)",
          overflowY: "auto",
        } as CSSProperties}
      >
        {trade && (
          <>
            {/* Header */}
            <div style={{ padding: "0.75rem 1rem", borderBottom: "1px solid var(--ops-line)", display: "flex", alignItems: "flex-start", gap: "0.5rem", flexShrink: 0, background: "var(--ops-bg-elevated)" } as CSSProperties}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontFamily: "var(--ops-mono)", fontSize: "0.65rem", color: "var(--ops-fg-dim)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } as CSSProperties}>
                  {trade.trade_id}
                </div>
                <div style={{ fontFamily: "var(--ops-mono)", fontSize: "1rem", fontWeight: 700, color: "var(--ops-fg)", letterSpacing: "0.02em" } as CSSProperties}>
                  {trade.pair}
                </div>
                <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.35rem" }}>
                  <Tag kind={STATUS_TAG[trade.status]}>{trade.status.toUpperCase()}</Tag>
                  <Tag kind={trade.is_paper ? "amber" : "ok"}>{trade.is_paper ? "PAPER" : "LIVE"}</Tag>
                </div>
              </div>
              <button type="button" onClick={onClose} aria-label="Close trade detail"
                style={{ background: "none", border: "1px solid var(--ops-line)", color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)", fontSize: "0.7rem", padding: "0.2rem 0.5rem", cursor: "pointer", flexShrink: 0 } as CSSProperties}>
                ✕
              </button>
            </div>

            {/* Body */}
            <div style={{ flex: 1, overflowY: "auto", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.75rem" } as CSSProperties}>
              <Panel title="ORDER">
                <KV label="Side">{trade.side.toUpperCase()}</KV>
                <KV label="Leverage">{trade.leverage !== undefined ? `${trade.leverage}x` : "—"}</KV>
                <KV label="Requested Size">{(trade.requested_size ?? trade.size).toFixed(4)}</KV>
                <KV label="Filled Size">{trade.filled_size !== undefined ? trade.filled_size.toFixed(4) : "—"}</KV>
                <KV label="Entry">{formatPrice(trade.entry_price)}</KV>
                <KV label="Exit">{formatPrice(trade.exit_price)}</KV>
                <KV label="Fees">{trade.fees !== undefined ? `$${trade.fees.toFixed(4)}` : "—"}</KV>
              </Panel>

              <Panel title="RISK">
                <KV label="Stop Loss">{formatPrice(trade.stop_loss)}</KV>
                <KV label="Take Profit">{formatPrice(trade.take_profit)}</KV>
                <KV label="Close Reason">{trade.close_reason ?? "—"}</KV>
              </Panel>

              <Panel title="P&L">
                <KV label="P&L (USD)" accent={pnlAccent(trade.pnl_usd)}>{formatPnl(trade.pnl_usd)}</KV>
                <KV label="P&L (%)" accent={pnlAccent(trade.pnl_pct)}>{formatPct(trade.pnl_pct)}</KV>
                <KV label="Opened At">{formatDateTime(trade.opened_at)}</KV>
                <KV label="Closed At">{formatDateTime(trade.closed_at)}</KV>
              </Panel>

              <Panel title="TIMELINE">
                {signalLoading ? (
                  <><SkeletonRow /><SkeletonRow /><SkeletonRow /></>
                ) : signalError ? (
                  <div style={{ fontFamily: "var(--ops-mono)", fontSize: "0.68rem", color: "var(--ops-crit)" } as CSSProperties}>
                    Signal load error: {signalError}
                  </div>
                ) : (
                  <TradeTimeline trade={trade} signal={signal} />
                )}
              </Panel>
            </div>
          </>
        )}
      </aside>
    </>
  );
}
