"use client";

import type { CSSProperties } from "react";
import { Hatch, Tag } from "@/components/ops";
import type { QueryRecord } from "@/hooks/useLens";

interface Props {
  history: QueryRecord[];
  onPick: (record: QueryRecord) => void;
}

export function QueryHistory({ history, onPick }: Props) {
  if (history.length === 0) {
    return <Hatch label="NO QUERIES YET" height={70} />;
  }

  const row: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 12px",
    fontFamily: "var(--ops-mono)",
    fontSize: 11,
    borderBottom: "1px dashed var(--ops-line)",
    cursor: "pointer",
    background: "transparent",
    border: "none",
    width: "100%",
    textAlign: "left",
  };

  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {history.map((rec) => {
        const time = new Date(rec.ts).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
        return (
          <li key={rec.id}>
            <button type="button" onClick={() => onPick(rec)} style={row}>
              <span style={{ color: "var(--ops-amber)", fontSize: 10 }}>{time}</span>
              <Tag kind={rec.mode === "deep" ? "info" : "default"}>{rec.mode}</Tag>
              <span
                style={{
                  color: "var(--ops-fg)",
                  flex: 1,
                  minWidth: 0,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
                title={rec.query}
              >
                {rec.query}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
