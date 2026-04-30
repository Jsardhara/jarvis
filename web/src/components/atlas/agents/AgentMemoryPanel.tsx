"use client";

/**
 * AgentMemoryPanel
 *
 * Renders the agent's KV memory as a table:
 *   key | updated_at | value (JSON pretty, max 200 chars, expandable)
 *
 * Keys sorted alphabetically.
 * Empty state shown when memory is empty.
 */

import { useState } from "react";
import { Panel } from "@/components/ops/Panel";
import type { MemoryEntry } from "@/hooks/useAgentMemory";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentMemoryPanelProps {
  memory: Record<string, MemoryEntry>;
  isLoading?: boolean;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  return `${Math.round(diff / 3_600_000)}h ago`;
}

function prettyValue(val: unknown): string {
  try {
    return JSON.stringify(val, null, 2);
  } catch {
    return String(val);
  }
}

// ─── Memory row ───────────────────────────────────────────────────────────────

interface MemoryRowProps {
  memKey: string;
  entry: MemoryEntry;
}

function MemoryRow({ memKey, entry }: MemoryRowProps) {
  const [expanded, setExpanded] = useState(false);
  const full = prettyValue(entry.value);
  const preview = full.length > 200 ? full.slice(0, 200) + "…" : full;

  return (
    <tr>
      <td
        style={{
          fontFamily: "var(--ops-mono)",
          fontSize: 10,
          color: "var(--ops-amber)",
          padding: "6px 10px",
          verticalAlign: "top",
          whiteSpace: "nowrap",
          borderBottom: "1px solid var(--ops-line-faint)",
        }}
      >
        {memKey}
      </td>
      <td
        style={{
          fontFamily: "var(--ops-mono)",
          fontSize: 9,
          color: "var(--ops-fg-faint)",
          padding: "6px 10px",
          verticalAlign: "top",
          whiteSpace: "nowrap",
          borderBottom: "1px solid var(--ops-line-faint)",
        }}
      >
        {relTime(entry.updated_at)}
      </td>
      <td
        style={{
          fontFamily: "var(--ops-mono)",
          fontSize: 10,
          color: "var(--ops-fg-dim)",
          padding: "6px 10px",
          verticalAlign: "top",
          wordBreak: "break-all",
          borderBottom: "1px solid var(--ops-line-faint)",
          maxWidth: 320,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
          <span style={{ flex: 1 }}>
            {expanded ? (
              <pre
                style={{
                  fontFamily: "var(--ops-mono)",
                  fontSize: 10,
                  color: "var(--ops-fg-mute)",
                  background: "var(--ops-bg-void)",
                  border: "1px solid var(--ops-line)",
                  padding: "6px 8px",
                  overflowX: "auto",
                  maxHeight: 200,
                  whiteSpace: "pre-wrap",
                }}
              >
                {full}
              </pre>
            ) : (
              preview
            )}
          </span>
          {full.length > 200 && (
            <button
              onClick={() => setExpanded((e) => !e)}
              aria-label={expanded ? "Collapse value" : "Expand value"}
              style={{
                background: "none",
                border: "none",
                color: "var(--ops-fg-faint)",
                fontFamily: "var(--ops-mono)",
                fontSize: 9,
                cursor: "pointer",
                padding: "0 2px",
                flexShrink: 0,
              }}
            >
              {expanded ? "▲" : "▼"}
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentMemoryPanel({ memory, isLoading }: AgentMemoryPanelProps) {
  const keys = Object.keys(memory).sort();

  return (
    <Panel
      title="MEMORY"
      trailing={
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-faint)",
          }}
        >
          {keys.length} keys
        </span>
      }
      flushBody
      className="agent-memory-panel"
    >
      {isLoading && keys.length === 0 ? (
        <div
          style={{
            padding: 14,
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg-faint)",
          }}
        >
          Loading memory...
        </div>
      ) : keys.length === 0 ? (
        <div
          style={{
            padding: 14,
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg-faint)",
          }}
        >
          No memory entries.
        </div>
      ) : (
        <div style={{ overflowY: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              tableLayout: "fixed",
            }}
          >
            <colgroup>
              <col style={{ width: "28%" }} />
              <col style={{ width: "18%" }} />
              <col style={{ width: "54%" }} />
            </colgroup>
            <thead>
              <tr>
                {["KEY", "UPDATED", "VALUE"].map((h) => (
                  <th
                    key={h}
                    style={{
                      fontFamily: "var(--ops-mono)",
                      fontSize: 9,
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      color: "var(--ops-fg-faint)",
                      padding: "6px 10px",
                      textAlign: "left",
                      borderBottom: "1px solid var(--ops-line)",
                      fontWeight: 600,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <MemoryRow key={k} memKey={k} entry={memory[k]} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
