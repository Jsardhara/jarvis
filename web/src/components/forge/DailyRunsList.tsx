"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import { Tag, Hatch } from "@/components/ops";
import type { ForgeDailyRun } from "@/hooks/useForge";

interface Props {
  runs: ForgeDailyRun[];
}

const STATUS_KIND: Record<string, "ok" | "amber" | "crit" | "default"> = {
  success: "ok",
  failed: "crit",
  blocked: "amber",
  skipped_budget: "amber",
};

export function DailyRunsList({ runs }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (runs.length === 0) {
    return <Hatch label="NO DAILY FORGE RUNS YET" height={120} />;
  }

  const sorted = [...runs].sort((a, b) => b.ts.localeCompare(a.ts));

  const row: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "90px 80px 1fr 120px",
    gap: 10,
    padding: "10px 12px",
    borderBottom: "1px solid var(--ops-line)",
    fontFamily: "var(--ops-mono)",
    fontSize: 11,
    cursor: "pointer",
    background: "transparent",
    border: "none",
    textAlign: "left",
    width: "100%",
    alignItems: "center",
  };

  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {sorted.map((r) => {
        const id = `${r.ts}-${r.spec?.slug ?? r.status}`;
        const expanded = expandedId === id;
        const time = new Date(r.ts).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
        const date = r.date;
        const slug = r.spec?.slug ?? "—";
        const title = r.spec?.title ?? r.error?.split(":")[0] ?? "—";
        return (
          <li key={id} style={{ borderBottom: "1px solid var(--ops-line)" }}>
            <button
              type="button"
              onClick={() => setExpandedId(expanded ? null : id)}
              style={{ ...row, borderBottom: "none" }}
              aria-expanded={expanded}
            >
              <span style={{ color: "var(--ops-amber)" }}>
                {date} {time}
              </span>
              <Tag kind={STATUS_KIND[r.status] ?? "default"}>{r.status}</Tag>
              <span
                style={{
                  color: "var(--ops-fg)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  minWidth: 0,
                }}
                title={title}
              >
                {title}
              </span>
              <span
                style={{
                  color: "var(--ops-fg-mute)",
                  fontSize: 10,
                  letterSpacing: "0.04em",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {slug}
              </span>
            </button>

            {expanded && (
              <div
                style={{
                  padding: "8px 14px 14px",
                  background: "var(--ops-bg)",
                  borderTop: "1px dashed var(--ops-line)",
                }}
              >
                {r.spec?.news_url && (
                  <p
                    style={{
                      margin: "0 0 6px",
                      fontFamily: "var(--ops-mono)",
                      fontSize: 10,
                      color: "var(--ops-fg-mute)",
                      letterSpacing: "0.04em",
                    }}
                  >
                    SOURCE:{" "}
                    <a
                      href={r.spec.news_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: "var(--ops-info)" }}
                    >
                      {r.spec.news_source ?? r.spec.news_url}
                    </a>
                  </p>
                )}
                {r.error && (
                  <pre
                    style={{
                      margin: "0 0 6px",
                      padding: 8,
                      background: "rgba(255, 90, 90, 0.06)",
                      border: "1px solid rgba(255, 90, 90, 0.3)",
                      fontFamily: "var(--ops-mono)",
                      fontSize: 10,
                      color: "var(--ops-crit)",
                      whiteSpace: "pre-wrap",
                      maxHeight: 120,
                      overflow: "auto",
                    }}
                  >
                    {r.error}
                  </pre>
                )}
                {r.spec?.spec_md && (
                  <pre
                    style={{
                      margin: 0,
                      padding: 8,
                      background: "var(--ops-bg-deep)",
                      border: "1px solid var(--ops-line)",
                      fontFamily: "var(--ops-mono)",
                      fontSize: 10,
                      color: "var(--ops-fg-dim)",
                      whiteSpace: "pre-wrap",
                      maxHeight: 280,
                      overflow: "auto",
                    }}
                  >
                    {r.spec.spec_md}
                  </pre>
                )}
                {r.pr_url && (
                  <a
                    href={r.pr_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: "inline-block",
                      marginTop: 8,
                      fontFamily: "var(--ops-mono)",
                      fontSize: 10,
                      color: "#6FCF7F",
                      letterSpacing: "0.06em",
                    }}
                  >
                    → OPEN PR
                  </a>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
