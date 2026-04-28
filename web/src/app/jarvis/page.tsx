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
  Brain,
  Lock,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { BreadcrumbNav } from "@/components/breadcrumb-nav";
import { DispatchConfirmDialog } from "@/components/DispatchConfirmDialog";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

const JARVIS_API = process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765";

interface ToolCall {
  toolUseId: string;
  agent: string;
  action: string;
  args: Record<string, unknown>;
  result?: ToolResult;
}

interface ToolResult {
  text: string;
  isError: boolean;
  parsed?: AgentResponse;
}

interface AgentResponse {
  agent?: string;
  intent?: string;
  action?: string;
  result?: Record<string, unknown>;
  follow_ups?: string[];
  needs_confirm?: boolean;
  tier?: number;
  verification?: { status?: string };
}

interface Turn {
  id: string;
  user: string;
  userOverride?: "opus" | "sonnet";
  text: string;
  toolCalls: ToolCall[];
  status: "streaming" | "done" | "error";
  thinking: string;
  costUsd?: number;
  durationMs?: number;
  errorMessage?: string;
  model?: string;
  routeReason?: string;
  manualOverride?: boolean;
  routeTier?: number;
}

const SLASH_OVERRIDE = /^\s*\/(opus|sonnet)\s+/i;

function parseOverride(input: string): { override: "opus" | "sonnet" | null; cleaned: string } {
  const m = SLASH_OVERRIDE.exec(input);
  if (!m) return { override: null, cleaned: input };
  return {
    override: m[1].toLowerCase() as "opus" | "sonnet",
    cleaned: input.slice(m[0].length),
  };
}

function modelLabel(model?: string): string {
  if (!model) return "auto";
  if (model.includes("opus")) return "opus 4.7";
  if (model.includes("sonnet")) return "sonnet 4.6";
  if (model.includes("haiku")) return "haiku";
  return model;
}

