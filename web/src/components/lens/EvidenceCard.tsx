"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import { Tag } from "@/components/ops";
import type {
  QueryRecord,
  LensQuickSearchResponse,
  LensDeepResearchResponse,
} from "@/hooks/useLens";

interface Props {
  record: QueryRecord;
}

function isQuick(
  r: LensQuickSearchResponse | LensDeepResearchResponse,
): r is LensQuickSearchResponse {
  return Array.isArray((r as LensQuickSearchResponse).results);
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function EvidenceCard({ record }: Props) {
  const [showMd, setShowMd] = useState(false);
  const time = new Date(record.ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const sources: { url: string; title: string; snippet?: string }[] = isQuick(record.result)
    ? record.result.results.map((r) => ({
        url: r.url,
        title: r.title,
        snippet: r.snippet,
      }))
    : record.result.sources;

  const wrap: CSSProperties = {
    border: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 8,
  };

  const header: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap",
  };

  return (
    <div style={wrap}>
      <div style={header}>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-amber)",
            letterSpacing: "0.08em",
          }}
        >
          {time}
        </span>
        <Tag kind={record.mode === "deep" ? "info" : "default"}>
          {record.mode.toUpperCase()}
        </Tag>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 12,
            color: "var(--ops-fg)",
            fontStyle: "italic",
            flex: 1,
            minWidth: 0,
          }}
        >
          “{record.query}”
        </span>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 9,
            color: "var(--ops-fg-mute)",
            letterSpacing: "0.08em",
          }}
        >
          {sources.length} SOURCE{sources.length === 1 ? "" : "S"}
        </span>
      </div>

      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {sources.map((s, i) => (
          <li
            key={`${record.id}-${i}`}
            style={{
              display: "grid",
              gridTemplateColumns: "26px 1fr",
              gap: 10,
              padding: "6px 0",
              borderTop: i === 0 ? "none" : "1px dashed var(--ops-line)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--ops-mono)",
                fontSize: 10,
                color: "#E0859E",
                fontWeight: 600,
                letterSpacing: "0.04em",
                paddingTop: 2,
              }}
            >
              [{i + 1}]
            </span>
            <div style={{ minWidth: 0 }}>
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                style={{
                  color: "var(--ops-fg)",
                  fontSize: 12,
                  textDecoration: "none",
                  fontFamily: "var(--ops-sans)",
                  display: "block",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
                title={s.title}
              >
                {s.title}
              </a>
              <span
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 10,
                  color: "var(--ops-fg-mute)",
                  letterSpacing: "0.04em",
                }}
              >
                {domainOf(s.url)}
              </span>
              {s.snippet && (
                <p
                  style={{
                    margin: "4px 0 0",
                    fontFamily: "var(--ops-sans)",
                    fontSize: 11,
                    color: "var(--ops-fg-dim)",
                    fontStyle: "italic",
                    lineHeight: 1.4,
                  }}
                >
                  {s.snippet}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>

      {record.result.markdown && (
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            paddingTop: 4,
            borderTop: "1px solid var(--ops-line)",
          }}
        >
          <button
            type="button"
            onClick={() => setShowMd((v) => !v)}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontFamily: "var(--ops-mono)",
              fontSize: 9,
              color: "var(--ops-info)",
              letterSpacing: "0.08em",
              padding: 0,
            }}
          >
            {showMd ? "× HIDE NOTES" : "▸ SHOW NOTES"}
          </button>
        </div>
      )}
      {showMd && (
        <pre
          style={{
            margin: 0,
            padding: 8,
            background: "var(--ops-bg)",
            border: "1px solid var(--ops-line)",
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-dim)",
            whiteSpace: "pre-wrap",
            maxHeight: 240,
            overflow: "auto",
          }}
        >
          {record.result.markdown}
        </pre>
      )}
    </div>
  );
}
