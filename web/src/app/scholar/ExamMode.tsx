"use client";

import {
  CSSProperties,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { OpsButton, OpsField, OpsTextarea, SubH, Tag } from "@/components/ops";
import type { ExamProblem, ExamSession } from "@/hooks/use-scholar";
import { useRateProblem } from "@/hooks/use-scholar";

// ─── Timer ────────────────────────────────────────────────────────────────────

interface ExamTimerProps {
  endsIso: string;
  onExpire: () => void;
  paused: boolean;
  pausedSecondsRef: React.MutableRefObject<number>;
}

function ExamTimer({ endsIso, onExpire, paused, pausedSecondsRef }: ExamTimerProps) {
  const [remaining, setRemaining] = useState(() => {
    const ms = new Date(endsIso).getTime() - Date.now();
    return Math.max(0, Math.floor(ms / 1000));
  });
  const expiredRef = useRef(false);
  const lastTickRef = useRef(Date.now());

  useEffect(() => {
    if (paused) {
      lastTickRef.current = Date.now();
      return;
    }
    if (remaining <= 0) {
      if (!expiredRef.current) {
        expiredRef.current = true;
        onExpire();
      }
      return;
    }
    const t = setTimeout(() => {
      const now = Date.now();
      const elapsed = Math.floor((now - lastTickRef.current) / 1000);
      lastTickRef.current = now;
      setRemaining((s) => Math.max(0, s - elapsed));
    }, 1000);
    return () => clearTimeout(t);
  }, [remaining, onExpire, paused]);

  const min = Math.floor(remaining / 60);
  const sec = remaining % 60;
  const isCrit = remaining < 10;
  const isUrgent = remaining < 30;

  return (
    <span
      style={{
        fontFamily: "var(--ops-mono)",
        fontSize: 48,
        fontVariantNumeric: "tabular-nums",
        color: isCrit
          ? "var(--ops-crit)"
          : isUrgent
            ? "var(--ops-amber)"
            : "var(--ops-fg)",
        letterSpacing: "0.02em",
        animation: isCrit
          ? "ops-pulse-dot 0.6s infinite"
          : isUrgent
            ? "ops-pulse-dot 1s infinite"
            : "none",
        display: "block",
        lineHeight: 1,
      } as CSSProperties}
    >
      {String(min).padStart(2, "0")}:{String(sec).padStart(2, "0")}
    </span>
  );
}

// ─── Progress dots ────────────────────────────────────────────────────────────

interface ProgressDotsProps {
  total: number;
  current: number;
  answered: Set<number>;
}

function ProgressDots({ total, current, answered }: ProgressDotsProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: 5,
        flexWrap: "wrap",
      } as CSSProperties}
    >
      {Array.from({ length: total }).map((_, i) => {
        const isCur = i === current;
        const isDone = answered.has(i);
        return (
          <div
            key={i}
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: isCur
                ? "var(--ops-amber)"
                : isDone
                  ? "var(--ops-ok)"
                  : "var(--ops-line-strong)",
              border: isCur
                ? "1px solid var(--ops-amber-bright)"
                : "1px solid transparent",
              transition: "background 200ms ease-out",
              flexShrink: 0,
            } as CSSProperties}
          />
        );
      })}
    </div>
  );
}

// ─── Summary ──────────────────────────────────────────────────────────────────

interface SummaryViewProps {
  correct: number;
  total: number;
  course: string;
  startedIso: string;
  ratings: Record<number, boolean>;
  problems: ExamProblem[];
  onExit: () => void;
}

function SummaryView({
  correct,
  total,
  course,
  startedIso,
  ratings,
  problems,
  onExit,
}: SummaryViewProps) {
  const ratio = total > 0 ? correct / total : 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: 20,
        padding: 24,
        overflowY: "auto",
      } as CSSProperties}
    >
      <SubH>EXAM COMPLETE</SubH>
      <div
        style={{
          fontFamily: "var(--ops-mono)",
          fontSize: 48,
          color: ratio >= 0.7 ? "var(--ops-ok)" : "var(--ops-crit)",
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1,
        } as CSSProperties}
      >
        {correct} / {total}
      </div>
      <Tag kind={ratio >= 0.7 ? "ok" : "crit"} solid>
        {Math.round(ratio * 100)}% CORRECT
      </Tag>
      <div
        style={{
          fontFamily: "var(--ops-mono)",
          fontSize: 11,
          color: "var(--ops-fg-dim)",
        } as CSSProperties}
      >
        {course} · {new Date(startedIso).toLocaleDateString()}
      </div>

      {/* Per-problem summary */}
      {problems.length > 0 && (
        <div
          style={{
            width: "100%",
            maxWidth: 480,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          } as CSSProperties}
        >
          {problems.map((p, i) => {
            const hit = ratings[i];
            const text = p.prompt ?? p.problem ?? "";
            return (
              <div
                key={p.id}
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "flex-start",
                  padding: "8px 12px",
                  background: "var(--ops-bg-elevated)",
                  border: "1px solid var(--ops-line)",
                  borderLeft: `2px solid ${hit === true ? "var(--ops-ok)" : hit === false ? "var(--ops-crit)" : "var(--ops-line-strong)"}`,
                  borderRadius: 2,
                  fontFamily: "var(--ops-mono)",
                  fontSize: 11,
                } as CSSProperties}
              >
                <span
                  style={{
                    color: hit === true
                      ? "var(--ops-ok)"
                      : hit === false
                        ? "var(--ops-crit)"
                        : "var(--ops-fg-faint)",
                    minWidth: 14,
                    fontWeight: 700,
                  } as CSSProperties}
                >
                  {i + 1}.
                </span>
                <span
                  style={{
                    color: "var(--ops-fg-mute)",
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  } as CSSProperties}
                >
                  {text}
                </span>
                <Tag kind={hit === true ? "ok" : hit === false ? "crit" : "info"}>
                  {hit === true ? "HIT" : hit === false ? "MISS" : "SKIP"}
                </Tag>
              </div>
            );
          })}
        </div>
      )}

      <OpsButton variant="primary" onClick={onExit}>
        EXIT EXAM
      </OpsButton>
    </div>
  );
}

