"use client";

/**
 * /scholar — Scholar workspace
 *
 * Three-pane layout:
 *   LEFT  (320px) — Review Queue (spaced-repetition cards due today)
 *   CENTER (1fr)  — Problem Solver / Exam Mode (switchable)
 *   RIGHT (320px) — Weak Topics
 *
 * Course selection + exam launch live in the view-header.
 * LocalStorage persists course and last problem textarea across refresh.
 */

import {
  CSSProperties,
  useCallback,
  useRef,
  useState,
} from "react";
import { OpsButton } from "@/components/ops";
import {
  type ExamSession,
  useDueCards,
  useImportSeed,
  useScholarDocs,
  useStartExam,
  useWeakTopics,
} from "@/hooks/use-scholar";
import { showError, showInfo, showSuccess } from "@/lib/toast";
import { ReviewQueue } from "./ReviewQueue";
import { ProblemSolver } from "./ProblemSolver";
import { ExamMode } from "./ExamMode";
import { WeakTopics } from "./WeakTopics";
import { readLS, writeLS } from "./shared";

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_COURSES = [
  "Linear Algebra",
  "Calculus",
  "Statistics",
  "Discrete Math",
  "Algorithms",
];

const EXAM_DUE_DATE = "Tomorrow · 4:00 PM";
const LS_COURSE = "scholar.course.v1";
const LS_PROBLEM = "scholar.lastproblem.v1";
const LS_EXTRA_COURSES = "scholar.courses.extra.v1";

type CenterMode = "solver" | "exam";

// ─── Session counter ──────────────────────────────────────────────────────────

interface SessionCounterProps {
  cardsReviewed: number;
  problemsSolved: number;
  correct: number;
}

function SessionCounter({ cardsReviewed, problemsSolved, correct }: SessionCounterProps) {
  const accuracy =
    problemsSolved > 0 ? Math.round((correct / problemsSolved) * 100) : null;

  return (
    <div
      style={{
        display: "flex",
        gap: 14,
        alignItems: "center",
      } as CSSProperties}
    >
      {[
        { label: "CARDS", value: String(cardsReviewed) },
        { label: "PROBLEMS", value: String(problemsSolved) },
        { label: "ACCURACY", value: accuracy !== null ? `${accuracy}%` : "—" },
      ].map(({ label, value }) => (
        <div
          key={label}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
          } as CSSProperties}
        >
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 14,
              fontVariantNumeric: "tabular-nums",
              color: "var(--ops-fg)",
              lineHeight: 1,
            } as CSSProperties}
          >
            {value}
          </span>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 8,
              letterSpacing: "0.12em",
              color: "var(--ops-fg-faint)",
              textTransform: "uppercase",
              lineHeight: 1.4,
            } as CSSProperties}
          >
            {label}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── Exam config dialog ───────────────────────────────────────────────────────

interface ExamConfigDialogProps {
  course: string;
  onConfirm: (durationMin: number, problemCount: number) => void;
  onCancel: () => void;
  loading: boolean;
}

