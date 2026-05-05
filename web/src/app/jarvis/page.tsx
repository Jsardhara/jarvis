"use client";

import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  ArrowRight,
  AlertTriangle,
  Loader2,
  Brain,
  Lock,
} from "lucide-react";
import { DispatchConfirmDialog } from "@/components/DispatchConfirmDialog";
import {
  Panel,
  AgentGlyph,
  Bars,
  BrandMark,
  Dot,
  Hatch,
  KV,
  Tag,
  OpsButton,
  getAgentIdentity,
  SUBSYSTEM_AGENTS,
} from "@/components/ops";

import { apiFetch } from "@/lib/api-client";
import { useIsMobile } from "@/hooks/useIsMobile";

// ─── Recall types ─────────────────────────────────────────────────────────────

interface RecallHit {
  score: number;
  role: string;
  text: string;
  ts: string;
  lane: string | null;
}

const QUICK_PROMPTS = [
  "morning briefing",
  "what's in my inbox",
  "today's schedule",
  "atlas pnl",
] as const;

// ─── Types ───────────────────────────────────────────────────────────────────

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

interface PendingConfirmation {
  confirmationId: string;
  summary: string;
  turnId: string;
}

// ─── Server turn shape (from /api/jarvis/turns) ──────────────────────────────

interface ServerToolCall {
  tool_use_id: string;
  agent: string;
  action: string;
  args: Record<string, unknown>;
  result: { text: string; is_error: boolean } | null;
}

interface ServerTurn {
  user_id: string;
  turn_id: string;
  user_text: string;
  assistant_text: string;
  tool_calls: ServerToolCall[];
  model: string;
  cost_usd: number;
  duration_ms: number;
  ts: string;
}

