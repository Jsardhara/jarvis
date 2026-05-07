"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog,
  CommandInput,
  CommandList,
} from "@/components/ui/command";
import { Hatch } from "@/components/ops/Hatch";
import { SubH } from "@/components/ops/SubH";

const JARVIS_API =
  process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765";

// ── Types ─────────────────────────────────────────────────────────────────────

type HitKind =
  | "inbox"
  | "task"
  | "decision"
  | "agent_log"
  | "chat"
  | "problem"
  | "exam"
  | "forge_run";

interface SearchHit {
  kind: HitKind;
  id: string;
  title: string;
  snippet: string;
  ts: string;
  score: number;
  href: string;
  metadata: Record<string, unknown>;
}

// ── Kind metadata ─────────────────────────────────────────────────────────────

const KIND_META: Record<
  HitKind,
  { badge: string; label: string }
> = {
  inbox: { badge: "[I]", label: "INBOX" },
  task: { badge: "[T]", label: "TASKS" },
  decision: { badge: "[D]", label: "DECISIONS" },
  agent_log: { badge: "[A]", label: "ACTIVITY" },
  chat: { badge: "[C]", label: "CHAT" },
  problem: { badge: "[P]", label: "PROBLEMS" },
  exam: { badge: "[E]", label: "EXAMS" },
  forge_run: { badge: "[F]", label: "FORGE" },
};

const KIND_ORDER: HitKind[] = [
  "inbox",
  "task",
  "decision",
  "agent_log",
  "chat",
  "problem",
  "exam",
  "forge_run",
];

// ── Debounce hook ─────────────────────────────────────────────────────────────

function useDebounce(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

// ── useSearch ─────────────────────────────────────────────────────────────────

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; hits: SearchHit[] }
  | { status: "error"; message: string };

function useSearch(query: string): SearchState {
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (!debouncedQuery.trim()) {
      setState({ status: "idle" });
      return;
    }

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setState({ status: "loading" });

    const url = `${JARVIS_API}/api/search?q=${encodeURIComponent(debouncedQuery)}&limit_per_kind=5`;

    fetch(url, { signal: ac.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<{ data: SearchHit[]; error: string | null }>;
      })
      .then((body) => {
        if (body.error) throw new Error(body.error);
        setState({ status: "ok", hits: body.data });
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") return;
        const msg = err instanceof Error ? err.message : "Search failed";
        setState({ status: "error", message: msg });
      });

    return () => ac.abort();
  }, [debouncedQuery]);

  return state;
}

// ── SearchDialog ──────────────────────────────────────────────────────────────

export function SearchDialog() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();
  const searchState = useSearch(query);

  // ⌘K / Ctrl+K toggle
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Reset query on close
  const handleOpenChange = useCallback((next: boolean) => {
    setOpen(next);
    if (!next) setQuery("");
  }, []);

  const handleSelect = useCallback(
    (href: string) => {
      handleOpenChange(false);
      router.push(href);
    },
    [router, handleOpenChange]
  );

  // Group hits by kind
  const grouped = (() => {
    if (searchState.status !== "ok") return null;
    const map = new Map<HitKind, SearchHit[]>();
    for (const hit of searchState.hits) {
      const bucket = map.get(hit.kind) ?? [];
      bucket.push(hit);
      map.set(hit.kind, bucket);
    }
    return map;
  })();

  return (
    <CommandDialog open={open} onOpenChange={handleOpenChange}>
      <CommandInput
        placeholder="Search inbox, tasks, decisions, activity, chat…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList className="max-h-[480px]">
        {/* Idle / empty query */}
        {searchState.status === "idle" && (
          <Hatch label="TYPE TO SEARCH" height={96} className="m-2" />
        )}

        {/* Loading */}
        {searchState.status === "loading" && (
          <div className="flex items-center justify-center py-8">
            <span
              className="inline-block h-4 w-4 animate-spin rounded-full border-2"
              style={{
                borderColor: "var(--ops-fg-faint)",
                borderTopColor: "var(--ops-accent)",
              }}
            />
          </div>
        )}

        {/* Error */}
        {searchState.status === "error" && (
          <div
            className="mx-2 my-2 flex items-center gap-3 rounded px-3 py-2 text-xs font-mono"
            style={{
              background: "color-mix(in srgb, var(--ops-crit) 12%, transparent)",
              border: "1px solid var(--ops-crit)",
              color: "var(--ops-crit)",
            }}
          >
            <span className="flex-1 truncate">ERR: {searchState.message}</span>
            <button
              onClick={() => setQuery((q) => q + " ")}
              className="shrink-0 underline hover:no-underline"
            >
              retry
            </button>
          </div>
        )}

        {/* Results */}
        {searchState.status === "ok" && grouped && grouped.size === 0 && (
          <Hatch label="NO RESULTS" height={80} className="m-2" />
        )}

        {searchState.status === "ok" &&
          grouped &&
          grouped.size > 0 &&
          KIND_ORDER.filter((k) => grouped.has(k)).map((kind) => {
            const hits = grouped.get(kind)!;
            const meta = KIND_META[kind];
            return (
              <div key={kind} className="px-2 pb-1">
                <SubH className="px-1 pt-2 pb-1">{meta.label}</SubH>
                {hits.map((hit, idx) => (
                  <ResultRow
                    key={`${kind}-${hit.id}-${idx}`}
                    hit={hit}
                    badge={meta.badge}
                    onSelect={handleSelect}
                  />
                ))}
              </div>
            );
          })}
      </CommandList>
    </CommandDialog>
  );
}

// ── ResultRow ─────────────────────────────────────────────────────────────────

interface ResultRowProps {
  hit: SearchHit;
  badge: string;
  onSelect: (href: string) => void;
}

function ResultRow({ hit, badge, onSelect }: ResultRowProps) {
  return (
    <button
      onClick={() => onSelect(hit.href)}
      className="group flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm transition-colors focus:outline-none focus-visible:ring-1"
      style={
        {
          "--tw-ring-color": "var(--ops-accent)",
        } as React.CSSProperties
      }
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.background =
          "color-mix(in srgb, var(--ops-accent) 8%, transparent)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.background = "transparent";
      }}
    >
      {/* Kind badge */}
      <span
        className="shrink-0 font-mono text-[10px] leading-none"
        style={{ color: "var(--ops-fg-faint)" }}
      >
        {badge}
      </span>

      {/* Title + snippet */}
      <span className="min-w-0 flex-1">
        <span
          className="block truncate text-xs font-medium leading-tight"
          style={{ color: "var(--ops-fg)" }}
        >
          {hit.title}
        </span>
        <span
          className="block truncate text-[11px] leading-snug"
          style={{ color: "var(--ops-fg-faint)" }}
        >
          {hit.snippet}
        </span>
      </span>

      {/* Score */}
      <span
        className="shrink-0 font-mono text-[10px] tabular-nums"
        style={{ color: "var(--ops-fg-faint)" }}
      >
        {hit.score.toFixed(2)}
      </span>
    </button>
  );
}