// ─── Exam problem card ────────────────────────────────────────────────────────

interface ProblemCardProps {
  problem: ExamProblem;
  idx: number;
  total: number;
  onRate: (correct: boolean) => Promise<void>;
  onNext: () => void;
  isLast: boolean;
}

function ProblemCard({
  problem,
  idx,
  total,
  onRate,
  onNext,
  isLast,
}: ProblemCardProps) {
  const [answer, setAnswer] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [rated, setRated] = useState<boolean | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleRate = useCallback(
    async (correct: boolean) => {
      await onRate(correct);
      setRated(correct);
    },
    [onRate],
  );

  // Cmd/Ctrl+Enter submits (moves to next)
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        onNext();
      }
    },
    [onNext],
  );

  // Auto-resize textarea
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setAnswer(e.target.value);
      const el = e.target;
      el.style.height = "auto";
      const maxHeight = 12 * 20; // 12 rows * ~20px
      el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    },
    [],
  );

  const problemText = problem.prompt ?? problem.problem ?? "";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 14,
      } as CSSProperties}
    >
      {/* Problem text */}
      <div
        style={{
          background: "var(--ops-bg-elevated)",
          border: "1px solid var(--ops-line-strong)",
          borderRadius: 2,
          padding: "14px 16px",
          fontFamily: "var(--ops-mono)",
          fontSize: 12,
          lineHeight: 1.65,
          color: "var(--ops-fg)",
        } as CSSProperties}
      >
        {problemText}
      </div>

      {/* Concept tags if available */}
      {problem.expected_concepts && problem.expected_concepts.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {problem.expected_concepts.map((c) => (
            <Tag key={c} kind="info">{c}</Tag>
          ))}
        </div>
      )}

      {/* Answer textarea */}
      <OpsField label="YOUR ANSWER">
        <textarea
          ref={textareaRef}
          rows={5}
          value={answer}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Write your answer here… (⌘/Ctrl+Enter to advance)"
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
            minHeight: "5lh",
            overflow: "auto",
            transition: "border-color 80ms",
            lineHeight: 1.5,
          } as CSSProperties}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--ops-line-bright)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--ops-line)";
          }}
        />
      </OpsField>

      {/* Reveal + rating + next */}
      {problem.solution && !revealed && (
        <OpsButton onClick={() => setRevealed(true)}>SHOW SOLUTION</OpsButton>
      )}

      {revealed && problem.solution && (
        <div
          style={{
            background: "var(--ops-bg-deep)",
            border: "1px solid var(--ops-line)",
            borderRadius: 2,
            padding: "12px 14px",
            fontFamily: "var(--ops-mono)",
            fontSize: 12,
            lineHeight: 1.6,
            color: "var(--ops-fg-mute)",
            animation: "ops-fade-in 200ms ease-out",
          } as CSSProperties}
        >
          {problem.solution}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {rated === null ? (
          <>
            <OpsButton
              onClick={() => void handleRate(true)}
              style={{
                borderColor: "var(--ops-ok)",
                color: "var(--ops-ok)",
              } as CSSProperties}
            >
              I GOT IT
            </OpsButton>
            <OpsButton variant="danger" onClick={() => void handleRate(false)}>
              I MISSED IT
            </OpsButton>
          </>
        ) : (
          <Tag kind={rated ? "ok" : "crit"} solid>
            {rated ? "CORRECT" : "MISSED"}
          </Tag>
        )}
        <OpsButton
          variant="primary"
          onClick={onNext}
          style={{ marginLeft: "auto" } as CSSProperties}
        >
          {isLast ? "FINISH" : `NEXT (${idx + 1}/${total}) →`}
        </OpsButton>
      </div>
    </div>
  );
}

// ─── Exam mode ────────────────────────────────────────────────────────────────

interface ExamModeProps {
  session: ExamSession;
  onExit: () => void;
  course: string;
}

interface RatingMap {
  [idx: number]: boolean;
}