function serverTurnToTurn(s: ServerTurn): Turn {
  const toolCalls: ToolCall[] = s.tool_calls.map((c) => {
    let parsed: AgentResponse | undefined;
    if (c.result?.text) {
      try {
        parsed = JSON.parse(c.result.text) as AgentResponse;
      } catch {
        parsed = undefined;
      }
    }
    return {
      toolUseId: c.tool_use_id,
      agent: c.agent,
      action: c.action,
      args: c.args ?? {},
      result: c.result
        ? { text: c.result.text, isError: c.result.is_error, parsed }
        : undefined,
    };
  });
  return {
    id: s.turn_id,
    user: s.user_text,
    text: s.assistant_text,
    toolCalls,
    status: "done",
    thinking: "",
    costUsd: s.cost_usd,
    durationMs: s.duration_ms,
    model: s.model || undefined,
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

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

function stamp(): string {
  const t = new Date();
  const pad = (x: number) => String(x).padStart(2, "0");
  return `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
}

// ─── Stream applier ──────────────────────────────────────────────────────────

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
                ? { ...c, result: { text, isError: Boolean(evt.is_error), parsed } }
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
          return { ...t, status: "error", errorMessage: String(evt.message ?? "stream error") };
        default:
          return t;
      }
    }),
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

const TURNS_STORAGE_KEY = "jarvis.chat.turns.v1";
const TURNS_PERSIST_MAX = 50;

export default function JarvisPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirmation | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const restoredRef = useRef(false);
  const isMobile = useIsMobile();

  // Recall state
  const [recallQuery, setRecallQuery] = useState("");
  const [recallBusy, setRecallBusy] = useState(false);
  const [recallHits, setRecallHits] = useState<RecallHit[] | null>(null);
  const [recallError, setRecallError] = useState<string | null>(null);

  const runRecall = useCallback(async () => {
    const q = recallQuery.trim();
    if (!q || recallBusy) return;
    setRecallBusy(true);
    setRecallHits(null);
    setRecallError(null);
    try {
      const res = await apiFetch(`/api/jarvis/recall`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, top_k: 5 }),
      });
      const body = (await res.json()) as { data?: RecallHit[]; error?: string | null };
      if (!res.ok || body.error) {
        setRecallError(body.error ?? `HTTP ${res.status}`);
      } else {
        setRecallHits(body.data ?? []);
      }
    } catch (err) {
      setRecallError(err instanceof Error ? err.message : "request failed");
    } finally {
      setRecallBusy(false);
    }
  }, [recallQuery, recallBusy]);

  // Restore saved chat history on mount: prefer server (cross-device),
  // fall back to localStorage when offline.
  useEffect(() => {
    if (typeof window === "undefined" || restoredRef.current) return;
    restoredRef.current = true;

    const fromLocal = (): Turn[] => {
      try {
        const raw = window.localStorage.getItem(TURNS_STORAGE_KEY);
        if (!raw) return [];
        const parsed: unknown = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed
          .filter((t): t is Turn => typeof t === "object" && t !== null && "id" in t)
          .map((t) => (t.status === "streaming" ? { ...t, status: "done" as const } : t));
      } catch {
        return [];
      }
    };

    const fetchServer = async () => {
      try {
        const res = await apiFetch(`/api/jarvis/turns?limit=${TURNS_PERSIST_MAX}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { data?: ServerTurn[]; error?: string | null };
        if (body.error || !Array.isArray(body.data)) throw new Error(body.error ?? "bad shape");
        const mapped = body.data.map(serverTurnToTurn);
        if (mapped.length > 0) {
          setTurns(mapped);
          return true;
        }
      } catch {
        return false;
      }
      return false;
    };

    void fetchServer().then((ok) => {
      if (!ok) {
        const local = fromLocal();
        if (local.length > 0) setTurns(local);
      }
    });
  }, []);

  // Persist chat history whenever it changes
  useEffect(() => {
    if (typeof window === "undefined" || !restoredRef.current) return;
    try {
      const trimmed = turns.slice(-TURNS_PERSIST_MAX);
      window.localStorage.setItem(TURNS_STORAGE_KEY, JSON.stringify(trimmed));
    } catch {
      // quota exceeded — drop silently
    }
  }, [turns]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const send = useCallback(async (text?: string) => {
    const raw = (text ?? input).trim();
    if (!raw || busy) return;
    setBusy(true);
    if (!text) setInput("");

    const turnId = `t-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const { override, cleaned } = parseOverride(raw);
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
      const res = await apiFetch(`/api/jarvis/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: raw }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

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

            if (evt.type === "tool_result") {
              const bodyText = String(evt.text ?? "");
              try {
                const parsed = JSON.parse(bodyText) as AgentResponse;
                if (
                  parsed.needs_confirm === true &&
                  typeof (parsed as Record<string, unknown>)["confirmation_id"] === "string"
                ) {
                  const cid = (parsed as Record<string, unknown>)["confirmation_id"] as string;
                  const summaryText =
                    typeof (parsed as Record<string, unknown>)["summary"] === "string"
                      ? ((parsed as Record<string, unknown>)["summary"] as string)
                      : (parsed.intent ?? "Action requires operator approval.");
                  setPendingConfirm({ confirmationId: cid, summary: summaryText, turnId });
                }
              } catch {
                // non-JSON tool result
              }
            }
          } catch {
            // malformed event
          }
        }
      }
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId && t.status === "streaming" ? { ...t, status: "done" } : t,
        ),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "request failed";
      setTurns((prev) =>
        prev.map((t) => (t.id === turnId ? { ...t, status: "error", errorMessage: msg } : t)),
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
        "Tell Jarvis what you need…",
        "what's on my calendar today",
        "triage my inbox",
        "research recent AI hardware moves",
        "paper-scan the markets and report",
        "what's the morning briefing look like",
      ][turns.length % 6],
    [turns.length],
  );

  // Dispatch bars: count how many times each agent was called across all turns
  const dispatchCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of turns) {
      for (const c of t.toolCalls) {
        if (c.agent) counts[c.agent] = (counts[c.agent] ?? 0) + 1;
      }
    }
    return counts;
  }, [turns]);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr" : "1fr 280px",
        gap: 0,
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
      } as CSSProperties}
    >
      {/* ── Confirm dialog ─────────────────────────────────────────────────── */}
      {pendingConfirm && (() => {
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
                    : t,
                ),
              );
            }}
            onRejected={() => {
              setPendingConfirm(null);
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === captured.turnId
                    ? { ...t, text: t.text + "\n\n[rejected by operator]" }
                    : t,
                ),
              );
            }}
          />
        );
      })()}

      {/* ── Message stream + composer ──────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          borderRight: "1px solid var(--ops-line)",
        } as CSSProperties}
      >
        {/* scroll area */}
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "20px 20px",
            display: "flex",
            flexDirection: "column",
            gap: 20,
          } as CSSProperties}
        >
          {turns.length === 0 ? (
            <EmptyState />
          ) : (
            turns.map((t) => <TurnView key={t.id} turn={t} />)
          )}
        </div>

        {/* composer */}
        <div
          style={{
            borderTop: "1px solid var(--ops-line)",
            background: "var(--ops-bg-deep)",
            padding: "10px 14px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          } as CSSProperties}
        >
          {/* quick-prompt chips */}
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" } as CSSProperties}>
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q}
                onClick={() => void send(q)}
                disabled={busy}
                style={{
                  background: "transparent",
                  border: "1px solid var(--ops-line)",
                  color: "var(--ops-fg-dim)",
                  padding: "3px 8px",
                  fontSize: 10,
                  letterSpacing: "0.06em",
                  fontFamily: "var(--ops-mono)",
                  borderRadius: 2,
                  cursor: "pointer",
                } as CSSProperties}
              >
                ↳ {q}
              </button>
            ))}
          </div>

          {/* input row */}
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end" } as CSSProperties}>
            <span
              style={{
                fontSize: 9,
                color: "var(--ops-amber)",
                letterSpacing: "0.18em",
                padding: "8px 0",
                minWidth: 52,
                fontFamily: "var(--ops-mono)",
              } as CSSProperties}
            >
              YOU ▸
            </span>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              placeholder={placeholder}
              disabled={busy}
              style={{
                flex: 1,
                background: "var(--ops-bg-input)",
                border: "1px solid var(--ops-line)",
                color: "var(--ops-fg)",
                padding: "8px 10px",
                fontFamily: "var(--ops-mono)",
                fontSize: 12,
                lineHeight: 1.5,
                borderRadius: 2,
                outline: "none",
                resize: "none",
                minHeight: 40,
              } as CSSProperties}
            />
            <OpsButton
              variant="primary"
              onClick={() => void send()}
              disabled={busy || !input.trim()}
              style={{ padding: "8px 12px", display: "flex", gap: 6, alignItems: "center" } as CSSProperties}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              SEND
            </OpsButton>
          </div>

          <p
            style={{
              fontSize: 10,
              color: "var(--ops-fg-faint)",
              fontFamily: "var(--ops-mono)",
              letterSpacing: "0.06em",
            } as CSSProperties}
          >
            ENTER · SEND &nbsp;·&nbsp; SHIFT+ENTER · NEWLINE
          </p>
        </div>
      </div>

      {/* ── Right rail ────────────────────────────────────────────────────── */}
      <div
        style={{
          display: isMobile ? "none" : "flex",
          flexDirection: "column",
          gap: 10,
          padding: 12,
          overflowY: "auto",
        } as CSSProperties}
      >
        {/* Conversation stats */}
        <Panel title="CONVERSATION" trailing={<Dot kind={busy ? "ok" : "idle"} pulse={busy} />}>
          <KV label="MESSAGES">{turns.length}</KV>
          <KV label="SESSION">{stamp()}</KV>
          <KV label="STATUS">{busy ? "PROCESSING" : turns.length === 0 ? "STANDING BY" : "IDLE"}</KV>
        </Panel>

        {/* Dispatch last 24h */}
        <Panel title="DISPATCH · AGENTS">
          {SUBSYSTEM_AGENTS.map((id) => {
            const identity = getAgentIdentity(id);
            if (!identity) return null;
            const count = dispatchCounts[id] ?? 0;
            const barValues = Array.from({ length: 12 }, (_, i) =>
              i === 11 ? count * 8 : Math.random() * 4,
            );
            return (
              <div
                key={id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 0",
                  fontSize: 10,
                } as CSSProperties}
              >
                <AgentGlyph agent={identity} size={14} />
                <span
                  style={{
                    color: identity.colorHex,
                    fontFamily: "var(--ops-mono)",
                    flex: 1,
                    fontSize: 9,
                    letterSpacing: "0.08em",
                  } as CSSProperties}
                >
                  {identity.name}
                </span>
                <Bars values={barValues} color={identity.colorHex} height={14} />
                <span
                  style={{
                    color: "var(--ops-fg-dim)",
                    fontFamily: "var(--ops-mono)",
                    width: 18,
                    textAlign: "right",
                    fontSize: 10,
                  } as CSSProperties}
                >
                  {count}
                </span>
              </div>
            );
          })}
        </Panel>

        {/* Pinned context */}
        <Panel title="PINNED CONTEXT">
          {[
            "Prefer terse, action-oriented replies",
            "Confirm before send-mail / calendar mutations",
            "Default tz · America/Los_Angeles",
          ].map((fact) => (
            <div
              key={fact}
              style={{
                padding: "5px 8px",
                border: "1px solid var(--ops-line)",
                borderLeft: "2px solid var(--ops-amber)",
                fontFamily: "var(--ops-sans)",
                fontSize: 10,
                color: "var(--ops-fg-mute)",
                marginBottom: 4,
              } as CSSProperties}
            >
              {fact}
            </div>
          ))}
        </Panel>

        {/* Semantic recall */}
        <RecallPanel
          query={recallQuery}
          onQueryChange={setRecallQuery}
          onSearch={runRecall}
          busy={recallBusy}
          hits={recallHits}
          error={recallError}
        />
      </div>
    </div>
  );
}

