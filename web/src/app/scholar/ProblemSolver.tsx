"use client";

import { CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { Hatch, OpsButton, OpsField, SubH, Tag } from "@/components/ops";
import {
  type SolveResult,
  useRateProblem,
  useSolveProblem,
} from "@/hooks/use-scholar";
import { ApiBanner, writeLS } from "./shared";

const LS_PROBLEM = "scholar.lastproblem.v1";
const STEP_STAGGER_MS = 80;

interface ProblemSolverProps {
  course: string;
  initialProblem?: string;
  onSolved?: () => void;
  onRated?: (correct: boolean) => void;
}

// ─── Streaming step list ──────────────────────────────────────────────────────

interface StepListProps {
  steps: string[];
  visibleCount: number;
}

function StepList({ steps, visibleCount }: StepListProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 0,
        border: "1px solid var(--ops-line)",
        borderRadius: 2,
      } as CSSProperties}
    >
      {steps.slice(0, visibleCount).map((step, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            gap: 12,
            padding: "10px 14px",
            borderBottom:
              i < visibleCount - 1 ? "1px solid var(--ops-line)" : "none",
            fontFamily: "var(--ops-mono)",
            fontSize: 12,
            lineHeight: 1.55,
            animation: "ops-fade-in 200ms ease-out",
          } as CSSProperties}
        >
          <span
            style={{
              color: "var(--ops-amber)",
              minWidth: 18,
              fontWeight: 600,
            } as CSSProperties}
          >
            {i + 1}.
          </span>
          <span style={{ color: "var(--ops-fg)" }}>{step}</span>
        </div>
      ))}
      {visibleCount < steps.length && (
        <div
          style={{
            padding: "8px 14px",
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-faint)",
            letterSpacing: "0.1em",
          } as CSSProperties}
        >
          …
        </div>
      )}
    </div>
  );
}

// ─── Inline confirmation strip ────────────────────────────────────────────────

interface LoggedStripProps {
  onDone: () => void;
}

