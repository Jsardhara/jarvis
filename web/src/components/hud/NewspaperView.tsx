"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api-client";

interface InboxEvent {
  ts: string;
  agent: string;
  severity?: string;
  summary: string;
  detail?: string;
  url?: string;
  tag?: string;
}

const JARVIS_API =
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765";

const TAG_FROM_AGENT: Record<string, string> = {
  atlas: "TRADE",
  lens: "RESEARCH",
  scholar: "STUDY",
  forge: "CODE",
  tempo: "MAIL",
  sentinel: "SYSTEM",
};

const TAG_COLOR: Record<string, string> = {
  TRADE: "var(--ops-agent-atlas)",
  RESEARCH: "var(--ops-agent-lens)",
  STUDY: "var(--ops-agent-scholar)",
  CODE: "var(--ops-agent-forge)",
  MAIL: "var(--ops-agent-tempo)",
  SYSTEM: "var(--ops-agent-sentinel)",
  ALERT: "var(--ops-crit)",
};

/**
 * Newspaper-style 2-col editorial grid for inbox events. Section headers
 * group by agent (renamed: ATLAS / LENS → TRADE / RESEARCH etc.).
 */
export function NewspaperView() {
  const [events, setEvents] = useState<InboxEvent[]>([]);
  const [filter, setFilter] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await apiFetch(`${JARVIS_API}/api/inbox?limit=80`);
        if (r.ok && !cancelled) {
          const j = (await r.json()) as { data?: InboxEvent[] };
          setEvents(j.data ?? []);
        }
      } catch {
        /* tolerate */
      }
    };
    void tick();
    const id = setInterval(tick, 12_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const grouped = useMemo(() => groupByTag(events), [events]);
  const tags = Object.keys(grouped);
  const visibleTags = filter ? tags.filter((t) => t === filter) : tags;

  return (
    <div className="relative flex h-[calc(100vh-44px)] flex-col gap-3 overflow-hidden p-4">
      <div aria-hidden className="hud-scan-line" />

      <header className="flex items-center justify-between border-b border-[var(--ops-line-faint)] pb-2">
        <div className="flex items-center gap-3">
          <span
            className="hud-display hud-text-glow"
            style={{ color: "var(--hud-cyan)", fontSize: 14 }}
          >
            JARVIS // DAILY DISPATCH
          </span>
          <span
            className="font-mono text-[9px] tracking-widest"
            style={{ color: "var(--ops-fg-faint)" }}
          >
            {events.length} EVENTS · {tags.length} SECTIONS
          </span>
        </div>
        <div className="flex items-center gap-2">
          <FilterPill
            label="ALL"
            active={filter === null}
            onClick={() => setFilter(null)}
          />
          {tags.map((t) => (
            <FilterPill
              key={t}
              label={t}
              active={filter === t}
              color={TAG_COLOR[t]}
              onClick={() => setFilter(t)}
            />
          ))}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto pr-2">
        {visibleTags.length === 0 && (
          <div className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
            quiet wire — no events to surface.
          </div>
        )}
        {visibleTags.map((tag) => (
          <Section
            key={tag}
            tag={tag}
            color={TAG_COLOR[tag] ?? "var(--hud-cyan)"}
            items={grouped[tag]}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Subcomponents ───────────────────────────────────────────────────────────

function FilterPill({
  label,
  active,
  color,
  onClick,
}: {
  label: string;
  active: boolean;
  color?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="hud-pill"
      style={{
        color: color ?? "var(--hud-cyan)",
        background: active ? "rgba(0, 229, 255, 0.14)" : "transparent",
      }}
    >
      {label}
    </button>
  );
}

function Section({
  tag,
  color,
  items,
}: {
  tag: string;
  color: string;
  items: InboxEvent[];
}) {
  return (
    <section className="mb-6">
      {/* Section divider */}
      <div className="mb-2 flex items-center gap-3">
        <span
          className="hud-display"
          style={{ color, fontSize: 13 }}
        >
          {tag}
        </span>
        <div
          className="h-px flex-1"
          style={{ background: color, opacity: 0.3 }}
        />
        <span
          className="font-mono text-[9px] tracking-widest"
          style={{ color: "var(--ops-fg-faint)" }}
        >
          {items.length} ITEMS
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {items.slice(0, 12).map((e, i) => (
          <Article key={i} event={e} color={color} tag={tag} />
        ))}
      </div>
    </section>
  );
}

function Article({
  event,
  color,
  tag,
}: {
  event: InboxEvent;
  color: string;
  tag: string;
}) {
  const isAlert = event.severity === "alert";
  return (
    <article
      className="hud-panel hud-corners flex flex-col gap-2 px-4 py-3"
      style={{
        borderColor: isAlert ? "var(--ops-crit)" : undefined,
        boxShadow: isAlert ? "0 0 8px rgba(255, 59, 59, 0.30)" : undefined,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <h3
          className="text-[14px] font-bold leading-tight text-[var(--ops-fg)]"
          style={{ fontFamily: "var(--ops-sans)", letterSpacing: "0.02em" }}
        >
          {event.summary}
        </h3>
        <span
          className="hud-pill shrink-0"
          style={{ color: isAlert ? "var(--ops-crit)" : color }}
        >
          {isAlert ? "ALERT" : tag}
        </span>
      </div>
      {event.detail && (
        <p
          className="line-clamp-3 text-[10.5px] leading-relaxed text-[var(--ops-fg-mute)]"
          style={{ fontFamily: "var(--ops-sans)" }}
        >
          {event.detail}
        </p>
      )}
      <div className="flex items-center justify-between border-t border-[var(--ops-line-faint)] pt-1.5">
        <span
          className="font-mono text-[8px] uppercase tracking-widest"
          style={{ color: "var(--ops-fg-faint)" }}
        >
          {event.agent ?? "system"} · {fmtTime(event.ts ?? "")}
        </span>
        {event.url && (
          <a
            href={event.url}
            target="_blank"
            rel="noreferrer noopener"
            className="font-mono text-[8px] uppercase tracking-widest"
            style={{ color: "var(--hud-cyan)" }}
          >
            SOURCE →
          </a>
        )}
      </div>
    </article>
  );
}

function groupByTag(events: InboxEvent[]): Record<string, InboxEvent[]> {
  const out: Record<string, InboxEvent[]> = {};
  for (const e of events) {
    const agentKey = (e.agent ?? "").toLowerCase();
    const tag =
      e.severity === "alert"
        ? "ALERT"
        : (e.tag?.toUpperCase() || TAG_FROM_AGENT[agentKey] || "FEED");
    (out[tag] ??= []).push(e);
  }
  return out;
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
