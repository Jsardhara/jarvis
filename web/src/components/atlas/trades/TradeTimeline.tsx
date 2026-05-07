"use client";

/**
 * TradeTimeline
 *
 * Four-step lifecycle timeline for a trade:
 *   ORACLE → GUARDIAN → TRADER → SAGE
 *
 * Split from TradeDetailDrawer.tsx to keep each file under 300 lines.
 */

import { CSSProperties } from "react";
import type { Trade } from "@/hooks/useTradeBlotter";

// ─── Signal data shape ────────────────────────────────────────────────────────

export interface SignalData {
  signal_id?: string;
  pair?: string;
  direction?: string;
  confidence?: number;
  created_at?: string;
  [key: string]: unknown;
}

// ─── Step status ──────────────────────────────────────────────────────────────

export type StepStatus = "done" | "pending" | "error";

export function oracleStepStatus(trade: Trade): StepStatus {
  return trade.signal_id ? "done" : "pending";
}

export function guardianStepStatus(trade: Trade): StepStatus {
  if (trade.guardian_approved === true) return "done";
  if (trade.guardian_approved === false) return "error";
  if (trade.status !== "placed") return "done";
  return "pending";
}

export function traderStepStatus(trade: Trade): StepStatus {
  return trade.status === "open" || trade.status === "closed" || trade.status === "placed"
    ? "done"
    : "pending";
}

// ─── Formatting helpers ───────────────────────────────────────────────────────

function formatDateTime(iso: string | undefined): string {
  if (!iso) return "";
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

// ─── TimelineStep ─────────────────────────────────────────────────────────────

interface TimelineStepProps {
  label: string;
  status: StepStatus;
  detail?: string;
}

function TimelineStep({ label, status, detail }: TimelineStepProps) {
  const color =
    status === "done"
      ? "var(--ops-ok)"
      : status === "error"
      ? "var(--ops-crit)"
      : "var(--ops-fg-faint)";

  return (
    <div style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", paddingBottom: "0.6rem" } as CSSProperties}>
      <div
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
          marginTop: 3,
          boxShadow: status === "done" ? `0 0 6px ${color}` : "none",
        } as CSSProperties}
      />
      <div>
        <div style={{
          fontFamily: "var(--ops-mono)",
          fontSize: "0.7rem",
          color: status === "pending" ? "var(--ops-fg-faint)" : "var(--ops-fg)",
          fontWeight: 600,
          letterSpacing: "0.04em",
        } as CSSProperties}>
          {label}
        </div>
        {detail && (
          <div style={{ fontFamily: "var(--ops-mono)", fontSize: "0.65rem", color: "var(--ops-fg-dim)", marginTop: 2 } as CSSProperties}>
            {detail}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface TradeTimelineProps {
  trade: Trade;
  signal: SignalData | null;
}

export function TradeTimeline({ trade, signal }: TradeTimelineProps) {
  const oracleDetail = signal
    ? `${signal.direction ?? ""} · confidence ${
        signal.confidence !== undefined
          ? `${(signal.confidence * 100).toFixed(0)}%`
          : "—"
      } · ${signal.created_at ? formatDateTime(signal.created_at) : ""}`
    : trade.signal_id
    ? trade.signal_id
    : "No signal linked";

  const guardianDetail =
    trade.guardian_approved === true
      ? "Approved"
      : trade.guardian_approved === false
      ? "Rejected"
      : "—";

  return (
    <div style={{ paddingTop: "0.4rem" }}>
      <TimelineStep
        label="ORACLE — Signal"
        status={oracleStepStatus(trade)}
        detail={oracleDetail}
      />
      <TimelineStep
        label="GUARDIAN — Decision"
        status={guardianStepStatus(trade)}
        detail={guardianDetail}
      />
      <TimelineStep
        label="TRADER — Order"
        status={traderStepStatus(trade)}
        detail={`${trade.side.toUpperCase()} ${trade.size.toFixed(4)} @ ${formatPrice(trade.entry_price)}`}
      />
      <TimelineStep
        label="SAGE — Notes"
        status={trade.agent_notes ? "done" : "pending"}
        detail={trade.agent_notes ?? "—"}
      />
    </div>
  );
}