function ExamConfigDialog({
  course,
  onConfirm,
  onCancel,
  loading,
}: ExamConfigDialogProps) {
  const [duration, setDuration] = useState("60");
  const [count, setCount] = useState("10");

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 40,
        background: "rgba(7,8,9,0.88)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backdropFilter: "blur(2px)",
      } as CSSProperties}
    >
      <div
        style={{
          background: "var(--ops-bg-panel)",
          border: "1px solid var(--ops-line-strong)",
          borderRadius: 2,
          width: 340,
          padding: 24,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        } as CSSProperties}
      >
        <div
          style={{
            fontFamily: "var(--ops-sans)",
            fontSize: 13,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--ops-fg)",
          } as CSSProperties}
        >
          EXAM SESSION
        </div>

        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg-dim)",
          } as CSSProperties}
        >
          {course} · {EXAM_DUE_DATE}
        </div>

        <label
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--ops-fg-dim)",
          } as CSSProperties}
        >
          DURATION (MIN)
          <input
            type="number"
            min={5}
            max={180}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            style={{
              background: "var(--ops-bg-input)",
              border: "1px solid var(--ops-line)",
              color: "var(--ops-fg)",
              fontFamily: "var(--ops-mono)",
              fontSize: 12,
              padding: "5px 8px",
              borderRadius: 2,
              width: "100%",
              outline: "none",
            } as CSSProperties}
          />
        </label>

        <label
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--ops-fg-dim)",
          } as CSSProperties}
        >
          PROBLEM COUNT
          <input
            type="number"
            min={1}
            max={50}
            value={count}
            onChange={(e) => setCount(e.target.value)}
            style={{
              background: "var(--ops-bg-input)",
              border: "1px solid var(--ops-line)",
              color: "var(--ops-fg)",
              fontFamily: "var(--ops-mono)",
              fontSize: 12,
              padding: "5px 8px",
              borderRadius: 2,
              width: "100%",
              outline: "none",
            } as CSSProperties}
          />
        </label>

        <div
          style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}
        >
          <OpsButton onClick={onCancel} disabled={loading}>
            CANCEL
          </OpsButton>
          <OpsButton
            variant="primary"
            disabled={loading}
            onClick={() =>
              onConfirm(Number(duration) || 60, Number(count) || 10)
            }
          >
            {loading ? "STARTING…" : "START EXAM"}
          </OpsButton>
        </div>
      </div>
    </div>
  );
}

// ─── View header ──────────────────────────────────────────────────────────────

interface ViewHeaderProps {
  course: string;
  courses: string[];
  onCourseChange: (c: string) => void;
  onStartExam: () => void;
  showImportSeed: boolean;
  onImportSeed: () => void;
  importing: boolean;
  sessionCounter: { cardsReviewed: number; problemsSolved: number; correct: number };
}

function ViewHeader({
  course,
  courses,
  onCourseChange,
  onStartExam,
  showImportSeed,
  onImportSeed,
  importing,
  sessionCounter,
}: ViewHeaderProps) {
  const handleCourseSelect = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const val = e.target.value;
      if (val === "__add__") {
        const name = window.prompt("New course name:");
        if (name?.trim()) onCourseChange(name.trim());
      } else {
        onCourseChange(val);
      }
    },
    [onCourseChange],
  );

  return (
    <div className="ops-view-header">
      <div>
        <div className="ops-view-title">SCHOLAR · STUDY</div>
        <div className="ops-view-subtitle">
          {course} · {EXAM_DUE_DATE}
        </div>
      </div>

      <div className="ops-view-actions">
        {/* Session counter */}
        <SessionCounter {...sessionCounter} />

        {/* Course selector */}
        <select
          value={course}
          onChange={handleCourseSelect}
          style={{
            background: "var(--ops-bg-input)",
            border: "1px solid var(--ops-line-strong)",
            color: "var(--ops-fg-mute)",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            padding: "5px 8px",
            borderRadius: 2,
            letterSpacing: "0.04em",
            outline: "none",
            cursor: "pointer",
          } as CSSProperties}
        >
          {courses.map((c) => (
            <option key={c} value={c}>
              {c.toUpperCase()}
            </option>
          ))}
          <option value="__add__">+ ADD COURSE…</option>
        </select>

        <OpsButton variant="primary" onClick={onStartExam}>
          START EXAM
        </OpsButton>

        {showImportSeed && (
          <OpsButton onClick={onImportSeed} disabled={importing}>
            {importing ? "IMPORTING…" : "IMPORT LINALG SEED"}
          </OpsButton>
        )}
      </div>
    </div>
  );
}

// ─── Center panel mode tab strip ─────────────────────────────────────────────

interface ModeTabs {
  current: CenterMode;
  onSolver: () => void;
  onExam: () => void;
}

