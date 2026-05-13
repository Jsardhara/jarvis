"use client";

import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { apiFetch } from "@/lib/api-client";

interface PortfolioRow {
  symbol: string;
  price: number;
  delta_pct: number;
}

interface NewsItem {
  ts: string;
  agent: string;
  summary: string;
}

const JARVIS_API =
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765";

/**
 * HUD left rail — portfolio prices + LATEST inbox news.
 */
export function LeftSidebar() {
  const [positions, setPositions] = useState<PortfolioRow[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await apiFetch(`${JARVIS_API}/atlas/positions`);
        if (r.ok && !cancelled) {
          const j = (await r.json()) as { data?: PortfolioRow[] };
          setPositions(j.data ?? []);
        }
      } catch {
        /* offline tolerated */
      }
      try {
        const r2 = await apiFetch(`${JARVIS_API}/api/inbox?limit=8`);
        if (r2.ok && !cancelled) {
          const j = (await r2.json()) as { data?: NewsItem[] };
          setNews(j.data ?? []);
        }
      } catch {
        /* offline tolerated */
      }
    };
    void tick();
    const id = setInterval(tick, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <aside
      aria-label="Markets and news"
      className="flex h-full w-full flex-col gap-3"
    >
      {/* Portfolio panel */}
      <section className="hud-panel hud-corners flex flex-col gap-1.5 px-3 py-2.5">
        <header className="hud-label">{"// PORTFOLIO"}</header>
        {positions.length === 0 && (
          <div className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
            no positions
          </div>
        )}
        {positions.slice(0, 8).map((p) => {
          const up = p.delta_pct >= 0;
          const color = up ? "var(--ops-ok)" : "var(--ops-crit)";
          return (
            <div
              key={p.symbol}
              className="flex items-center justify-between border-b border-[var(--ops-line-faint)] py-1 last:border-b-0"
            >
              <span className="font-mono text-[10.5px] tracking-wider text-[var(--ops-fg)]">
                {p.symbol}
              </span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10.5px] text-[var(--ops-fg-mute)] tabular-nums">
                  {p.price.toFixed(2)}
                </span>
                <span
                  className="flex items-center gap-0.5 font-mono text-[9.5px] tabular-nums"
                  style={{ color }}
                >
                  {up ? (
                    <ArrowUpRight className="h-2.5 w-2.5" />
                  ) : (
                    <ArrowDownRight className="h-2.5 w-2.5" />
                  )}
                  {Math.abs(p.delta_pct).toFixed(2)}%
                </span>
              </div>
            </div>
          );
        })}
      </section>

      {/* News panel */}
      <section className="hud-panel hud-corners flex min-h-0 flex-1 flex-col gap-1.5 px-3 py-2.5">
        <header className="hud-label">{"// LATEST"}</header>
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
          {news.length === 0 && (
            <div className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
              quiet…
            </div>
          )}
          {news.map((n, i) => (
            <div
              key={i}
              className="border-b border-[var(--ops-line-faint)] py-1 last:border-b-0"
            >
              <div className="font-mono text-[8px] uppercase tracking-widest text-[var(--hud-cyan)]">
                {n.agent}
              </div>
              <div className="line-clamp-2 font-mono text-[10px] leading-snug text-[var(--ops-fg-mute)]">
                {n.summary}
              </div>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
