"use client";

/**
 * AgentInspectorDrawer
 *
 * Right-side slide-in drawer. When agentId !== null, fetches:
 *   GET /api/atlas/agents/{agentId}       — display_name, model, state, recent_activity
 *   GET /api/atlas/agents/{agentId}/memory — KV pairs
 *
 * Shows: header (name + state tag) + recent activity (20 rows) + memory KV table.
 * Loading and error states handled. JSON payload preview is click-to-expand.
 */

import { useEffect, useState, CSSProperties } from "react";
import { Panel } from "@/components/ops/Panel";
import { Tag } from "@/components/ops/Tag";
import {
  fetchWithTimeout,
  formatTime,
  stateColor,
  normalizeMemory,
} from "./drawer-utils";
import type { DrawerData, ActivityItem, MemoryEntry } from "./drawer-utils";

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentInspectorDrawerProps {
  agentId: string | null;
  onClose: () => void;
}

// ─── ExpandableJSON ───────────────────────────────────────────────────────────

function ExpandableJSON({ value }: { value: unknown }) {
  const [expanded, setExpanded] = useState(false);
  if (value === null || value === undefined) {
    return <span style={{ color: "var(--ops-fg-faint)" }}>null</span>;
  }
  if (typeof value !== "object") {
    return (
      <span style={{ color: "var(--ops-fg-mute)", wordBreak: "break-all" }}>
        {JSON.stringify(value)}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={() => setExpanded((v) => !v)}
      style={{
        background: "none", border: "none", padding: 0, cursor: "pointer",
        textAlign: "left", fontFamily: "var(--ops-mono)", fontSize: 10,
        color: "var(--ops-fg-dim)", wordBreak: "break-all", display: "block", width: "100%",
      } as CSSProperties}
      aria-expanded={expanded}
    >
      {expanded ? (
        <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--ops-fg-mute)", fontSize: 10 } as CSSProperties}>
          {JSON.stringify(value, null, 2)}
        </pre>
      ) : (
        <span style={{ color: "var(--ops-amber)", fontSize: 9 }}>{"{...} EXPAND"}</span>
      )}
    </button>
  );
}

// ─── Activity row ─────────────────────────────────────────────────────────────

function ActivityRow({ item, index }: { item: ActivityItem; index: number }) {
  return (
    <div key={item.id ?? index} className="atlas-activity-row">
      <span style={{
        display: "inline-flex", padding: "1px 5px",
        border: "1px solid var(--ops-line-strong)", borderRadius: 2,
        fontSize: 9, letterSpacing: "0.06em", textTransform: "uppercase",
        color: "var(--ops-info)", flexShrink: 0,
        fontFamily: "var(--ops-mono)", whiteSpace: "nowrap",
      } as CSSProperties}>
        {item.event_type ?? "event"}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: "var(--ops-fg-dim)", fontSize: 9, letterSpacing: "0.04em" } as CSSProperties}>
          {formatTime(item.occurred_at ?? item.created_at)}
        </div>
        {item.payload && <div style={{ marginTop: 2 }}><ExpandableJSON value={item.payload} /></div>}
      </div>
    </div>
  );
}

// ─── Memory row ───────────────────────────────────────────────────────────────