// ─── Recall panel ────────────────────────────────────────────────────────────

interface RecallPanelProps {
  query: string;
  onQueryChange: (v: string) => void;
  onSearch: () => void;
  busy: boolean;
  hits: RecallHit[] | null;
  error: string | null;
}

function RecallPanel({ query, onQueryChange, onSearch, busy, hits, error }: RecallPanelProps) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") onSearch();
    },
    [onSearch],
  );

  return (
    <Panel title="RECALL">
      {/* Search row */}
      <div
        style={{
          display: "flex",
          gap: 6,
          marginBottom: 8,
        } as CSSProperties}
      >
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="search past turns…"
          disabled={busy}
          style={{
            flex: 1,
            background: "var(--ops-bg-input)",
            border: "1px solid var(--ops-line)",
            color: "var(--ops-fg)",
            padding: "5px 8px",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            borderRadius: 2,
            outline: "none",
          } as CSSProperties}
        />
        <OpsButton
          variant="default"
          onClick={onSearch}
          disabled={busy || !query.trim()}
          style={{ padding: "5px 10px", fontSize: 10 } as CSSProperties}
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : "GO"}
        </OpsButton>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            fontSize: 10,
            color: "var(--ops-crit)",
            fontFamily: "var(--ops-mono)",
            marginBottom: 6,
          } as CSSProperties}
        >
          {error}
        </div>
      )}

      {/* No results yet */}
      {hits === null && !error && <Hatch label="NO MATCHES" height={52} />}

      {/* Empty results */}
      {hits !== null && hits.length === 0 && <Hatch label="NO MATCHES" height={52} />}

      {/* Results */}
      {hits !== null && hits.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 } as CSSProperties}>
          {hits.map((hit, i) => (
            <RecallHitRow key={i} hit={hit} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function RecallHitRow({ hit }: { hit: RecallHit }) {
  const shortTs = hit.ts ? hit.ts.slice(0, 16).replace("T", " ") : "—";
  const snippet = hit.text.length > 140 ? hit.text.slice(0, 140) + "…" : hit.text;
  return (
    <div
      style={{
        padding: "5px 8px",
        border: "1px solid var(--ops-line)",
        borderLeft: `2px solid ${hit.role === "user" ? "var(--ops-amber)" : "var(--ops-ok)"}`,
        display: "flex",
        flexDirection: "column",
        gap: 3,
      } as CSSProperties}
    >
      {/* Top row: score + role badge */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 9,
          fontFamily: "var(--ops-mono)",
        } as CSSProperties}
      >
        <span
          style={{
            color: "var(--ops-fg-dim)",
            fontVariantNumeric: "tabular-nums",
            minWidth: 38,
          } as CSSProperties}
        >
          {hit.score.toFixed(3)}
        </span>
        <Tag kind={hit.role === "user" ? "amber" : "ok"}>
          {hit.role.toUpperCase()}
        </Tag>
        <span
          style={{
            color: "var(--ops-fg-faint)",
            fontFamily: "var(--ops-mono)",
            fontSize: 9,
            marginLeft: "auto",
          } as CSSProperties}
        >
          {shortTs}
        </span>
      </div>
      {/* Snippet */}
      <div
        style={{
          fontSize: 10,
          fontFamily: "var(--ops-sans)",
          color: "var(--ops-fg-mute)",
          lineHeight: 1.4,
          wordBreak: "break-word",
        } as CSSProperties}
      >
        {snippet}
      </div>
    </div>
  );
}

// ─── Empty state ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div
      style={{
        margin: "auto",
        textAlign: "center",
        color: "var(--ops-fg-faint)",
        fontSize: 11,
        letterSpacing: "0.16em",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 16,
        padding: "40px 0",
      } as CSSProperties}
    >
      <BrandMark className="scale-[2.8]" />
      <div>
        <div
          style={{
            fontFamily: "var(--ops-sans)",
            fontSize: 14,
            letterSpacing: "0.12em",
            color: "var(--ops-fg-dim)",
            fontWeight: 600,
            marginBottom: 6,
          } as CSSProperties}
        >
          JARVIS · STANDING BY
        </div>
        <div
          style={{
            color: "var(--ops-fg-faint)",
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            letterSpacing: "0.06em",
          } as CSSProperties}
        >
          Ask anything · I&apos;ll route it.
        </div>
      </div>
    </div>
  );
}