function ModeTabStrip({ current, onSolver, onExam }: ModeTabs) {
  const tabStyle = (active: boolean): CSSProperties => ({
    fontFamily: "var(--ops-mono)",
    fontSize: 10,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
    padding: "8px 16px",
    background: active ? "var(--ops-bg-elevated)" : "transparent",
    color: active ? "var(--ops-fg)" : "var(--ops-fg-dim)",
    borderBottom: active
      ? "1px solid var(--ops-amber)"
      : "1px solid transparent",
    borderRight: "1px solid var(--ops-line)",
    cursor: "pointer",
    transition: "background 80ms, color 80ms",
  });

  return (
    <div
      style={{
        display: "flex",
        borderBottom: "1px solid var(--ops-line)",
        background: "var(--ops-bg-deep)",
      } as CSSProperties}
    >
      <button style={tabStyle(current === "solver")} onClick={onSolver}>
        PROBLEM SOLVER
      </button>
      <button style={tabStyle(current === "exam")} onClick={onExam}>
        EXAM MODE
      </button>
    </div>
  );
}

// ─── Page root ────────────────────────────────────────────────────────────────

export default function ScholarPage() {
  // Course — persisted to localStorage
  const [extraCourses, setExtraCourses] = useState<string[]>(
    () => {
      const stored = readLS(LS_EXTRA_COURSES);
      if (!stored) return [];
      try {
        return JSON.parse(stored) as string[];
      } catch {
        return [];
      }
    },
  );
  const allCourses = [...DEFAULT_COURSES, ...extraCourses.filter((c) => !DEFAULT_COURSES.includes(c))];

  const [course, setCourse] = useState<string>(
    () => readLS(LS_COURSE) || "Linear Algebra",
  );
  const handleCourseChange = useCallback((c: string) => {
    setCourse(c);
    writeLS(LS_COURSE, c);
    // Add to extra courses if not in defaults
    if (!DEFAULT_COURSES.includes(c)) {
      setExtraCourses((prev) => {
        const next = prev.includes(c) ? prev : [...prev, c];
        writeLS(LS_EXTRA_COURSES, JSON.stringify(next));
        return next;
      });
    }
  }, []);

  // Center pane state
  const [centerMode, setCenterMode] = useState<CenterMode>("solver");
  const [showExamConfig, setShowExamConfig] = useState(false);
  const [examSession, setExamSession] = useState<ExamSession | null>(null);

  // Practice problem injected from weak topics
  const [practiceProblem, setPracticeProblem] = useState<string>("");
  const practiceKeyRef = useRef(0);

  // Session counter
  const [sessionCardsReviewed, setSessionCardsReviewed] = useState(0);
  const [sessionProblemsSolved, setSessionProblemsSolved] = useState(0);
  const [sessionCorrect, setSessionCorrect] = useState(0);

  // API data
  const {
    data: dueCards,
    loading: dueLoading,
    error: dueError,
    refetch: dueRefetch,
  } = useDueCards();

  const {
    data: weakData,
    loading: weakLoading,
    error: weakError,
    refetch: weakRefetch,
  } = useWeakTopics(8);

  const { data: docs } = useScholarDocs();

  const { mutate: importSeed, loading: importing } = useImportSeed();
  const { startExam, loading: examStarting } = useStartExam();

  const cards = dueCards ?? [];
  const weakTopics = weakData?.weak_topics ?? [];
  const hasAnyDocs = (docs?.length ?? 0) > 0;
  const showImportSeed = !hasAnyDocs && cards.length === 0;

  const handleImportSeed = useCallback(async () => {
    const result = await importSeed("linalg");
    if (result) {
      showSuccess(`IMPORTED ${result.cards_imported} CARDS`);
      dueRefetch();
    } else {
      showError("SEED IMPORT FAILED — check API");
    }
  }, [importSeed, dueRefetch]);

  const handleStartExam = useCallback(() => {
    setShowExamConfig(true);
  }, []);

  const handleExamConfirm = useCallback(
    async (durationMin: number, problemCount: number) => {
      const session = await startExam(course, durationMin, problemCount);
      if (session) {
        setShowExamConfig(false);
        setExamSession(session);
        setCenterMode("exam");
        showInfo(`EXAM STARTED · ${problemCount} PROBLEMS · ${durationMin}MIN`);
      } else {
        showError("EXAM START FAILED — ANTHROPIC_API_KEY may not be set");
      }
    },
    [course, startExam],
  );

  const handleExitExam = useCallback(() => {
    setExamSession(null);
    setCenterMode("solver");
  }, []);

  const handlePractice = useCallback((concept: string) => {
    const prompt = `Practice problem on ${concept}`;
    writeLS(LS_PROBLEM, prompt);
    setPracticeProblem(prompt);
    practiceKeyRef.current += 1;
    setCenterMode("solver");
    showInfo(`PRACTICE: ${concept.toUpperCase()}`);
  }, []);

  // Seed initial problem from localStorage on mount
  const [initialProblem] = useState<string>(() => readLS(LS_PROBLEM));

  // Determine which problem to pass to solver (injected > initial)
  const activeProblem = practiceProblem || initialProblem;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      } as CSSProperties}
    >
      <ViewHeader
        course={course}
        courses={allCourses}
        onCourseChange={handleCourseChange}
        onStartExam={handleStartExam}
        showImportSeed={showImportSeed}
        onImportSeed={handleImportSeed}
        importing={importing}
        sessionCounter={{
          cardsReviewed: sessionCardsReviewed,
          problemsSolved: sessionProblemsSolved,
          correct: sessionCorrect,
        }}
      />

      <div
        className="ops-view-body"
        style={{
          display: "grid",
          gridTemplateColumns: "320px 1fr 320px",
          gridTemplateRows: "100%",
          gap: 0,
          overflow: "hidden",
        } as CSSProperties}
      >
        {/* LEFT — Review Queue */}
        <div
          style={{
            borderRight: "1px solid var(--ops-line)",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          } as CSSProperties}
        >
          <ReviewQueue
            cards={cards}
            loading={dueLoading}
            error={dueError}
            onRefetch={dueRefetch}
            hasAnyDocs={hasAnyDocs}
            onImportSeed={handleImportSeed}
            importing={importing}
            onCardRated={() => setSessionCardsReviewed((n) => n + 1)}
          />
        </div>

        {/* CENTER — Problem Solver / Exam Mode */}
        <div
          style={{
            borderRight: "1px solid var(--ops-line)",
            position: "relative",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          } as CSSProperties}
        >
          {centerMode === "solver" && (
            <ModeTabStrip
              current={centerMode}
              onSolver={() => setCenterMode("solver")}
              onExam={handleStartExam}
            />
          )}

          <div
            style={{
              flex: 1,
              overflow: "hidden",
              position: "relative",
            } as CSSProperties}
          >
            {centerMode === "solver" && (
              <ProblemSolver
                key={practiceKeyRef.current}
                course={course}
                initialProblem={activeProblem}
                onSolved={() => setSessionProblemsSolved((n) => n + 1)}
                onRated={(correct) => {
                  if (correct) setSessionCorrect((n) => n + 1);
                }}
              />
            )}

            {centerMode === "exam" && examSession && (
              <ExamMode
                session={examSession}
                onExit={handleExitExam}
                course={course}
              />
            )}
          </div>

          {/* Exam config overlay */}
          {showExamConfig && (
            <ExamConfigDialog
              course={course}
              onConfirm={(d, c) => void handleExamConfirm(d, c)}
              onCancel={() => setShowExamConfig(false)}
              loading={examStarting}
            />
          )}
        </div>

        {/* RIGHT — Weak Topics */}
        <div
          style={{
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          } as CSSProperties}
        >
          <WeakTopics
            topics={weakTopics}
            loading={weakLoading}
            error={weakError}
            onRefetch={weakRefetch}
            onPractice={handlePractice}
          />
        </div>
      </div>
    </div>
  );
}
