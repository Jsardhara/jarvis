"use client";

import type { CSSProperties, FormEvent } from "react";
import { useState } from "react";
import type { TempoTask } from "@/hooks/useTempo";
import { Hatch, OpsButton } from "@/components/ops";

interface Props {
  tasks: TempoTask[];
  onAdd: (title: string) => Promise<void>;
  onComplete: (taskId: string) => Promise<void>;
  loading: boolean;
}

export function TodoStrip({ tasks, onAdd, onComplete, loading }: Props) {
  const [draft, setDraft] = useState("");

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    void onAdd(draft).then(() => setDraft(""));
  }

  const inputRow: CSSProperties = {
    display: "flex",
    gap: 6,
    padding: "8px 12px",
    borderBottom: "1px solid var(--ops-line)",
  };

  const itemRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    borderBottom: "1px dashed var(--ops-line)",
    fontFamily: "var(--ops-mono)",
    fontSize: 11,
  };

  return (
    <div>
      <form onSubmit={handleAdd} style={inputRow}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="add task…"
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

      {loading && tasks.length === 0 ? (
        <Hatch label="LOADING TASKS…" height={50} />
      ) : tasks.length === 0 ? (
        <Hatch label="NO OPEN TASKS" height={50} />
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {tasks.map((t) => (
            <li key={t.id} style={itemRow}>
              <button
                type="button"
                onClick={() => void onComplete(t.id)}
                aria-label={`complete ${t.title}`}
                style={{
                  width: 14,
                  height: 14,
                  border: "1px solid var(--ops-line-bright)",
                  background: "transparent",
                  cursor: "pointer",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  flex: 1,
                  color: "var(--ops-fg)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
                title={t.title}
              >
                {t.title}
              </span>
              {t.due && (
                <span
                  style={{
                    color: "var(--ops-amber)",
                    fontSize: 10,
                    letterSpacing: "0.06em",
                  }}
                >
                  {new Date(t.due).toLocaleDateString()}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
