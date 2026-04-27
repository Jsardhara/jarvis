"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  CircleDashed,
  Loader2,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { BreadcrumbNav } from "@/components/breadcrumb-nav";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

const JARVIS_API = process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765";
const JARVIS_WS = JARVIS_API.replace(/^http/, "ws") + "/ws";

interface TraceEvent {
  type: string;
  request_id: string;
  agent: string;
  ts: string;
  payload?: Record<string, unknown>;
}

interface AgentResponse {
  agent: string;
  intent: string;
  action: string;
  result?: Record<string, unknown>;
  follow_ups?: string[];
  confidence?: number;
  needs_confirm?: boolean;
  tier?: number;
  verification?: { status?: string };
  request_id?: string;
}

interface DispatchResult {
  request_id: string;
  intent?: { primary?: string; rationale?: string };
  responses?: Record<string, AgentResponse>;
  needs_confirm?: boolean;
}

interface Turn {
  id: string;
  user: string;
  startedAt: string;
  completedAt?: string;
  events: TraceEvent[];
  result?: DispatchResult;
  error?: string;
}

// ─── Visual helpers ─────────────────────────────────────────────────────────

const TIER_LABEL: Record<number, string> = {
  1: "T1 · risk",
  2: "T2 · time-sensitive",
  3: "T3 · trade/research",
  4: "T4 · scheduling",
  5: "T5 · routine",
};

const TIER_TONE: Record<number, string> = {
  1: "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30",
  2: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
  3: "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/30",
  4: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  5: "bg-slate-500/15 text-slate-700 dark:text-slate-400 border-slate-500/30",
};

