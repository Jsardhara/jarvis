"use client";

import { CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { Hatch, Kbd, OpsButton, Panel, SubH, Tag } from "@/components/ops";
import type { DueCard } from "@/hooks/use-scholar";
import { useRateDueCard } from "@/hooks/use-scholar";
import { ApiBanner } from "./shared";

// ─── Rating definitions ───────────────────────────────────────────────────────

const RATING_LABELS: { rating: 0 | 1 | 2 | 3 | 4 | 5; label: string }[] = [
  { rating: 0, label: "0 · BLACKOUT" },
  { rating: 1, label: "1 · WRONG" },
  { rating: 2, label: "2 · BARELY" },
  { rating: 3, label: "3 · OK" },
  { rating: 4, label: "4 · GOOD" },
  { rating: 5, label: "5 · PERFECT" },
];

// ─── Progress strip ───────────────────────────────────────────────────────────

interface ProgressStripProps {
  done: number;
  total: number;
}

function ProgressStrip({ done, total }: ProgressStripProps) {
  if (total === 0) return null;
  const blocks = Math.min(total, 20);
  const doneBlocks = Math.round((done / total) * blocks);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 14px",
        borderBottom: "1px solid var(--ops-line)",
        background: "var(--ops-bg-deep)",
      } as CSSProperties}
    >
      <div style={{ display: "flex", gap: 2, flex: 1 }}>
        {Array.from({ length: blocks }).map((_, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: 4,
              borderRadius: 1,
              background: i < doneBlocks ? "var(--ops-ok)" : "var(--ops-line-strong)",
              transition: "background 200ms var(--ease-out-expo, ease-out)",
            } as CSSProperties}
          />
        ))}
      </div>
      <span
        style={{
          fontFamily: "var(--ops-mono)",
          fontSize: 9,
          color: "var(--ops-fg-faint)",
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "0.08em",
          whiteSpace: "nowrap",
        } as CSSProperties}
      >
        {done}/{total}
      </span>
    </div>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface ReviewQueueProps {
  cards: DueCard[];
  loading: boolean;
  error: string | null;
  onRefetch: () => void;
  hasAnyDocs: boolean;
  onImportSeed: () => void;
  importing: boolean;
  onCardRated?: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ReviewQueue({
  cards,
  loading,
  error,
  onRefetch,
  hasAnyDocs,
  onImportSeed,
  importing,
  onCardRated,
}: ReviewQueueProps) {
  const { rate, loading: rating } = useRateDueCard();
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  // flash state: null | "ok" | "miss"
  const [flash, setFlash] = useState<"ok" | "miss" | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const remaining = cards.slice(index);
  const current = remaining[0] ?? null;
  const done = index;

  const handleReveal = useCallback(() => setRevealed(true), []);

  const handleRate = useCallback(
    async (r: 0 | 1 | 2 | 3 | 4 | 5) => {
      if (!current || rating) return;
      // flash colour
      const flashKind = r >= 3 ? "ok" : "miss";
      setFlash(flashKind);
      if (flashTimer.current) clearTimeout(flashTimer.current);
      flashTimer.current = setTimeout(() => {
        setFlash(null);
        setRevealed(false);
        setIndex((i) => i + 1);
      }, 350);
      await rate(current.id, r);
      onCardRated?.();
    },
    [current, rate, rating, onCardRated],
  );

  // Keyboard shortcuts: Space=reveal, 0-5=rate, J=next(skip), K=prev
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Don't intercept when user is typing in an input
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (e.key === " " || e.key === "Space") {
        e.preventDefault();
        if (!revealed && current) handleReveal();
      } else if (revealed && current && /^[0-5]$/.test(e.key)) {
        e.preventDefault();
        void handleRate(Number(e.key) as 0 | 1 | 2 | 3 | 4 | 5);
      } else if (e.key === "j" || e.key === "J") {
        if (current) {
          setRevealed(false);
          setIndex((i) => i + 1);
        }
      } else if (e.key === "k" || e.key === "K") {
        setIndex((i) => Math.max(0, i - 1));
        setRevealed(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, revealed, handleReveal, handleRate]);

  // Reset index when new cards arrive
  useEffect(() => {
    setIndex(0);
    setRevealed(false);
  }, [cards]);

  const headerTrailing = (
    <Tag kind={loading ? "info" : remaining.length > 0 ? "amber" : "ok"}>
      {loading ? "LOADING" : `${remaining.length} DUE`}
    </Tag>
  );

  const flashBorderColor =
    flash === "ok"
      ? "var(--ops-ok)"
      : flash === "miss"
        ? "var(--ops-crit)"
        : "var(--ops-line-strong)";

  return (
    <Panel
      title={`REVIEW QUEUE · ${loading ? "…" : remaining.length} DUE`}
      trailing={headerTrailing}
      bodyClassName="p-0"
      flushBody
      className="h-full"
    >
      {/* Progress strip */}
      <ProgressStrip done={done} total={cards.length} />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "calc(100% - 16px)",
          padding: 14,
          gap: 12,
          overflowY: "auto",
        } as CSSProperties}
      >
        {error && (
          <ApiBanner
            message="Scholar API not ready — retry in a moment"
            onRetry={onRefetch}
          />
        )}

        {!error && !loading && cards.length === 0 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
            <Hatch
              label={
                hasAnyDocs
                  ? "NO CARDS DUE · ALL CAUGHT UP"
                  : "NO CARDS DUE · IMPORT SEED OR UPLOAD DOC"
              }
              height={100}
            />
            {!hasAnyDocs && (
              <OpsButton
                variant="primary"
                onClick={onImportSeed}
                disabled={importing}
              >
                {importing ? "IMPORTING…" : "IMPORT LINALG SEED"}
              </OpsButton>
            )}
          </div>
        )}

        {!error && current && (
          <>
            <SubH
              trailing={
                <span
                  style={{ color: "var(--ops-fg-faint)", fontSize: 10 } as CSSProperties}
                >
                  {index + 1} / {cards.length}
                </span>
              }
            >
              CARD
            </SubH>

            {/* Card face — flip animation container */}
            <div
              style={{
                perspective: 800,
                minHeight: revealed ? "auto" : 80,
              } as CSSProperties}
            >
              {/* Front */}
              <div
                style={{
                  background: "var(--ops-bg-elevated)",
                  border: `1px solid ${flashBorderColor}`,
                  borderRadius: 2,
                  padding: "14px 16px",
                  fontFamily: "var(--ops-mono)",
                  fontSize: 12,
                  color: "var(--ops-fg)",
                  lineHeight: 1.6,
                  minHeight: 80,
                  transition: "border-color 200ms ease-out",
                } as CSSProperties}
              >
                {current.front}
              </div>
            </div>

            {!revealed ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <OpsButton variant="primary" onClick={handleReveal}>
                  REVEAL
                </OpsButton>
                {/* Keyboard hint */}
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    alignItems: "center",
                    justifyContent: "center",
                  } as CSSProperties}
                >
                  <Kbd>Space</Kbd>
                  <span
                    style={{
                      fontFamily: "var(--ops-mono)",
                      fontSize: 9,
                      color: "var(--ops-fg-faint)",
                    } as CSSProperties}
                  >
                    reveal
                  </span>
                  <Kbd>J</Kbd>
                  <span
                    style={{
                      fontFamily: "var(--ops-mono)",
                      fontSize: 9,
                      color: "var(--ops-fg-faint)",
                    } as CSSProperties}
                  >
                    skip
                  </span>
                </div>
              </div>
            ) : (
              <>
                {/* Back — animate in */}
                <div
                  style={{
                    background: "var(--ops-bg-deep)",
                    border: `1px solid ${flashBorderColor}`,
                    borderRadius: 2,
                    padding: "14px 16px",
                    fontFamily: "var(--ops-mono)",
                    fontSize: 12,
                    color: "var(--ops-fg-mute)",
                    lineHeight: 1.6,
                    animation: "ops-fade-in 200ms ease-out",
                    transition: "border-color 200ms ease-out",
                  } as CSSProperties}
                >
                  {current.back}
                </div>

                {/* Concept tags */}
                {current.tags.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {current.tags.map((tag) => (
                      <Tag key={tag} kind="info">{tag}</Tag>
                    ))}
                  </div>
                )}

                {/* Rating grid */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 4,
                  } as CSSProperties}
                >
                  {RATING_LABELS.map(({ rating: r, label }) => (
                    <OpsButton
                      key={r}
                      variant={r >= 4 ? "primary" : r <= 1 ? "danger" : "default"}
                      onClick={() => void handleRate(r)}
                      disabled={rating || flash !== null}
                      style={{ fontSize: 9, padding: "5px 6px" } as CSSProperties}
                    >
                      {label}
                    </OpsButton>
                  ))}
                </div>

                {/* Keyboard hints */}
                <div
                  style={{
                    display: "flex",
                    gap: 4,
                    flexWrap: "wrap",
                    alignItems: "center",
                  } as CSSProperties}
                >
                  {([0, 1, 2, 3, 4, 5] as const).map((n) => (
                    <span
                      key={n}
                      style={{ display: "inline-flex", alignItems: "center", gap: 3 } as CSSProperties}
                    >
                      <Kbd>{String(n)}</Kbd>
                    </span>
                  ))}
                  <span
                    style={{
                      fontFamily: "var(--ops-mono)",
                      fontSize: 9,
                      color: "var(--ops-fg-faint)",
                      marginLeft: 4,
                    } as CSSProperties}
                  >
                    rate
                  </span>
                </div>
              </>
            )}
          </>
        )}

        {/* All done */}
        {!error && !loading && cards.length > 0 && !current && (
          <Hatch label="SESSION COMPLETE · ALL CARDS REVIEWED" height={80} />
        )}
      </div>
    </Panel>
  );
}
