"use client";

import type { CSSProperties } from "react";
import type { TempoTriageResult, TempoMailItem } from "@/hooks/useTempo";
import { Hatch, Tag } from "@/components/ops";

interface Props {
  data: TempoTriageResult | null;
  onRefresh: () => void;
  loading: boolean;
}

const BUCKET_LABELS: Record<keyof TempoTriageResult["counts"], string> = {
  action_required: "ACTION",
  info_only: "INFO",
  noise: "NOISE",
};

const BUCKET_KIND: Record<keyof TempoTriageResult["counts"], "ok" | "info" | "default"> = {
  action_required: "ok",
  info_only: "info",
  noise: "default",
};

function MailRow({ item }: { item: TempoMailItem }) {
  const row: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    padding: "8px 12px",
    borderBottom: "1px dashed var(--ops-line)",
    fontFamily: "var(--ops-mono)",
    fontSize: 11,
  };
  return (
    <li style={row}>
      <span
        style={{
          color: "var(--ops-fg)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
        title={item.subject}
      >
        {item.subject || item.id}
      </span>
      {item.from && (
        <span
          style={{
            color: "var(--ops-fg-mute)",
            fontSize: 10,
            letterSpacing: "0.04em",
          }}
        >
          {item.from}
        </span>
      )}
      {item.reason && (
        <span
          style={{
            color: "var(--ops-fg-dim)",
            fontSize: 10,
            fontStyle: "italic",
          }}
        >
          {item.reason}
        </span>
      )}
    </li>
  );
}

export function TriageFeed({ data, onRefresh, loading }: Props) {
  const counts = data?.counts ?? { action_required: 0, info_only: 0, noise: 0 };

  const summaryRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    borderBottom: "1px solid var(--ops-line)",
  };

  return (
    <div>
      <div style={summaryRow}>
        {(Object.keys(BUCKET_LABELS) as (keyof typeof BUCKET_LABELS)[]).map((k) => (
          <Tag key={k} kind={BUCKET_KIND[k]}>
            {BUCKET_LABELS[k]} · {counts[k]}
          </Tag>
        ))}
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          style={{
            marginLeft: "auto",
            background: "transparent",
            border: "1px solid var(--ops-line-bright)",
            color: "var(--ops-fg)",
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            letterSpacing: "0.08em",
            padding: "4px 10px",
            cursor: loading ? "wait" : "pointer",
          }}
        >
          {loading ? "…" : "RUN TRIAGE"}
        </button>
      </div>

      {data && data.action_required.length > 0 ? (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {data.action_required.map((m) => (
            <MailRow key={m.id} item={m} />
          ))}
        </ul>
      ) : (
        <Hatch label={loading ? "TRIAGING…" : "INBOX CLEAR"} height={80} />
      )}
    </div>
  );
}