function modelTone(model?: string): string {
  if (!model) return "bg-slate-500/15 text-slate-600 dark:text-slate-400";
  if (model.includes("opus"))
    return "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300 border-fuchsia-500/30";
  if (model.includes("sonnet"))
    return "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border-cyan-500/30";
  return "bg-slate-500/15 text-slate-600 dark:text-slate-400";
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
  if (!status) return null;
  const norm = status.toLowerCase();
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

interface PendingConfirmation {
  confirmationId: string;
  summary: string;
  turnId: string;
}

export default function JarvisPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirmation | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom when new content arrives.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const send = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setInput("");

    const turnId = `t-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const { override, cleaned } = parseOverride(trimmed);
    const fresh: Turn = {
      id: turnId,
      user: cleaned,
      userOverride: override ?? undefined,
      text: "",
      toolCalls: [],
      status: "streaming",
      thinking: "",
    };
    setTurns((prev) => [...prev, fresh]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${JARVIS_API}/api/jarvis/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),  // backend strips slash override
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const raw of events) {
          const line = raw.trim();
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;
          try {
            const evt = JSON.parse(payload) as Record<string, unknown>;
            applyEvent(turnId, evt, setTurns);

            // Surface confirmation gate from dispatch responses
            if (evt.type === "tool_result") {
              const text = String(evt.text ?? "");
              try {
                const parsed = JSON.parse(text) as AgentResponse;
                if (
                  parsed.needs_confirm === true &&
                  typeof (parsed as Record<string, unknown>)["confirmation_id"] === "string"
                ) {
                  const cid = (parsed as Record<string, unknown>)["confirmation_id"] as string;
                  const summaryText =
                    typeof (parsed as Record<string, unknown>)["summary"] === "string"
                      ? ((parsed as Record<string, unknown>)["summary"] as string)
                      : parsed.intent ?? "Action requires operator approval.";
                  setPendingConfirm({ confirmationId: cid, summary: summaryText, turnId });
                }
              } catch {
                // non-JSON tool result — skip
              }
            }
          } catch {
            // ignore malformed event
          }
        }
      }
      setTurns((prev) =>
        prev.map((t) => (t.id === turnId && t.status === "streaming" ? { ...t, status: "done" } : t)),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "request failed";
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId ? { ...t, status: "error", errorMessage: msg } : t,
        ),
      );
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
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
        "research recent AI hardware moves",
        "paper-scan the markets and report",
        "what's the morning briefing look like",
      ][turns.length % 6],
    [turns.length],
  );

  return (
    <div className="flex h-full flex-col">
      <BreadcrumbNav items={[{ label: "Jarvis" }]} />

      {pendingConfirm && (() => {
        // Capture a stable reference before callbacks mutate state.
        const captured = pendingConfirm;
        return (
          <DispatchConfirmDialog
            open
            onOpenChange={(open) => { if (!open) setPendingConfirm(null); }}
            confirmationId={captured.confirmationId}
            summary={captured.summary}
            onApproved={(result) => {
              setPendingConfirm(null);
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === captured.turnId
                    ? {
                        ...t,
                        text:
                          t.text +
                          `\n\n[approved] ${typeof result === "object" && result !== null ? JSON.stringify(result, null, 2).slice(0, 400) : String(result)}`,
                      }
                    : t
                )
              );
            }}
            onRejected={() => {
              setPendingConfirm(null);
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === captured.turnId
                    ? { ...t, text: t.text + "\n\n[rejected by operator]" }
                    : t
                )
              );
            }}
          />
        );
      })()}

      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h1 className="text-xl font-semibold">Talk to Jarvis</h1>
          <Badge
            variant="outline"
            className="text-[10px] uppercase tracking-wider"
            title="Auto-routed: short / chitchat → sonnet 4.6 · heavy / risky → opus 4.7. Prefix with /opus or /sonnet to force."
          >
            auto-router · sonnet ↔ opus
          </Badge>
        </div>
      </div>

      <Card className="flex-1 overflow-hidden">
        <CardContent className="flex h-full flex-col gap-3 p-0">
          <ScrollArea className="flex-1">
            <div ref={scrollRef} className="space-y-6 p-4">
              {turns.length === 0 ? <EmptyHero /> : turns.map((t) => <TurnView key={t.id} turn={t} />)}
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
              Enter to send · Shift+Enter for newline · Jarvis can delegate to tempo / scholar / lens / forge / atlas
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Stream applier ─────────────────────────────────────────────────────────

function applyEvent(
  turnId: string,
  evt: Record<string, unknown>,
  setTurns: React.Dispatch<React.SetStateAction<Turn[]>>,
) {
  const type = String(evt.type ?? "");
  setTurns((prev) =>
    prev.map((t) => {
      if (t.id !== turnId) return t;
      switch (type) {
        case "model":
          return {
            ...t,
            model: String(evt.model ?? ""),
            routeReason: String(evt.reason ?? ""),
            manualOverride: Boolean(evt.manual),
            routeTier: typeof evt.tier === "number" ? evt.tier : undefined,
          };
        case "text":
          return { ...t, text: t.text + String(evt.delta ?? "") };
        case "thinking":
          return { ...t, thinking: t.thinking + String(evt.delta ?? "") };
        case "tool_use": {
          const call: ToolCall = {
            toolUseId: String(evt.tool_use_id ?? ""),
            agent: String(evt.agent ?? ""),
            action: String(evt.action ?? ""),
            args: (evt.args as Record<string, unknown>) ?? {},
          };
          // Skip non-delegate built-ins (e.g. ToolSearch) so we don't clutter UI.
          if (String(evt.name ?? "").includes("delegate") === false && !call.agent) {
            return t;
          }
          return { ...t, toolCalls: [...t.toolCalls, call] };
        }
        case "tool_result": {
          const id = String(evt.tool_use_id ?? "");
          const text = String(evt.text ?? "");
          let parsed: AgentResponse | undefined;
          try {
            parsed = JSON.parse(text) as AgentResponse;
          } catch {
            parsed = undefined;
          }
          return {
            ...t,
            toolCalls: t.toolCalls.map((c) =>
              c.toolUseId === id
                ? {
                    ...c,
                    result: { text, isError: Boolean(evt.is_error), parsed },
                  }
                : c,
            ),
          };
        }
        case "done":
          return {
            ...t,
            status: "done",
            costUsd: typeof evt.total_cost_usd === "number" ? evt.total_cost_usd : t.costUsd,
            durationMs: typeof evt.duration_ms === "number" ? evt.duration_ms : t.durationMs,
          };
        case "error":
          return {
            ...t,
            status: "error",
            errorMessage: String(evt.message ?? "stream error"),
          };
        default:
          return t;
      }
    }),
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function EmptyHero() {
  const samples = [
    "what's on my calendar today",
    "triage my inbox",
    "look up news on AI hardware",
    "open a PR fixing the auth bug in jarvis",
    "paper trade BTC scan",
  ];
  return (
    <div className="mx-auto max-w-md space-y-4 py-12 text-center">
      <Sparkles className="mx-auto h-10 w-10 text-primary/70" />
      <h2 className="text-lg font-semibold">Tell Jarvis what you need.</h2>
      <p className="text-sm text-muted-foreground">
        Opus 4.7 with the OpenClaw soul. He&apos;ll think, decide which subsystem
        to delegate to (tempo / scholar / lens / forge / atlas), call the tool,
        and synthesize the answer for you.
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
        <div className="max-w-[80%] space-y-1">
          {turn.userOverride && (
            <div className="flex justify-end">
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px] uppercase tracking-wider",
                  modelTone(turn.userOverride === "opus" ? "claude-opus-4-7" : "claude-sonnet-4-6"),
                )}
              >
                <Lock className="mr-1 h-3 w-3" />
                forced · {turn.userOverride}
              </Badge>
            </div>
          )}
          <div className="rounded-2xl bg-primary px-4 py-2 text-sm text-primary-foreground">
            {turn.user}
          </div>
        </div>
      </div>

      {turn.model && (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Badge
            variant="outline"
            className={cn("text-[10px] uppercase tracking-wider", modelTone(turn.model))}
            title={turn.routeReason ?? ""}
          >
            {turn.manualOverride && <Lock className="mr-1 h-3 w-3" />}
            {modelLabel(turn.model)}
          </Badge>
          {turn.routeReason && <span className="italic">{turn.routeReason}</span>}
        </div>
      )}

      {turn.toolCalls.length > 0 && <DelegationTrace calls={turn.toolCalls} />}

      {turn.errorMessage && (
        <div className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="h-4 w-4" />
          {turn.errorMessage}
        </div>
      )}

      {turn.thinking && <ThinkingPanel thinking={turn.thinking} />}

      {turn.text && (
        <div className="rounded-2xl border bg-muted/40 px-4 py-2 text-sm whitespace-pre-wrap">
          {turn.text}
          {turn.status === "streaming" && (
            <span className="ml-1 inline-block h-3 w-1.5 animate-pulse bg-foreground align-middle" />
          )}
        </div>
      )}

      {turn.status !== "streaming" && (turn.costUsd !== undefined || turn.durationMs !== undefined) && (
        <div className="flex justify-end gap-3 text-[10px] text-muted-foreground">
          {turn.durationMs !== undefined && <span>{(turn.durationMs / 1000).toFixed(1)}s</span>}
          {turn.costUsd !== undefined && <span>${turn.costUsd.toFixed(4)}</span>}
        </div>
      )}
    </div>
  );
}

function ThinkingPanel({ thinking }: { thinking: string }) {
  return (
    <details className="group rounded-md border bg-muted/30 px-3 py-2 text-xs">
      <summary className="flex cursor-pointer items-center gap-2 text-muted-foreground">
        <Brain className="h-3 w-3" />
        thinking
      </summary>
      <pre className="mt-1.5 whitespace-pre-wrap text-[11px] text-muted-foreground">
        {thinking}
      </pre>
    </details>
  );
}

function DelegationTrace({ calls }: { calls: ToolCall[] }) {
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Delegation</div>
      <ol className="space-y-1.5 border-l pl-4">
        {calls.map((c) => {
          const status = c.result ? (c.result.isError ? "error" : "ok") : "running";
          const tier = c.result?.parsed?.tier;
          const verification = c.result?.parsed?.verification?.status;
          const intent = c.result?.parsed?.intent;
          const needsConfirm = c.result?.parsed?.needs_confirm;
          return (
            <li key={c.toolUseId} className="-ml-[7px]">
              <div className="flex items-start gap-2">
                <StatusDot status={status} />
                <div className="flex flex-1 flex-wrap items-center gap-1.5 text-xs">
                  <span className="font-mono font-semibold">{c.agent || "?"}</span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  <span className="font-mono text-muted-foreground">{c.action || "?"}</span>
                  {tier !== undefined && (
                    <Badge variant="outline" className={cn("text-[10px]", TIER_TONE[tier] ?? "")}>
                      {TIER_LABEL[tier] ?? `T${tier}`}
                    </Badge>
                  )}
                  <VerificationPill status={verification} />
                  {needsConfirm && (
                    <Badge variant="outline" className="text-[10px] uppercase bg-amber-500/15 text-amber-700 dark:text-amber-400">
                      needs confirm
                    </Badge>
                  )}
                  {intent && status === "ok" && (
                    <span className="font-mono text-[10px] text-muted-foreground">→ {intent}</span>
                  )}
                </div>
              </div>
              {c.result && c.result.parsed?.result && (
                <pre className="ml-5 mt-1 max-h-40 overflow-x-auto rounded bg-muted/50 p-2 text-[11px]">
                  {JSON.stringify(c.result.parsed.result, null, 2).slice(0, 1000)}
                </pre>
              )}
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
