"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { dispatch, listAgents, type AgentDescriptor } from "@/lib/api";
import { useTraceEvents, useWs } from "@/lib/ws";
import { StatusBar } from "@/components/StatusBar";
import { AgentCard, type AgentRuntimeState } from "@/components/AgentCard";
import { DispatchGraph, type DispatchSnapshot } from "@/components/DispatchGraph";
import { SwimlaneStream, type SwimlaneEvent } from "@/components/SwimlaneStream";
import { AtlasSubflow, type AtlasStage, type AtlasStageState } from "@/components/AtlasSubflow";
import { AgentDrawer } from "@/components/AgentDrawer";
import { ConfirmationQueue } from "@/components/ConfirmationQueue";
import { CommandPalette } from "@/components/CommandPalette";
import { Toasts } from "@/components/Toasts";
import type { Tier } from "@/components/TierBadge";
import type { VerificationStatus } from "@/components/VerificationPill";

type AgentMap = Record<string, AgentRuntimeState>;

const SENTINEL: AgentDescriptor = {
  name: "sentinel",
  description: "background daemon (cron jobs)",
  actions: [],
};

const MAX_LANE_EVENTS = 80;

// Atlas sub-agents arrive as agent=atlas.oracle, atlas.architect, etc.
const ATLAS_SUB_AGENTS = new Set<AtlasStage>(["oracle", "architect", "guardian", "trader", "sage"]);

const VERIFICATION_STATUSES = new Set<VerificationStatus>([
  "verified",
  "inference",
  "unknown",
  "post_state_checked",
]);

function isVerificationStatus(v: unknown): v is VerificationStatus {
  return typeof v === "string" && VERIFICATION_STATUSES.has(v as VerificationStatus);
}

function toTier(raw: unknown): Tier | undefined {
  if (typeof raw === "number" && raw >= 1 && raw <= 5) return raw as Tier;
  return undefined;
}

// atlas.oracle → "oracle", atlas.architect → "architect", etc. Returns null for non-atlas-sub.
function atlasSubStage(agentName: string): AtlasStage | null {
  const prefix = "atlas.";
  if (!agentName.startsWith(prefix)) return null;
  const sub = agentName.slice(prefix.length) as AtlasStage;
  return ATLAS_SUB_AGENTS.has(sub) ? sub : null;
}

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
  const [atlasStages, setAtlasStages] = useState<Partial<Record<AtlasStage, AtlasStageState>>>({});
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
          setAtlasStages({});
          return;
        }

        case "agent.start": {
          if (!e.agent) return;
          const action = (e.payload?.action as string | undefined) || "running";
          const tier = toTier(e.payload?.tier);
          const atlasSub = atlasSubStage(e.agent);

          updateAgent(e.agent, { status: "running", action, tier });

          if (atlasSub) {
            setAtlasStages((prev) => ({
              ...prev,
              [atlasSub]: { status: "running", summary: action, ts: e.ts },
            }));
          }

          setEvents((arr) => [
            ...arr,
            {
              id: crypto.randomUUID(),
              agent: e.agent!,
              action,
              status: "running" as const,
              ts: e.ts ?? new Date().toISOString(),
              tier,
            },
          ].slice(-MAX_LANE_EVENTS));
          return;
        }

        case "agent.done": {
          if (!e.agent) return;
          const action = (e.payload?.action as string) ?? "done";
          const confidence = Number(e.payload?.confidence ?? 1);
          const needsConfirm = Boolean(e.payload?.needs_confirm);
          // Backend emits verification_status as a flat string, not a nested object
          const rawVs = e.payload?.verification_status;
          const verification = isVerificationStatus(rawVs) ? rawVs : undefined;
          const tier = toTier(e.payload?.tier);
          const atlasSub = atlasSubStage(e.agent);

          updateAgent(e.agent, {
            status: needsConfirm ? "warn" : "done",
            action,
            confidence,
            verification,
            tier,
          });

          if (atlasSub) {
            const blocked = atlasSub === "guardian" && (e.payload?.action as string) === "blocked";
            setAtlasStages((prev) => ({
              ...prev,
              [atlasSub]: {
                status: blocked ? "halted" : "done",
                summary: action,
                ts: e.ts,
                verification,
              },
            }));
          }

          setEvents((arr) => [
            ...arr,
            {
              id: crypto.randomUUID(),
              agent: e.agent!,
              action,
              status: (needsConfirm ? "proposed" : "done") as "proposed" | "done",
              ts: e.ts ?? new Date().toISOString(),
              tier,
              verification,
            },
          ].slice(-MAX_LANE_EVENTS));
          return;
        }

        case "agent.error": {
          if (!e.agent) return;
          const atlasSub = atlasSubStage(e.agent);
          updateAgent(e.agent, { status: "error", action: "errored", confidence: 0 });
          if (atlasSub) {
            setAtlasStages((prev) => ({
              ...prev,
              [atlasSub]: { status: "error", summary: "errored", ts: e.ts },
            }));
          }
          setEvents((arr) => [
            ...arr,
            {
              id: crypto.randomUUID(),
              agent: e.agent!,
              action: "error",
              status: "error" as const,
              ts: e.ts ?? new Date().toISOString(),
            },
          ].slice(-MAX_LANE_EVENTS));
          return;
        }
      }
    },
    [updateAgent]
  );
  useTraceEvents(handleEvent);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        setPaletteOpen(true);
      } else if (ev.key === "Escape") {
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

  const dismissAtlas = useCallback(() => {
    setAtlasStages({});
  }, []);

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
          onChange={(ev) => setText(ev.target.value)}
          onKeyDown={(ev) => {
            if (ev.key === "Enter") {
              ev.preventDefault();
              void send();
            }
          }}
          placeholder='dispatch any request — e.g. "morning briefing", "what is on my plate today"'
          disabled={busy}
        />
        <span className="hint">⌘K palette · click agent to chat</span>
      </div>

      <AtlasSubflow stages={atlasStages} onDismiss={dismissAtlas} />

      <AgentDrawer agent={drawer} onClose={() => setDrawer(null)} />
      <CommandPalette
        agents={allAgents.filter((a) => a.actions.length > 0)}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      />
      <Toasts />

      {/* Suppress unused-var warning */}
      <span style={{ display: "none" }}>{ws.status}</span>
    </div>
  );
}
