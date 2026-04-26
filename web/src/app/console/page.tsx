"use client";

import { useState } from "react";
import { dispatch, type DispatchResponse } from "@/lib/api";

type LogEntry = {
  ts: string;
  request: string;
  result: DispatchResponse;
};

export default function ConsolePage() {
  const [request, setRequest] = useState("");
  const [log, setLog] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const onSend = async () => {
    const r = request.trim();
    if (!r || loading) return;
    setLoading(true);
    try {
      const result = await dispatch(r);
      setLog((prev) => [{ ts: new Date().toISOString(), request: r, result }, ...prev]);
      setRequest("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h1>Console</h1>
      <p className="muted">Talk to Jarvis. Each request hits /api/dispatch and shows the per-agent envelope.</p>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <textarea
          rows={3}
          placeholder='e.g. "what is on my plate today" or "research RAG eval frameworks"'
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSend();
          }}
        />
        <div style={{ marginTop: "0.5rem", display: "flex", justifyContent: "space-between" }}>
          <span className="muted">Cmd/Ctrl + Enter to send</span>
          <button onClick={onSend} disabled={loading || !request.trim()}>
            {loading ? "Dispatching…" : "Send"}
          </button>
        </div>
      </div>

      {log.map((entry) => (
        <div key={entry.ts} className="card" style={{ marginBottom: "1rem" }}>
          <h2>{entry.request}</h2>
          <p className="muted mono">
            → {entry.result.intent.primary}
            {entry.result.intent.parallel.length > 0 && ` + ${entry.result.intent.parallel.join(", ")}`}{" "}
            ({entry.result.intent.confidence.toFixed(2)})
          </p>
          {entry.result.needs_confirm && (
            <p style={{ color: "var(--severity-warn)" }}>⚠ One or more responses need confirmation.</p>
          )}
          {Object.entries(entry.result.responses).map(([agent, resp]) => (
            <div key={agent} className="row" style={{ flexDirection: "column", alignItems: "stretch", gap: "0.25rem" }}>
              <div>
                <span className="mono muted">{agent}</span> — {resp.action}
              </div>
              <pre className="mono muted" style={{ fontSize: "0.78rem", overflowX: "auto", margin: 0 }}>
                {JSON.stringify(resp.result, null, 2).slice(0, 800)}
              </pre>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}
