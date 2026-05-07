"use client";

/**
 * /lens — investigation board
 *
 * Search bar dominates the top; results render as evidence cards with
 * numbered source pins; watchlist + query history sit in the right rail.
 */

import type { CSSProperties } from "react";
import { useState } from "react";
import { useLens, type QueryRecord } from "@/hooks/useLens";
import { Panel, AgentGlyph, Tag, Hatch, getAgentIdentity } from "@/components/ops";
import { SearchBar } from "@/components/lens/SearchBar";
import { EvidenceCard } from "@/components/lens/EvidenceCard";
import { WatchlistPanel } from "@/components/lens/WatchlistPanel";
import { QueryHistory } from "@/components/lens/QueryHistory";

const lens = getAgentIdentity("lens")!;

export default function LensPage() {
  const { history, search, busy, error } = useLens();
  const [active, setActive] = useState<QueryRecord | null>(null);

  async function handleSubmit(query: string, mode: "quick" | "deep") {
    const rec = await search(query, mode);
    if (rec) setActive(rec);
  }

  const headerStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 16px",
    borderBottom: "1px solid var(--ops-line)",
    background: "var(--ops-bg-deep)",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <header style={headerStyle}>
        <AgentGlyph agent={lens} size={22} />
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 13,
              letterSpacing: "0.12em",
              color: lens.colorHex,
            }}
          >
            LENS · {lens.role}
          </span>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 10,
              color: "var(--ops-fg-mute)",
              letterSpacing: "0.06em",
            }}
          >
            {lens.tagline}
          </span>
        </div>
        <span style={{ marginLeft: "auto" }}>
          <Tag kind="default">READ-ONLY · NO CONFIRM</Tag>
        </span>
      </header>

      <SearchBar onSubmit={handleSubmit} busy={busy} />

      {error && (
        <div
          style={{
            padding: "8px 16px",
            background: "rgba(255, 90, 90, 0.08)",
            color: "var(--ops-crit)",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          gap: 12,
          padding: 12,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
          <Panel
            title="EVIDENCE"
            trailing={
              active ? (
                <span
                  style={{
                    fontFamily: "var(--ops-mono)",
                    fontSize: 9,
                    color: "var(--ops-fg-mute)",
                    letterSpacing: "0.08em",
                  }}
                >
                  {active.mode.toUpperCase()} · {new Date(active.ts).toLocaleTimeString()}
                </span>
              ) : null
            }
          >
            {active ? (
              <EvidenceCard record={active} />
            ) : busy ? (
              <Hatch label="SEARCHING…" height={140} />
            ) : (
              <Hatch label="NO ACTIVE QUERY — RUN A SEARCH" height={140} />
            )}
          </Panel>

          {history.length > 1 && active && (
            <Panel title="OTHER RECENT" flushBody>
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {history
                  .filter((h) => h.id !== active.id)
                  .slice(0, 3)
                  .map((h) => (
                    <li key={h.id} style={{ borderTop: "1px solid var(--ops-line)" }}>
                      <button
                        type="button"
                        onClick={() => setActive(h)}
                        style={{
                          width: "100%",
                          padding: "10px 12px",
                          background: "transparent",
                          border: "none",
                          cursor: "pointer",
                          textAlign: "left",
                          fontFamily: "var(--ops-mono)",
                          fontSize: 11,
                          color: "var(--ops-fg)",
                        }}
                      >
                        ↺ {h.query}
                      </button>
                    </li>
                  ))}
              </ul>
            </Panel>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Panel title="WATCHLIST" flushBody>
            <WatchlistPanel />
          </Panel>

          <Panel title="QUERY HISTORY" flushBody>
            <QueryHistory history={history} onPick={setActive} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