export function ExamMode({ session, onExit, course }: ExamModeProps) {
  const [problemIdx, setProblemIdx] = useState(0);
  const [ratings, setRatings] = useState<RatingMap>({});
  const [done, setDone] = useState(false);
  const [paused, setPaused] = useState(false);
  const [showPauseConfirm, setShowPauseConfirm] = useState(false);
  const pausedSecondsRef = useRef(0);

  const { rateProblem } = useRateProblem();
  const problems = session.problems;
  const current = problems[problemIdx];

  const answeredSet = new Set(Object.keys(ratings).map(Number));

  const handleExpire = useCallback(() => {
    setDone(true);
  }, []);

  const handleRate = useCallback(
    async (correct: boolean) => {
      if (!current) return;
      await rateProblem(current.id, correct);
      setRatings((r) => ({ ...r, [problemIdx]: correct }));
    },
    [current, problemIdx, rateProblem],
  );

  const handleNext = useCallback(() => {
    if (problemIdx < problems.length - 1) {
      setProblemIdx((i) => i + 1);
    } else {
      setDone(true);
    }
  }, [problemIdx, problems.length]);

  // Keyboard: Enter=next, Esc=confirm exit
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA" || tag === "INPUT") return;
      if (e.key === "Enter" && !done) {
        e.preventDefault();
        handleNext();
      } else if (e.key === "ArrowRight" && !done) {
        handleNext();
      } else if (e.key === "Escape") {
        if (window.confirm("Exit exam? Progress will not be saved.")) {
          onExit();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [done, handleNext, onExit]);

  const correct = Object.values(ratings).filter(Boolean).length;

  if (done) {
    return (
      <SummaryView
        correct={correct}
        total={problems.length}
        course={course}
        startedIso={session.started_iso}
        ratings={ratings}
        problems={problems}
        onExit={onExit}
      />
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        gap: 0,
      } as CSSProperties}
    >
      {/* Exam header strip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "10px 16px",
          borderBottom: "1px solid var(--ops-line)",
          background: "var(--ops-bg-elevated)",
          gap: 14,
          flexWrap: "wrap",
        } as CSSProperties}
      >
        <Tag kind="amber">{course}</Tag>

        {/* Progress dots */}
        <ProgressDots
          total={problems.length}
          current={problemIdx}
          answered={answeredSet}
        />

        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-dim)",
            letterSpacing: "0.1em",
          } as CSSProperties}
        >
          {problemIdx + 1} / {problems.length}
        </span>

        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          <ExamTimer
            endsIso={session.ends_iso}
            onExpire={handleExpire}
            paused={paused}
            pausedSecondsRef={pausedSecondsRef}
          />
        </span>

        {/* Pause button */}
        <OpsButton
          onClick={() => {
            if (paused) {
              setShowPauseConfirm(true);
            } else {
              setPaused(true);
            }
          }}
          style={{ fontSize: 10 } as CSSProperties}
        >
          {paused ? "RESUME" : "PAUSE"}
        </OpsButton>

        <OpsButton
          onClick={onExit}
          variant="danger"
          style={{ fontSize: 10 } as CSSProperties}
        >
          EXIT
        </OpsButton>
      </div>

      {/* Pause overlay */}
      {paused && !showPauseConfirm && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 30,
            background: "rgba(7,8,9,0.72)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 16,
          } as CSSProperties}
        >
          <div
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 20,
              letterSpacing: "0.2em",
              color: "var(--ops-fg-dim)",
            } as CSSProperties}
          >
            PAUSED
          </div>
          <OpsButton variant="primary" onClick={() => setPaused(false)}>
            RESUME EXAM
          </OpsButton>
        </div>
      )}

      {/* Resume confirm */}
      {showPauseConfirm && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 40,
            background: "rgba(7,8,9,0.88)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          } as CSSProperties}
        >
          <div
            style={{
              background: "var(--ops-bg-panel)",
              border: "1px solid var(--ops-line-strong)",
              borderRadius: 2,
              padding: 24,
              display: "flex",
              flexDirection: "column",
              gap: 16,
              width: 300,
            } as CSSProperties}
          >
            <div
              style={{
                fontFamily: "var(--ops-mono)",
                fontSize: 12,
                color: "var(--ops-fg)",
              } as CSSProperties}
            >
              Resume exam? Timer will restart from where you paused.
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <OpsButton
                onClick={() => {
                  setShowPauseConfirm(false);
                  setPaused(false);
                }}
                variant="primary"
              >
                RESUME
              </OpsButton>
              <OpsButton onClick={() => setShowPauseConfirm(false)}>
                CANCEL
              </OpsButton>
            </div>
          </div>
        </div>
      )}

      {/* Problem area */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: 16,
          position: "relative",
        } as CSSProperties}
      >
        {current && (
          <ProblemCard
            key={problemIdx}
            problem={current}
            idx={problemIdx}
            total={problems.length}
            onRate={handleRate}
            onNext={handleNext}
            isLast={problemIdx === problems.length - 1}
          />
        )}
      </div>
    </div>
  );
}
