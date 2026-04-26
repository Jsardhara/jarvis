"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { dispatch, listAgents, type AgentDescriptor } from "@/lib/api";
import { useTraceEvents, useWs } from "@/lib/ws";
import { StatusBar } from "@/components/StatusBar";
import { AgentCard, type AgentRuntimeState } from "@/components/AgentCard";
import { DispatchGraph, type DispatchSnapshot } from "@/components/DispatchGraph";
import { SwimlaneStream, type SwimlaneEvent } from "@/components/SwimlaneStream";
import { AgentDrawer } from "@/components/AgentDrawer";
import { ConfirmationQueue } from "@/components/ConfirmationQueue";
import { CommandPalette } from "@/components/CommandPalette";
import { Toasts } from "@/components/Toasts";

type AgentMap = Record<string, AgentRuntimeState>;
const SENTINEL: AgentDescriptor = {
  name: "sentinel",
  description: "background daemon (cron jobs)",
  actions: [],
};

const MAX_LANE_EVENTS = 80;

export default function MissionControl() {
  const ws = useWs();
  const { data: agents } = useSWR<AgentDescriptor[]>("agents", listAgents);
  const allAgents = useMemo<AgentDescriptor[]>(
    () => (agents ? [...agents, SENTINEL] : [SENTINEL]),
    [agents]
  );

  const [runtime, setRuntime] = useState<AgentMap>({});
  const [snapshot, setSnapshot] = useState<DispatchSnapshot>(null);
  const [events, setEvents] = useState<SwimlaneEvent[]>([]);
  const [drawer, setDrawer] = useState<AgentDescriptor | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const updateAgent = useCallback((name: string, patch: Partial<AgentRuntimeState>) => {
    setRuntime((r) => {
      const prev: AgentRuntimeState = r[name] ?? { status: "idle", action: "", confidence: 0 };
      return { ...r, [name]: { ...prev, ...patch } };
    });
  }, []);

  const handleEvent = useCallback(
    (e: { type: string; agent?: string | null; payload?: Record<string, unknown>; ts?: string }) => {
      switch (e.type) {
        case "router.classified": {
          const intent = (e.payload?.intent ?? {}) as {
            primary?: string;
            parallel?: string[];
            raw_request?: string;
          };
          setSnapshot({
            request: intent.raw_request ?? "",
            primary: intent.primary ?? null,
            parallel: intent.parallel ?? [],
            ts: e.ts ?? new Date().toISOString(),
          });
          return;
        }
        case "agent.start": {
          if (!e.agent) return;
          const action = (e.payload?.action as string | undefined) || "running";
          updateAgent(e.agent, { status: "running", action });
          setEvents((arr) => {
            const next: SwimlaneEvent = {
              id: crypto.randomUUID(),
              agent: e.agent!,
              action,
              status: "running",
              ts: e.ts ?? new Date().toISOString(),
            };
            return [...arr, next].slice(-MAX_LANE_EVENTS);
          });
          return;
        }
        case "agent.done": {
          if (!e.agent) return;
          const action = (e.payload?.action as string) ?? "done";
          const confidence = Number(e.payload?.confidence ?? 1);
          const needsConfirm = Boolean(e.payload?.needs_confirm);
          updateAgent(e.agent, {
            status: needsConfirm ? "warn" : "done",
            action,
            confidence,
          });
          setEvents((arr) => {
            const next: SwimlaneEvent = {
              id: crypto.randomUUID(),
              agent: e.agent!,
              action,
              status: needsConfirm ? "proposed" : "done",
              ts: e.ts ?? new Date().toISOString(),
            };
            return [...arr, next].slice(-MAX_LANE_EVENTS);
          });
          return;
        }
        case "agent.error": {
          if (!e.agent) return;
          updateAgent(e.agent, { status: "error", action: "errored", confidence: 0 });
          setEvents((arr) => {
            const next: SwimlaneEvent = {
              id: crypto.randomUUID(),
              agent: e.agent!,
              action: "error",
              status: "error",
              ts: e.ts ?? new Date().toISOString(),
            };
            return [...arr, next].slice(-MAX_LANE_EVENTS);
          });
          return;
        }
      }
    },
    [updateAgent]
  );
  useTraceEvents(handleEvent);

  // Cmd+K opens palette
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (e.key === "Escape") {
        setPaletteOpen(false);
        setDrawer(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      await dispatch(text);
      setText("");
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const openDrawer = (name: string) => {
    const desc = allAgents.find((a) => a.name === name);
    if (desc) setDrawer(desc);
  };

  return (
    <div className="mc-shell">
      <StatusBar />

      <section className="mc-pane mc-agent-grid">
        <h2>agents</h2>
        {allAgents.map((a) => (
          <AgentCard
            key={a.name}
            descriptor={a}
            state={runtime[a.name] ?? { status: "idle", action: "", confidence: 0 }}
            onOpen={openDrawer}
          />
        ))}
      </section>

      <section className="mc-pane mc-graph">
        <h2>dispatch graph</h2>
        <DispatchGraph snapshot={snapshot} />
      </section>

      <section className="mc-pane mc-swimlanes">
        <h2>activity stream</h2>
        <SwimlaneStream agents={allAgents.map((a) => a.name)} events={events} />
      </section>

      <ConfirmationQueue />

      <div className="mc-dispatchbar">
        <span className="prompt">&gt;</span>
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void send();
            }
          }}
          placeholder='dispatch any request — e.g. "morning briefing", "what’s on my plate today"'
          disabled={busy}
        />
        <span className="hint">⌘K palette · click agent to chat</span>
      </div>

      <AgentDrawer agent={drawer} onClose={() => setDrawer(null)} />
      <CommandPalette
        agents={allAgents.filter((a) => a.actions.length > 0)}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      />
      <Toasts />

      {/* Suppress unused-var warnings */}
      <span style={{ display: "none" }}>{ws.status}</span>
    </div>
  );
}
