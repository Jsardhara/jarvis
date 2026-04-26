"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import {
  agentHistory,
  dispatchAgent,
  type AgentDescriptor,
  type AgentLogEntry,
  type AgentResponseEnvelope,
} from "@/lib/api";

type ThreadMsg =
  | { who: "user"; text: string; ts: string }
  | { who: "agent"; envelope: AgentResponseEnvelope };

interface AgentDrawerProps {
  agent: AgentDescriptor | null;
  onClose: () => void;
}

export function AgentDrawer({ agent, onClose }: AgentDrawerProps) {
  const [text, setText] = useState("");
  const [thread, setThread] = useState<ThreadMsg[]>([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (agent) {
      setThread([]);
      setText("");
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [agent]);

  const { data: history } = useSWR<AgentLogEntry[]>(
    agent ? `agent-history:${agent.name}` : null,
    () => (agent ? agentHistory(agent.name, 20) : Promise.resolve([])),
    { refreshInterval: 5000 }
  );

  if (!agent) return null;

  const send = async () => {
    if (!text.trim()) return;
    const userMsg: ThreadMsg = { who: "user", text, ts: new Date().toISOString() };
    setThread((t) => [...t, userMsg]);
    const sent = text;
    setText("");
    setBusy(true);
    try {
      const envelope = await dispatchAgent(agent.name, { text: sent });
      setThread((t) => [...t, { who: "agent", envelope }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "unknown error";
      setThread((t) => [
        ...t,
        {
          who: "agent",
          envelope: {
            agent: agent.name,
            intent: "error",
            action: "errored",
            result: { error: msg },
            follow_ups: [],
            confidence: 0,
            needs_confirm: false,
            request_id: "",
            ts: new Date().toISOString(),
          },
        },
      ]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const triggerAction = async (action: string) => {
    setBusy(true);
    try {
      const envelope = await dispatchAgent(agent.name, { action });
      setThread((t) => [
        ...t,
        { who: "user", text: `/${action}`, ts: new Date().toISOString() },
        { who: "agent", envelope },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`${agent.name} drawer`}>
        <header className="drawer-head">
          <div>
            <div className="name">{agent.name}</div>
            <div className="muted">{agent.description}</div>
          </div>
          <button onClick={onClose} style={{ background: "transparent", color: "var(--text-dim)", border: "1px solid var(--border)" }}>
            esc
          </button>
        </header>

        <div className="drawer-body">
          <h2>actions</h2>
          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "1rem" }}>
            {agent.actions.map((a) => (
              <button
                key={a}
                onClick={() => triggerAction(a)}
                style={{
                  background: "var(--surface-2)",
                  color: "var(--text-dim)",
                  border: "1px solid var(--border-bright)",
                  fontSize: "0.72rem",
                  padding: "2px 8px",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                }}
                disabled={busy}
              >
                /{a}
              </button>
            ))}
          </div>

          <h2>thread</h2>
          {thread.length === 0 && (
            <div className="muted" style={{ marginBottom: "1rem" }}>
              type a message or click an action above
            </div>
          )}
          {thread.map((m, i) =>
            m.who === "user" ? (
              <div className="thread-msg user" key={i}>
                <div className="who">you</div>
                {m.text}
              </div>
            ) : (
              <div className="thread-msg agent" key={i}>
                <div className="who">
                  {m.envelope.agent} · {m.envelope.action} · {Math.round(m.envelope.confidence * 100)}%
                  {m.envelope.needs_confirm ? " · NEEDS CONFIRM" : ""}
                </div>
                <pre>{JSON.stringify(m.envelope.result, null, 2)}</pre>
              </div>
            )
          )}

          <h2 style={{ marginTop: "1.5rem" }}>last 20 actions</h2>
          {(history ?? []).length === 0 && <div className="muted">no history yet</div>}
          {(history ?? []).slice().reverse().map((h) => (
            <div className="thread-msg" key={`${h.request_id}-${h.ts}`}>
              <div className="who">
                {new Date(h.ts).toLocaleTimeString()} · {h.action} · {h.status} · {h.duration_ms}ms
              </div>
            </div>
          ))}
        </div>

        <footer className="drawer-foot">
          <input
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={`message ${agent.name}…`}
            disabled={busy}
          />
          <button onClick={send} disabled={busy || !text.trim()}>
            send
          </button>
        </footer>
      </aside>
    </>
  );
}