// ─── Turn view ───────────────────────────────────────────────────────────────

function TurnView({ turn }: { turn: Turn }) {
  const time = stamp();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 } as CSSProperties}>
      {/* User bubble */}
      <div style={{ alignSelf: "flex-end", maxWidth: "72%" } as CSSProperties}>
        <div
          style={{
            fontSize: 9,
            letterSpacing: "0.16em",
            color: "var(--ops-amber)",
            marginBottom: 4,
            textAlign: "right",
            fontFamily: "var(--ops-mono)",
          } as CSSProperties}
        >
          {turn.userOverride && (
            <span
              style={{
                marginRight: 6,
                border: "1px solid var(--ops-amber)",
                padding: "1px 4px",
                fontSize: 8,
              } as CSSProperties}
            >
              <Lock
                style={{ display: "inline", width: 8, height: 8, marginRight: 2 } as CSSProperties}
              />
              {turn.userOverride.toUpperCase()}
            </span>
          )}
          YOU · {time}
        </div>
        <div
          style={{
            background: "rgba(242,160,61,0.08)",
            border: "1px solid var(--ops-amber)",
            padding: "10px 14px",
            fontSize: 13,
            fontFamily: "var(--ops-sans)",
            lineHeight: 1.5,
            color: "var(--ops-fg)",
            borderRadius: 2,
          } as CSSProperties}
        >
          {turn.user}
        </div>
      </div>

      {/* Model badge */}
      {turn.model && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 10,
            fontFamily: "var(--ops-mono)",
            color: "var(--ops-fg-dim)",
          } as CSSProperties}
        >
          <Tag kind="default">{modelLabel(turn.model)}</Tag>
          {turn.routeReason && (
            <span style={{ color: "var(--ops-fg-faint)", fontStyle: "italic", fontSize: 10 } as CSSProperties}>
              {turn.routeReason}
            </span>
          )}
        </div>
      )}

      {/* Delegation trace */}
      {turn.toolCalls.length > 0 && <DelegationTrace calls={turn.toolCalls} />}

      {/* Error */}
      {turn.errorMessage && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            border: "1px solid var(--ops-crit)",
            padding: "8px 12px",
            fontSize: 11,
            color: "var(--ops-crit)",
            fontFamily: "var(--ops-mono)",
          } as CSSProperties}
        >
          <AlertTriangle style={{ width: 14, height: 14, flexShrink: 0 } as CSSProperties} />
          {turn.errorMessage}
        </div>
      )}

      {/* Thinking */}
      {turn.thinking && <ThinkingPanel thinking={turn.thinking} />}

      {/* Response bubble */}
      {turn.text && (
        <div style={{ alignSelf: "flex-start", maxWidth: "85%" } as CSSProperties}>
          <div
            style={{
              fontSize: 9,
              letterSpacing: "0.16em",
              color: "var(--ops-ok)",
              marginBottom: 4,
              fontFamily: "var(--ops-mono)",
            } as CSSProperties}
          >
            {turn.status === "streaming" && (
              <span
                className="ops-live-dot"
                style={{ display: "inline-block", marginRight: 6 } as CSSProperties}
              />
            )}
            JARVIS · {time}
          </div>
          <div
            style={{
              background: "var(--ops-bg-elevated)",
              border: "1px solid var(--ops-line)",
              padding: "10px 14px",
              fontSize: 13,
              fontFamily: "var(--ops-sans)",
              lineHeight: 1.55,
              color: "var(--ops-fg)",
              borderRadius: 2,
              whiteSpace: "pre-wrap",
            } as CSSProperties}
          >
            {turn.text}
            {turn.status === "streaming" && (
              <span
                style={{
                  display: "inline-block",
                  width: 6,
                  height: 12,
                  background: "var(--ops-fg)",
                  marginLeft: 2,
                  verticalAlign: "middle",
                  animation: "ops-caret-blink 1s step-end infinite",
                } as CSSProperties}
              />
            )}
          </div>
        </div>
      )}

      {/* Cost/duration row */}
      {turn.status !== "streaming" && (turn.costUsd !== undefined || turn.durationMs !== undefined) && (
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 12,
            fontSize: 10,
            color: "var(--ops-fg-faint)",
            fontFamily: "var(--ops-mono)",
          } as CSSProperties}
        >
          {turn.durationMs !== undefined && <span>{(turn.durationMs / 1000).toFixed(1)}s</span>}
          {turn.costUsd !== undefined && <span>${turn.costUsd.toFixed(4)}</span>}
        </div>
      )}
    </div>
  );
}