function LoggedStrip({ onDone }: LoggedStripProps) {
  const [countdown, setCountdown] = useState(3);

  useEffect(() => {
    if (countdown <= 0) {
      onDone();
      return;
    }
    const t = setTimeout(() => setCountdown((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown, onDone]);

  return (
    <div
      style={{
        padding: "10px 14px",
        background: "color-mix(in srgb, var(--ops-ok) 8%, transparent)",
        border: "1px solid var(--ops-ok)",
        borderRadius: 2,
        fontFamily: "var(--ops-mono)",
        fontSize: 11,
        color: "var(--ops-ok)",
        letterSpacing: "0.1em",
        display: "flex",
        alignItems: "center",
        gap: 10,
        animation: "ops-fade-in 200ms ease-out",
      } as CSSProperties}
    >
      <span>LOGGED · NEXT PROBLEM IN {countdown}…</span>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ProblemSolver({ course, initialProblem, onSolved, onRated }: ProblemSolverProps) {
  const [problem, setProblem] = useState<string>(initialProblem ?? "");
  const [result, setResult] = useState<SolveResult | null>(null);
  const [rated, setRated] = useState(false);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const staggerTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const { solve, loading: solving, error: solveErr } = useSolveProblem();
  const { rateProblem, loading: ratLoading } = useRateProblem();

  // Persist to localStorage
  useEffect(() => {
    writeLS(LS_PROBLEM, problem);
  }, [problem]);

  // When parent injects a new practice problem, scroll to textarea
  useEffect(() => {
    if (initialProblem) {
      setProblem(initialProblem);
      setResult(null);
      setRated(false);
      setVisibleSteps(0);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [initialProblem]);

  // Stagger steps reveal on new result
  useEffect(() => {
    if (!result) return;
    // Clear any previous timers
    staggerTimers.current.forEach(clearTimeout);
    staggerTimers.current = [];
    setVisibleSteps(0);

    result.steps.forEach((_, i) => {
      const t = setTimeout(() => {
        setVisibleSteps((n) => Math.max(n, i + 1));
      }, i * STEP_STAGGER_MS);
      staggerTimers.current.push(t);
    });

    return () => {
      staggerTimers.current.forEach(clearTimeout);
    };
  }, [result]);

  // Auto-resize textarea
  const handleTextareaChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setProblem(e.target.value);
      const el = e.target;
      el.style.height = "auto";
      const maxRows = 12;
      const lineHeight = 20;
      el.style.height = `${Math.min(el.scrollHeight, maxRows * lineHeight)}px`;
    },
    [],
  );

  const handleSolve = useCallback(async () => {
    if (!problem.trim()) return;
    const res = await solve(problem.trim(), course);
    if (res) {
      setResult(res);
      setRated(false);
      onSolved?.();
    }
  }, [problem, course, solve, onSolved]);

  // ⌘/Ctrl+Enter submits
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void handleSolve();
      }
    },
    [handleSolve],
  );

  const handleRate = useCallback(
    async (correct: boolean) => {
      if (!result) return;
      await rateProblem(result.id, correct);
      setRated(true);
      onRated?.(correct);
    },
    [result, rateProblem, onRated],
  );

  const handleClear = useCallback(() => {
    setProblem("");
    setResult(null);
    setRated(false);
    setVisibleSteps(0);
    writeLS(LS_PROBLEM, "");
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        gap: 12,
        padding: 14,
        overflowY: "auto",
      } as CSSProperties}
    >
      <SubH>PROBLEM INPUT</SubH>

      <OpsField>
        <textarea
          ref={textareaRef}
          rows={6}
          placeholder={`Paste a problem… (⌘/Ctrl+Enter to solve)`}
          value={problem}
          onChange={handleTextareaChange}
          onKeyDown={handleKeyDown}
          disabled={solving}
          style={{
            width: "100%",
            background: "var(--ops-bg-input)",
            border: "1px solid var(--ops-line)",
            color: "var(--ops-fg)",
            fontFamily: "var(--ops-mono)",
            fontSize: 12,
            padding: "8px 10px",
            borderRadius: 2,
            resize: "none",
            outline: "none",
            minHeight: "6lh",
            overflow: "auto",
            transition: "border-color 80ms",
            lineHeight: 1.5,
            opacity: solving ? 0.5 : 1,
          } as CSSProperties}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--ops-line-bright)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--ops-line)";
          }}
        />
      </OpsField>

      <div style={{ display: "flex", gap: 8 }}>
        <OpsButton
          variant="primary"
          onClick={() => void handleSolve()}
          disabled={solving || !problem.trim()}
        >
          {solving ? "SOLVING…" : "WALK ME THROUGH"}
        </OpsButton>
        {result && (
          <OpsButton onClick={handleClear}>CLEAR</OpsButton>
        )}
      </div>

      {solveErr && (
        <ApiBanner
          message={
            solveErr.includes("ANTHROPIC_API_KEY")
              ? "AI solver unavailable — ANTHROPIC_API_KEY not configured"
              : "Scholar API not ready — retry in a moment"
          }
          onRetry={() => void handleSolve()}
        />
      )}

      {result && (
        <>
          <SubH>SOLUTION</SubH>

          {/* Step-by-step with staggered reveal */}
          <StepList steps={result.steps} visibleCount={visibleSteps} />

          {/* Final answer */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                fontFamily: "var(--ops-mono)",
                fontSize: 10,
                color: "var(--ops-fg-dim)",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              } as CSSProperties}
            >
              FINAL ANSWER
            </span>
            <Tag kind="amber" solid>
              {result.final_answer}
            </Tag>
          </div>

          {/* Concepts used */}
          {result.concepts_used.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {result.concepts_used.map((c) => (
                <Tag key={c} kind="info">
                  {c}
                </Tag>
              ))}
            </div>
          )}

          {/* Rate or confirmation strip */}
          {!rated ? (
            <div style={{ display: "flex", gap: 8 }}>
              <OpsButton
                onClick={() => void handleRate(true)}
                disabled={ratLoading}
                style={{
                  borderColor: "var(--ops-ok)",
                  color: "var(--ops-ok)",
                } as CSSProperties}
              >
                I GOT IT
              </OpsButton>
              <OpsButton
                variant="danger"
                onClick={() => void handleRate(false)}
                disabled={ratLoading}
              >
                I MISSED IT
              </OpsButton>
            </div>
          ) : (
            <LoggedStrip onDone={handleClear} />
          )}
        </>
      )}
    </div>
  );
}
