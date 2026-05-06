"use client";

import type { CSSProperties, FormEvent } from "react";
import { useState } from "react";
import { Hatch, OpsButton } from "@/components/ops";
import { useWatchlist } from "@/hooks/useLens";

export function WatchlistPanel() {
  const { items, loading, error, add, remove } = useWatchlist();
  const [draft, setDraft] = useState("");

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    void add(draft);
    setDraft("");
  }

  const inputRow: CSSProperties = {
    display: "flex",
    gap: 6,
    padding: "8px 12px",
    borderBottom: "1px solid var(--ops-line)",
  };

  const itemRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "6px 12px",
    fontFamily: "var(--ops-mono)",
    fontSize: 11,
    borderBottom: "1px dashed var(--ops-line)",
  };

  return (
    <div>
      <form onSubmit={handleAdd} style={inputRow}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="add term…"
          style={{
            flex: 1,
            background: "var(--ops-bg)",
            border: "1px solid var(--ops-line)",
            outline: "none",
            color: "var(--ops-fg)",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            padding: "4px 8px",
          }}
        />
        <OpsButton type="submit" variant="default" disabled={!draft.trim()}>
          ADD
        </OpsButton>
      </form>

      {loading ? (
        <div
          style={{
            padding: 16,
            textAlign: "center",
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-mute)",
          }}
        >
          LOADING…
        </div>
      ) : error ? (
        <div
          style={{
            padding: 16,
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-crit)",
          }}
        >
          {error}
        </div>
      ) : items.length === 0 ? (
        <Hatch label="EMPTY WATCHLIST" height={60} />
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {items.map((term) => (
            <li key={term} style={itemRow}>
              <span style={{ color: "var(--ops-fg)" }}>{term}</span>
              <button
                type="button"
                onClick={() => void remove(term)}
                aria-label={`remove ${term}`}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--ops-fg-mute)",
                  fontFamily: "var(--ops-mono)",
                  fontSize: 11,
                  letterSpacing: "0.08em",
                  padding: 0,
                }}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