// ─── Thinking panel ──────────────────────────────────────────────────────────

function ThinkingPanel({ thinking }: { thinking: string }) {
  return (
    <details
      style={{
        border: "1px solid var(--ops-line)",
        padding: "6px 10px",
        fontSize: 10,
        fontFamily: "var(--ops-mono)",
      } as CSSProperties}
    >
      <summary
        style={{
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 6,
          color: "var(--ops-fg-dim)",
          listStyle: "none",
        } as CSSProperties}
      >
        <Brain style={{ width: 12, height: 12 } as CSSProperties} />
        THINKING
      </summary>
      <pre
        style={{
          marginTop: 6,
          color: "var(--ops-fg-faint)",
          whiteSpace: "pre-wrap",
          lineHeight: 1.6,
          fontSize: 10,
        } as CSSProperties}
      >
        {thinking}
      </pre>
    </details>
  );
}

// ─── Delegation trace ────────────────────────────────────────────────────────

function DelegationTrace({ calls }: { calls: ToolCall[] }) {
  const isMobile = useIsMobile();
  return (
    <div
      style={{
        background: "var(--ops-bg-panel)",
        border: "1px solid var(--ops-line)",
        borderLeft: "2px solid var(--ops-ok)",
        padding: "8px 10px",
        fontSize: 11,
        fontFamily: "var(--ops-mono)",
      } as CSSProperties}
    >
      <div
        style={{
          fontSize: 9,
          letterSpacing: "0.18em",
          color: "var(--ops-fg-dim)",
          marginBottom: 8,
        } as CSSProperties}
      >
        DISPATCH PLAN · {calls.length} STEP{calls.length !== 1 ? "S" : ""}
      </div>
      {calls.map((c, i) => {
        const identity = getAgentIdentity(c.agent);
        const status = c.result ? (c.result.isError ? "error" : "ok") : "running";
        const needsConfirm = c.result?.parsed?.needs_confirm;
        const intent = c.result?.parsed?.intent;
        return (
          <div
            key={c.toolUseId}
            style={{
              display: "grid",
              gridTemplateColumns: isMobile ? "20px 1fr auto" : "20px 100px 1fr 80px",
              gridTemplateAreas: isMobile ? "'idx agent status' 'idx action action'" : undefined,
              rowGap: isMobile ? 2 : 0,
              gap: 8,
              padding: "4px 0",
              alignItems: "center",
              opacity: status === "running" ? 0.7 : 1,
            } as CSSProperties}
          >
            <span
              style={{ color: "var(--ops-fg-faint)", fontSize: 9, gridArea: isMobile ? "idx" : undefined } as CSSProperties}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                minWidth: 0,
                gridArea: isMobile ? "agent" : undefined,
              } as CSSProperties}
            >
              {identity ? (
                <>
                  <AgentGlyph agent={identity} size={14} />
                  <span
                    style={{
                      color: identity.colorHex,
                      fontSize: 10,
                      letterSpacing: "0.08em",
                    } as CSSProperties}
                  >
                    {identity.name}
                  </span>
                </>
              ) : (
                <span style={{ color: "var(--ops-fg-dim)", fontSize: 10 } as CSSProperties}>
                  {c.agent || "?"}
                </span>
              )}
            </span>
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                color: "var(--ops-fg-mute)",
                fontSize: 10,
                minWidth: 0,
                flexWrap: "wrap",
                gridArea: isMobile ? "action" : undefined,
              } as CSSProperties}
            >
              <ArrowRight style={{ width: 10, height: 10, flexShrink: 0 } as CSSProperties} />
              <span style={{ wordBreak: "break-word" } as CSSProperties}>{c.action || "?"}</span>
              {needsConfirm && <Tag kind="amber">CONFIRM</Tag>}
              {intent && status === "ok" && (
                <span style={{ color: "var(--ops-fg-faint)", fontSize: 9, wordBreak: "break-word" } as CSSProperties}>
                  → {intent}
                </span>
              )}
            </span>
            <span style={{ textAlign: "right", gridArea: isMobile ? "status" : undefined } as CSSProperties}>
              {status === "ok" && <Tag kind="ok">✓ DONE</Tag>}
              {status === "running" && <Tag kind="amber">▸ RUN</Tag>}
              {status === "error" && <Tag kind="crit">✕ ERR</Tag>}
            </span>
          </div>
        );
      })}
    </div>
  );
}