function VerificationPill({ status }: { status?: string }) {
  const norm = (status ?? "unknown").toLowerCase();
  const tone =
    norm === "verified"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
      : norm === "post_state_checked"
        ? "bg-sky-500/15 text-sky-700 dark:text-sky-400"
        : norm === "inference"
          ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
          : "bg-slate-500/15 text-slate-600 dark:text-slate-400";
  return (
    <Badge variant="outline" className={cn("text-[10px] uppercase tracking-wider", tone)}>
      {norm}
    </Badge>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function JarvisPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [wsState, setWsState] = useState<"connecting" | "open" | "closed">("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const turnsRef = useRef<Turn[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Keep ref in sync so the WS handler always reads the latest turns.
  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  // Auto-scroll to bottom when new content arrives.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [turns]);

  // WebSocket connection — reconnect on close.
  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;
    let retry = 0;

    function connect() {
      if (cancelled) return;
      try {
        ws = new WebSocket(JARVIS_WS);
      } catch {
        setWsState("closed");
        return;
      }
      wsRef.current = ws;
      setWsState("connecting");

      ws.onopen = () => {
        retry = 0;
        setWsState("open");
      };

      ws.onmessage = (evt) => {
        let parsed: TraceEvent | null = null;
        try {
          parsed = JSON.parse(evt.data);
        } catch {
          return;
        }
        if (!parsed || !parsed.request_id) return;
        const requestId = parsed.request_id;
        setTurns((prev) => {
          const next = prev.map((t) =>
            t.id === requestId ? { ...t, events: [...t.events, parsed!] } : t,
          );
          return next;
        });
      };

      ws.onerror = () => {
        setWsState("closed");
      };

      ws.onclose = () => {
        setWsState("closed");
        if (cancelled) return;
        retry = Math.min(retry + 1, 6);
        setTimeout(connect, 500 * 2 ** retry);
      };
    }

    connect();
    return () => {
      cancelled = true;
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    };
  }, []);

  const send = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    const startedAt = new Date().toISOString();

    let result: DispatchResult | undefined;
    let dispatchError: string | undefined;
    try {
      const res = await fetch(`${JARVIS_API}/api/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: trimmed }),
      });
      if (!res.ok) {
        dispatchError = `HTTP ${res.status}`;
      } else {
        result = (await res.json()) as DispatchResult;
      }
    } catch (err) {
      dispatchError = err instanceof Error ? err.message : "request failed";
    }

    const requestId = result?.request_id ?? `local-${Date.now()}`;
    const completedAt = new Date().toISOString();

    setTurns((prev) => {
      // If the WebSocket already started populating events under request_id,
      // merge them into the new turn record; otherwise create a fresh one.
      const existing = prev.find((t) => t.id === requestId);
      const fresh: Turn = {
        id: requestId,
        user: trimmed,
        startedAt,
        completedAt,
        events: existing?.events ?? [],
        result,
        error: dispatchError,
      };
      const filtered = prev.filter((t) => t.id !== requestId);
      return [...filtered, fresh];
    });
    setInput("");
    setBusy(false);
  }, [busy, input]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void send();
      }
    },
    [send],
  );

  const placeholder = useMemo(
    () =>
      [
        "Talk to Jarvis…",
        "what's on my calendar today",
        "triage my inbox",
        "research recent AI news",
        "paper-scan markets",
      ][turns.length % 5],
    [turns.length],
  );

  return (
    <div className="flex h-full flex-col">
      <BreadcrumbNav items={[{ label: "Jarvis" }]} />

      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h1 className="text-xl font-semibold">Talk to Jarvis</h1>
        </div>
        <ConnectionPill state={wsState} />
      </div>

      <Card className="flex-1 overflow-hidden">
        <CardContent className="flex h-full flex-col gap-3 p-0">
          <ScrollArea className="flex-1">
            <div ref={scrollRef} className="space-y-4 p-4">
              {turns.length === 0 ? (
                <EmptyHero />
              ) : (
                turns.map((t) => <TurnView key={t.id} turn={t} />)
              )}
            </div>
          </ScrollArea>

          <div className="border-t bg-background/95 p-3 backdrop-blur">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
                placeholder={placeholder}
                disabled={busy}
                className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
              />
              <Button onClick={() => void send()} disabled={busy || !input.trim()} size="icon" className="h-10 w-10 shrink-0">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                <span className="sr-only">Send</span>
              </Button>
            </div>
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              Enter to send · Shift+Enter for newline · Ctrl+C in terminal won't cancel a dispatch
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function ConnectionPill({ state }: { state: "connecting" | "open" | "closed" }) {
  const tone =
    state === "open"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
      : state === "connecting"
        ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
        : "bg-red-500/15 text-red-700 dark:text-red-400";
  return (
    <Badge variant="outline" className={cn("text-[10px] uppercase tracking-wider", tone)}>
      live trace · {state}
    </Badge>
  );
}

function EmptyHero() {
  const samples = [
    "what's on my calendar today",
    "triage my inbox",
    "look up news on AI hardware",
    "open PR to fix the auth bug in jarvis",
    "paper trade BTC scan",
  ];
  return (
    <div className="mx-auto max-w-md space-y-4 py-12 text-center">
      <Sparkles className="mx-auto h-10 w-10 text-primary/70" />
      <h2 className="text-lg font-semibold">Tell Jarvis what you need.</h2>
      <p className="text-sm text-muted-foreground">
        He&apos;ll classify the tier, check authority, route it to the right subsystem (tempo / atlas / lens / forge / scholar) and you&apos;ll see the live delegation trace below.
      </p>
      <div className="flex flex-wrap justify-center gap-2 pt-1">
        {samples.map((s) => (
          <Badge key={s} variant="outline" className="font-normal">
            &ldquo;{s}&rdquo;
          </Badge>
        ))}
      </div>
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-2 text-sm text-primary-foreground">
          {turn.user}
        </div>
      </div>

      <DelegationTrace turn={turn} />

      {turn.error && (
        <div className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="h-4 w-4" />
          {turn.error}
        </div>
      )}

      {turn.result && <FinalResponseCard result={turn.result} />}
    </div>
  );
}

function DelegationTrace({ turn }: { turn: Turn }) {
  if (!turn.events.length && !turn.result && !turn.error) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Routing…
      </div>
    );
  }

  // Group events by agent in arrival order; collapse start/done pairs.
  const byAgent = new Map<string, TraceEvent[]>();
  for (const ev of turn.events) {
    const list = byAgent.get(ev.agent) ?? [];
    list.push(ev);
    byAgent.set(ev.agent, list);
  }
  const order = Array.from(byAgent.keys());

  return (
    <div className="space-y-1.5">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Delegation</div>
      <ol className="space-y-1.5 border-l pl-4">
        {order.map((agent) => {
          const evs = byAgent.get(agent) ?? [];
          const startEv = evs.find((e) => e.type.endsWith(".start"));
          const doneEv = evs.find((e) => e.type.endsWith(".done"));
          const errEv = evs.find((e) => e.type.endsWith(".error"));
          const status = errEv ? "error" : doneEv ? "ok" : "running";
          const payload = (doneEv ?? startEv)?.payload ?? {};
          const tier = typeof payload.tier === "number" ? (payload.tier as number) : undefined;
          const action =
            typeof payload.action === "string"
              ? (payload.action as string)
              : typeof payload.intent === "string"
                ? (payload.intent as string)
                : undefined;
          const verification =
            typeof payload.verification_status === "string"
              ? (payload.verification_status as string)
              : undefined;
          const duration =
            typeof payload.duration_ms === "number" ? (payload.duration_ms as number) : undefined;

          return (
            <li key={agent} className="-ml-[7px] flex items-start gap-2">
              <StatusDot status={status} />
              <div className="flex flex-1 flex-wrap items-center gap-1.5 text-xs">
                <span className="font-mono font-semibold">{agent}</span>
                {action && <ArrowRight className="h-3 w-3 text-muted-foreground" />}
                {action && <span className="font-mono text-muted-foreground">{action}</span>}
                {tier !== undefined && (
                  <Badge variant="outline" className={cn("text-[10px]", TIER_TONE[tier] ?? "")}>
                    {TIER_LABEL[tier] ?? `T${tier}`}
                  </Badge>
                )}
                {verification && <VerificationPill status={verification} />}
                {duration !== undefined && (
                  <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                    {duration} ms
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StatusDot({ status }: { status: "running" | "ok" | "error" }) {
  if (status === "ok") return <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />;
  if (status === "error") return <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />;
  return <CircleDashed className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-amber-500" />;
}

function FinalResponseCard({ result }: { result: DispatchResult }) {
  const responses = result.responses ?? {};
  const agentNames = Object.keys(responses);
  if (agentNames.length === 0) {
    if (result.intent?.rationale) {
      return (
        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          <div className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Jarvis</div>
          {result.intent.rationale}
        </div>
      );
    }
    return null;
  }

  return (
    <div className="space-y-2">
      {agentNames.map((agent) => {
        const r = responses[agent];
        return (
          <div key={agent} className="rounded-md border bg-muted/40 p-3 text-sm">
            <div className="mb-1 flex items-center gap-2">
              <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                {agent}
              </span>
              {r.tier !== undefined && (
                <Badge variant="outline" className={cn("text-[10px]", TIER_TONE[r.tier] ?? "")}>
                  {TIER_LABEL[r.tier] ?? `T${r.tier}`}
                </Badge>
              )}
              <VerificationPill status={r.verification?.status} />
              {r.needs_confirm && (
                <Badge variant="outline" className="text-[10px] uppercase bg-amber-500/15 text-amber-700 dark:text-amber-400">
                  needs confirm
                </Badge>
              )}
            </div>
            <ResultPayload result={r.result} />
            {r.follow_ups && r.follow_ups.length > 0 && (
              <div className="mt-2 border-t pt-2 text-xs text-muted-foreground">
                <span className="font-medium">follow-ups:</span>{" "}
                {r.follow_ups.join(" · ")}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ResultPayload({ result }: { result?: Record<string, unknown> }) {
  if (!result) return null;
  // Common shapes Jarvis returns — render them friendly when we recognize.
  const events = result["events"];
  if (Array.isArray(events) && events.length > 0) {
    return (
      <ul className="space-y-1 text-sm">
        {events.slice(0, 8).map((e, i) => {
          const ev = e as Record<string, unknown>;
          return (
            <li key={i} className="flex flex-wrap items-baseline gap-2">
              <span className="font-medium">{String(ev.summary ?? ev.title ?? "(event)")}</span>
              {typeof ev.start === "string" && (
                <span className="text-xs text-muted-foreground">{ev.start}</span>
              )}
            </li>
          );
        })}
      </ul>
    );
  }
  const items = result["items"] ?? result["tasks"] ?? result["buckets"];
  if (items) {
    return (
      <pre className="overflow-x-auto rounded bg-muted/50 p-2 text-[11px]">
        {JSON.stringify(items, null, 2).slice(0, 1200)}
      </pre>
    );
  }
  return (
    <pre className="overflow-x-auto rounded bg-muted/50 p-2 text-[11px]">
      {JSON.stringify(result, null, 2).slice(0, 1200)}
    </pre>
  );
}