function MemoryRow({ entry, index }: { entry: MemoryEntry; index: number }) {
  return (
    <div key={entry.key ?? index} className="atlas-memory-row">
      <div style={{ minWidth: 0 }}>
        <div style={{ color: "var(--ops-fg-mute)", wordBreak: "break-all", fontSize: 10, letterSpacing: "0.04em" } as CSSProperties}>
          {entry.key}
        </div>
        {entry.updated_at && (
          <div style={{ color: "var(--ops-fg-faint)", fontSize: 9, marginTop: 1 } as CSSProperties}>
            {formatTime(entry.updated_at)}
          </div>
        )}
      </div>
      <div style={{ overflow: "hidden", minWidth: 0 }}>
        <ExpandableJSON value={entry.value} />
      </div>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentInspectorDrawer({ agentId, onClose }: AgentInspectorDrawerProps) {
  const [data, setData] = useState<DrawerData>({ detail: null, memory: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!agentId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData({ detail: null, memory: [] });

    void (async () => {
      try {
        const [detailRaw, memoryRaw] = await Promise.all([
          fetchWithTimeout(`${JARVIS_API}/api/atlas/agents/${agentId}`),
          fetchWithTimeout(`${JARVIS_API}/api/atlas/agents/${agentId}/memory`),
        ]);
        if (cancelled) return;
        setData({
          detail: detailRaw as DrawerData["detail"],
          memory: normalizeMemory(memoryRaw),
        });
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "fetch failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [agentId]);

  if (!agentId) return null;

  const { detail, memory } = data;
  const displayName = detail?.display_name ?? detail?.name ?? agentId.toUpperCase();
  const state = detail?.state ?? detail?.agent_status;
  const activity = detail?.recent_activity ?? [];
  const tagKind = stateColor(state);

  return (
    <div className="atlas-inspector-drawer" role="complementary" aria-label={`Inspector: ${agentId}`}>
      <div className="atlas-inspector-header">
        <span style={{ fontFamily: "var(--ops-mono)", fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--ops-fg-mute)", flex: 1 } as CSSProperties}>
          {displayName}
        </span>
        {tagKind && <Tag kind={tagKind}>{(state ?? "").toUpperCase()}</Tag>}
        <button type="button" aria-label="Close inspector" onClick={onClose} className="ops-btn ops-btn-icon" style={{ flexShrink: 0 } as CSSProperties}>
          ×
        </button>
      </div>

      <div className="atlas-inspector-body">
        {loading && (
          <div style={{ color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)", fontSize: 11, textAlign: "center", padding: "20px 0" } as CSSProperties}>
            LOADING...
          </div>
        )}
        {error && (
          <div style={{ color: "var(--ops-crit)", fontFamily: "var(--ops-mono)", fontSize: 11, padding: "8px 0" } as CSSProperties}>
            ERROR: {error}
          </div>
        )}

        {!loading && !error && detail && (
          <>
            <Panel title="IDENTITY">
              {detail.model && (
                <div className="atlas-memory-row">
                  <span style={{ color: "var(--ops-fg-dim)" }}>MODEL</span>
                  <span style={{ color: "var(--ops-fg-mute)", wordBreak: "break-all" }}>{detail.model}</span>
                </div>
              )}
              <div className="atlas-memory-row">
                <span style={{ color: "var(--ops-fg-dim)" }}>LAST HB</span>
                <span style={{ color: "var(--ops-fg-mute)" }}>{formatTime(detail.last_heartbeat)}</span>
              </div>
            </Panel>

            <Panel title="RECENT ACTIVITY" trailing={<span style={{ color: "var(--ops-fg-faint)", fontSize: 10 }}>{activity.length}</span>}>
              {activity.length === 0 ? (
                <div style={{ color: "var(--ops-fg-faint)", fontFamily: "var(--ops-mono)", fontSize: 10 }}>NO ACTIVITY</div>
              ) : (
                <div>{activity.slice(0, 20).map((item, i) => <ActivityRow key={item.id ?? i} item={item} index={i} />)}</div>
              )}
            </Panel>

            <Panel title="MEMORY" trailing={<span style={{ color: "var(--ops-fg-faint)", fontSize: 10 }}>{memory.length}</span>}>
              {memory.length === 0 ? (
                <div style={{ color: "var(--ops-fg-faint)", fontFamily: "var(--ops-mono)", fontSize: 10 }}>NO MEMORY ENTRIES</div>
              ) : (
                <div>{memory.map((entry, i) => <MemoryRow key={entry.key ?? i} entry={entry} index={i} />)}</div>
              )}
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}
