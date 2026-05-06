"use client";

import type { CSSProperties, FormEvent } from "react";
import { useState } from "react";
import { OpsButton, Tag } from "@/components/ops";
import type { LensMode } from "@/hooks/useLens";

interface Props {
  onSubmit: (query: string, mode: LensMode) => void;
  busy: boolean;
  initialQuery?: string;
}

export function SearchBar({ onSubmit, busy, initialQuery = "" }: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [mode, setMode] = useState<LensMode>("quick");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!query.trim() || busy) return;
    onSubmit(query.trim(), mode);
  }

  const wrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    padding: 16,
    borderBottom: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
  };

  const inputRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    border: "1px solid var(--ops-line-bright)",
    background: "var(--ops-bg)",
    padding: "10px 12px",
  };

  const modeRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontFamily: "var(--ops-mono)",
    fontSize: 10,
    color: "var(--ops-fg-mute)",
    letterSpacing: "0.08em",
  };

  return (
    <form onSubmit={handleSubmit} style={wrap}>
      <div style={inputRow}>
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 14,
            color: "#E0859E",
            letterSpacing: "0.1em",
          }}
        >
          ?
        </span>
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search the open web…"
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "var(--ops-fg)",
            fontFamily: "var(--ops-mono)",
            fontSize: 14,
            letterSpacing: "0.02em",
          }}
        />
        <OpsButton type="submit" variant="primary" disabled={busy || !query.trim()}>
          {busy ? "…" : mode === "deep" ? "RESEARCH" : "SEARCH"}
        </OpsButton>
      </div>
      <div style={modeRow}>
        <span>MODE</span>
        <button
          type="button"
          onClick={() => setMode("quick")}
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: 0,
          }}
        >
          <Tag kind={mode === "quick" ? "info" : "default"}>QUICK · 5 RESULTS</Tag>
        </button>
        <button
          type="button"
          onClick={() => setMode("deep")}
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: 0,
          }}
        >
          <Tag kind={mode === "deep" ? "info" : "default"}>DEEP · MULTI-SOURCE</Tag>
        </button>
      </div>
    </form>
  );
}
