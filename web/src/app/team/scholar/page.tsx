"use client";

import { CSSProperties, useState, useEffect, useRef, useCallback } from "react";
import {
  Panel,
  AgentGlyph,
  Bars,
  Hatch,
  KV,
  OpsButton,
  SubH,
  Tag,
  Dot,
  getAgentIdentity,
} from "@/components/ops";
import { useTasks, useActivityLog, useAgents } from "@/hooks/use-data";
import { useActiveRunsContext as useActiveRuns } from "@/providers/active-runs-provider";
import { useFastTaskPoll } from "@/hooks/use-fast-task-poll";
import { TaskDetailPanel } from "@/components/task-detail-panel";
import { useGoals, useProjects } from "@/hooks/use-data";
import type { Task } from "@/lib/types";
import type { TaskFormData } from "@/components/task-form";
import {
  useDocuments,
  useSummary,
  useFlashcards,
  useRateCard,
  useGenerateFlashcards,
  useUploadDocument,
  type ScholarDocument,
  type Flashcard,
  type Rating,
} from "@/hooks/use-scholar-study";

// ─── Tabs ─────────────────────────────────────────────────────────────────────

const TABS = [
  { id: "workspace", label: "WORKSPACE" },
  { id: "study", label: "STUDY" },
  { id: "config", label: "CONFIG" },
  { id: "logs", label: "LOGS" },
] as const;
type TabId = (typeof TABS)[number]["id"];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ScholarPage() {
  const identity = getAgentIdentity("scholar")!;

  const { tasks, loading, update: updateTask, remove: deleteTask, refetch } = useTasks();
  const { goals } = useGoals();
  const { projects } = useProjects();
  const { agents } = useAgents();
  const { events } = useActivityLog();
  const { runningTaskIds } = useActiveRuns();
  useFastTaskPoll(runningTaskIds.size > 0, refetch);

  const [tab, setTab] = useState<TabId>("study");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  const agentTasks = tasks.filter((t) => t.assignedTo === identity.id);
  const inProgress = agentTasks.filter((t) => t.kanban === "in-progress");
  const todo = agentTasks.filter((t) => t.kanban === "not-started");
  const completed = agentTasks.filter((t) => t.kanban === "done");
  const agentEvents = events.filter((e) => e.actor === identity.id).slice(0, 20);
  const agentDef = agents.find((a) => a.id === identity.id);

  const handleUpdateTask = async (data: TaskFormData) => {
    if (!selectedTask) return;
    await updateTask(selectedTask.id, {
      ...data,
      tags: data.tags.split(",").map((t) => t.trim()).filter(Boolean),
      acceptanceCriteria: data.acceptanceCriteria
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    });
    setSelectedTask(null);
  };

  const handleDeleteTask = async () => {
    if (!selectedTask) return;
    await deleteTask(selectedTask.id);
    setSelectedTask(null);
  };

  const bars = useRef(Array.from({ length: 36 }, () => 5 + Math.random() * 32)).current;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 } as CSSProperties}>
      {/* ── Header strip ─────────────────────────────────────────── */}
      <div
        style={{
          background: "var(--ops-bg-deep)",
          borderBottom: "1px solid var(--ops-line)",
          padding: "12px 18px 12px 21px",
          display: "grid",
          gridTemplateColumns: "auto 1fr auto auto auto auto",
          gap: 20,
          alignItems: "center",
          position: "relative",
        } as CSSProperties}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            height: "100%",
            width: 3,
            background: identity.colorHex,
            boxShadow: `0 0 12px ${identity.colorHex}55`,
          } as CSSProperties}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 12 } as CSSProperties}>
          <AgentGlyph agent={identity} size={42} />
          <div>
            <div
              style={{
                fontFamily: "var(--ops-sans)",
                fontSize: 20,
                fontWeight: 500,
                letterSpacing: "0.06em",
                color: identity.colorHex,
              } as CSSProperties}
            >
              {identity.name}
            </div>
            <div
              style={{
                fontSize: 9,
                letterSpacing: "0.2em",
                color: "var(--ops-fg-dim)",
                fontFamily: "var(--ops-mono)",
              } as CSSProperties}
            >
              {identity.role} · {identity.tagline}
            </div>
          </div>
        </div>
        <div style={{ width: 180 } as CSSProperties}>
          <Bars values={bars} color={identity.colorHex} height={28} />
          <div
            style={{
              fontSize: 8,
              color: "var(--ops-fg-faint)",
              letterSpacing: "0.1em",
              marginTop: 2,
              fontFamily: "var(--ops-mono)",
            } as CSSProperties}
          >
            ACTIVITY · LAST 36s
          </div>
        </div>
        <HeaderStat label="ACTIVE" value={String(inProgress.length)} />
        <HeaderStat label="QUEUE" value={String(todo.length)} />
        <HeaderStat label="DONE" value={String(completed.length)} accent="var(--ops-ok)" />
        <div style={{ display: "flex", gap: 6 } as CSSProperties}>
          <OpsButton variant="primary">▶ START</OpsButton>
          <OpsButton variant="danger">◼ PAUSE</OpsButton>
        </div>
      </div>

      {/* ── Tab bar ──────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--ops-line)",
          background: "var(--ops-bg-deep)",
          padding: "0 18px",
          gap: 0,
        } as CSSProperties}
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              background: "transparent",
              border: "none",
              padding: "9px 14px",
              fontSize: 10,
              letterSpacing: "0.16em",
              color: tab === t.id ? identity.colorHex : "var(--ops-fg-dim)",
              borderBottom: `2px solid ${tab === t.id ? identity.colorHex : "transparent"}`,
              fontFamily: "var(--ops-mono)",
              cursor: "pointer",
              marginBottom: -1,
            } as CSSProperties}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Tab content ──────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: "auto", minHeight: 0 } as CSSProperties}>
        {tab === "workspace" && (
          <WorkspaceTab
            identity={identity}
            inProgress={inProgress}
            todo={todo}
            completed={completed}
            loading={loading}
            onTaskClick={setSelectedTask}
          />
        )}
        {tab === "study" && <StudyTab accentColor={identity.colorHex} />}
        {tab === "config" && <ConfigTab identity={identity} agentDef={agentDef} />}
        {tab === "logs" && <LogsTab identity={identity} events={agentEvents} />}
      </div>

      {selectedTask && (
        <TaskDetailPanel
          task={selectedTask}
          projects={projects}
          goals={goals}
          allTasks={tasks}
          onUpdate={handleUpdateTask}
          onDelete={handleDeleteTask}
          onClose={() => setSelectedTask(null)}
        />
      )}
    </div>
  );
}

// ─── Header stat ──────────────────────────────────────────────────────────────

function HeaderStat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: 8,
          letterSpacing: "0.16em",
          color: "var(--ops-fg-dim)",
          fontFamily: "var(--ops-mono)",
          marginBottom: 2,
        } as CSSProperties}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 18,
          fontFamily: "var(--ops-mono)",
          fontVariantNumeric: "tabular-nums",
          color: accent ?? "var(--ops-fg)",
        } as CSSProperties}
      >
        {value}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// STUDY TAB
// ═══════════════════════════════════════════════════════════════════════════════

type StudyView =
  | { kind: "library" }
  | { kind: "document"; docId: string }
  | { kind: "drill"; docId: string; cards: Flashcard[] };

function StudyTab({ accentColor }: { accentColor: string }) {
  const [view, setView] = useState<StudyView>({ kind: "library" });

  const goToLibrary = useCallback(() => setView({ kind: "library" }), []);
  const goToDocument = useCallback((docId: string) => setView({ kind: "document", docId }), []);
  const startDrill = useCallback(
    (docId: string, cards: Flashcard[]) => setView({ kind: "drill", docId, cards }),
    [],
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" } as CSSProperties}>
      {view.kind === "library" && (
        <LibraryView accentColor={accentColor} onOpenDoc={goToDocument} />
      )}
      {view.kind === "document" && (
        <DocumentView
          docId={view.docId}
          accentColor={accentColor}
          onBack={goToLibrary}
          onStartDrill={startDrill}
        />
      )}
      {view.kind === "drill" && (
        <DrillView
          cards={view.cards}
          accentColor={accentColor}
          onBack={() => setView({ kind: "document", docId: view.docId })}
        />
      )}
    </div>
  );
}

// ─── View A: Library ──────────────────────────────────────────────────────────

function LibraryView({
  accentColor,
  onOpenDoc,
}: {
  accentColor: string;
  onOpenDoc: (id: string) => void;
}) {
  const { data: docs, loading, error, refetch } = useDocuments();
  const [showUpload, setShowUpload] = useState(false);

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 } as CSSProperties}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" } as CSSProperties}>
        <SubH>STUDY LIBRARY</SubH>
        <OpsButton variant="primary" onClick={() => setShowUpload(true)}>
          + UPLOAD
        </OpsButton>
      </div>

      {/* Upload modal */}
      {showUpload && (
        <UploadModal
          accentColor={accentColor}
          onClose={() => setShowUpload(false)}
          onUploaded={() => { setShowUpload(false); refetch(); }}
        />
      )}

      {/* Content */}
      {loading && <MonoText>LOADING...</MonoText>}
      {error && <MonoText style={{ color: "var(--ops-crit)" }}>ERROR: {error}</MonoText>}
      {!loading && !error && (!docs || docs.length === 0) && (
        <Hatch label="NO DOCUMENTS · UPLOAD A PDF OR NOTE" height={140} />
      )}
      {!loading && !error && docs && docs.length > 0 && (
        <Panel title={`DOCUMENTS · ${docs.length}`} flushBody>
          <table style={{ width: "100%", borderCollapse: "collapse" } as CSSProperties}>
            <thead>
              <tr>
                {["FILENAME", "PAGES", "CARDS", "DUE", "ADDED"].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "5px 12px",
                      fontSize: 8,
                      letterSpacing: "0.14em",
                      color: "var(--ops-fg-faint)",
                      fontFamily: "var(--ops-mono)",
                      borderBottom: "1px solid var(--ops-line)",
                    } as CSSProperties}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  doc={doc}
                  accentColor={accentColor}
                  onClick={() => onOpenDoc(doc.id)}
                />
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}

function DocumentRow({
  doc,
  accentColor,
  onClick,
}: {
  doc: ScholarDocument;
  accentColor: string;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const dueColor = doc.due_count > 0 ? "var(--ops-amber)" : "var(--ops-fg-faint)";

  return (
    <tr
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        cursor: "pointer",
        background: hovered ? "var(--ops-bg-hover)" : "transparent",
        transition: "background 120ms",
      } as CSSProperties}
    >
      <td
        style={{
          padding: "7px 12px",
          fontSize: 11,
          fontFamily: "var(--ops-sans)",
          color: hovered ? accentColor : "var(--ops-fg)",
          borderLeft: hovered ? `2px solid ${accentColor}` : "2px solid transparent",
          transition: "color 120ms, border-color 120ms",
        } as CSSProperties}
      >
        {doc.filename}
      </td>
      <td style={cellStyle}>{doc.page_count}</td>
      <td style={cellStyle}>{doc.flashcard_count}</td>
      <td style={{ ...cellStyle, color: dueColor } as CSSProperties}>{doc.due_count}</td>
      <td style={cellStyle}>
        {new Date(doc.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}
      </td>
    </tr>
  );
}

const cellStyle: CSSProperties = {
  padding: "7px 12px",
  fontSize: 10,
  fontFamily: "var(--ops-mono)",
  color: "var(--ops-fg-dim)",
};

// ─── Upload modal ─────────────────────────────────────────────────────────────

function UploadModal({
  accentColor,
  onClose,
  onUploaded,
}: {
  accentColor: string;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const { upload, loading, error, progress } = useUploadDocument();
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      const result = await upload(file);
      if (result) onUploaded();
    },
    [upload, onUploaded],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const ACCEPT = ".pdf,.txt,.md";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(7,8,9,0.82)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      } as CSSProperties}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: "var(--ops-bg-panel)",
          border: "1px solid var(--ops-line-strong)",
          width: 440,
          padding: 24,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        } as CSSProperties}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" } as CSSProperties}>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 11,
              letterSpacing: "0.14em",
              color: accentColor,
            } as CSSProperties}
          >
            UPLOAD DOCUMENT
          </span>
          <OpsButton onClick={onClose} style={{ fontSize: 14, padding: "2px 8px" }}>×</OpsButton>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          style={{
            border: `1px dashed ${dragging ? accentColor : "var(--ops-line-strong)"}`,
            background: dragging ? `${accentColor}0a` : "var(--ops-bg-elevated)",
            padding: "32px 24px",
            textAlign: "center",
            cursor: "pointer",
            transition: "border-color 150ms, background 150ms",
          } as CSSProperties}
        >
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
          <div
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 10,
              color: dragging ? accentColor : "var(--ops-fg-dim)",
              letterSpacing: "0.12em",
              lineHeight: 1.8,
            } as CSSProperties}
          >
            {loading
              ? `UPLOADING... ${progress}%`
              : "DROP FILE HERE OR CLICK TO BROWSE"}
            <br />
            <span style={{ color: "var(--ops-fg-faint)", fontSize: 9 } as CSSProperties}>
              PDF · TXT · MD
            </span>
          </div>
        </div>

        {/* Progress bar */}
        {loading && (
          <div style={{ background: "var(--ops-bg-elevated)", height: 3 } as CSSProperties}>
            <div
              style={{
                height: "100%",
                width: `${progress}%`,
                background: accentColor,
                transition: "width 200ms",
              } as CSSProperties}
            />
          </div>
        )}

        {error && (
          <MonoText style={{ color: "var(--ops-crit)", fontSize: 9 }}>ERROR: {error}</MonoText>
        )}
      </div>
    </div>
  );
}

// ─── View B: Document detail ──────────────────────────────────────────────────

function DocumentView({
  docId,
  accentColor,
  onBack,
  onStartDrill,
}: {
  docId: string;
  accentColor: string;
  onBack: () => void;
  onStartDrill: (docId: string, cards: Flashcard[]) => void;
}) {
  const { data: summary, loading: sumLoading, refetch: refetchSummary } = useSummary(docId);
  const { data: cards, loading: cardsLoading, refetch: refetchCards } = useFlashcards(docId);
  const { generate, loading: generating } = useGenerateFlashcards(docId);

  const handleGenerate = useCallback(async () => {
    await generate();
    refetchCards();
  }, [generate, refetchCards]);

  const docFilename = docId;

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 } as CSSProperties}>
      {/* Back link */}
      <button
        onClick={onBack}
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: "pointer",
          fontFamily: "var(--ops-mono)",
          fontSize: 9,
          letterSpacing: "0.14em",
          color: "var(--ops-fg-dim)",
          display: "flex",
          alignItems: "center",
          gap: 6,
          alignSelf: "flex-start",
        } as CSSProperties}
      >
        ← LIBRARY
      </button>

      <SubH>{docFilename}</SubH>

      {/* Two-column layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 14,
          alignItems: "start",
        } as CSSProperties}
      >
        {/* Summary panel */}
        <Panel
          title="SUMMARY"
          trailing={
            <OpsButton
              onClick={() => refetchSummary()}
              style={{ fontSize: 8, padding: "2px 8px", letterSpacing: "0.1em" }}
            >
              REGENERATE
            </OpsButton>
          }
        >
          {sumLoading && <MonoText>LOADING SUMMARY...</MonoText>}
          {!sumLoading && !summary && (
            <MonoText style={{ color: "var(--ops-fg-faint)" }}>NO SUMMARY · GENERATE BELOW</MonoText>
          )}
          {summary && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 } as CSSProperties}>
              <KV label="TLDR">{summary.tldr}</KV>
              {summary.key_concepts.length > 0 && (
                <div>
                  <MonoLabel>KEY CONCEPTS</MonoLabel>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 } as CSSProperties}>
                    {summary.key_concepts.map((c) => (
                      <Tag key={c}>{c}</Tag>
                    ))}
                  </div>
                </div>
              )}
              {summary.important_points.length > 0 && (
                <div>
                  <MonoLabel>IMPORTANT POINTS</MonoLabel>
                  <ul
                    style={{
                      margin: "6px 0 0",
                      paddingLeft: 16,
                      display: "flex",
                      flexDirection: "column",
                      gap: 4,
                    } as CSSProperties}
                  >
                    {summary.important_points.map((p, i) => (
                      <li
                        key={i}
                        style={{
                          fontSize: 11,
                          fontFamily: "var(--ops-sans)",
                          color: "var(--ops-fg-mute)",
                          lineHeight: 1.5,
                        } as CSSProperties}
                      >
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </Panel>

        {/* Flashcards panel */}
        <Panel
          title={`FLASHCARDS · ${cards?.length ?? 0}`}
          trailing={
            <div style={{ display: "flex", gap: 6 } as CSSProperties}>
              <OpsButton
                onClick={handleGenerate}
                disabled={generating}
                style={{ fontSize: 8, padding: "2px 8px", letterSpacing: "0.1em" }}
              >
                {generating ? "GENERATING..." : "GENERATE CARDS"}
              </OpsButton>
              {cards && cards.length > 0 && (
                <OpsButton
                  variant="primary"
                  onClick={() => onStartDrill(docId, cards)}
                  style={{ fontSize: 8, padding: "2px 8px", letterSpacing: "0.1em" }}
                >
                  START DRILL
                </OpsButton>
              )}
            </div>
          }
          flushBody
        >
          {cardsLoading && <div style={{ padding: 12 }}><MonoText>LOADING CARDS...</MonoText></div>}
          {!cardsLoading && (!cards || cards.length === 0) && (
            <div style={{ padding: 12 }}>
              <MonoText style={{ color: "var(--ops-fg-faint)" }}>
                NO CARDS · CLICK GENERATE CARDS
              </MonoText>
            </div>
          )}
          {cards && cards.length > 0 && (
            <div style={{ maxHeight: 360, overflowY: "auto" } as CSSProperties}>
              {cards.map((card) => (
                <CardRow key={card.id} card={card} accentColor={accentColor} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function CardRow({ card, accentColor }: { card: Flashcard; accentColor: string }) {
  const isDue = card.due_at ? new Date(card.due_at) <= new Date() : false;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "7px 12px",
        borderBottom: "1px solid var(--ops-line-faint)",
        gap: 8,
      } as CSSProperties}
    >
      <span
        style={{
          fontSize: 11,
          fontFamily: "var(--ops-sans)",
          color: "var(--ops-fg-mute)",
          flex: 1,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        } as CSSProperties}
      >
        {card.front}
      </span>
      {isDue && (
        <span
          style={{
            fontSize: 8,
            fontFamily: "var(--ops-mono)",
            letterSpacing: "0.1em",
            color: accentColor,
            background: `${accentColor}18`,
            padding: "2px 6px",
            flexShrink: 0,
          } as CSSProperties}
        >
          DUE
        </span>
      )}
    </div>
  );
}

// ─── View C: Drill mode ───────────────────────────────────────────────────────

function DrillView({
  cards,
  accentColor,
  onBack,
}: {
  cards: Flashcard[];
  accentColor: string;
  onBack: () => void;
}) {
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [done, setDone] = useState(false);
  const [reviewed, setReviewed] = useState(0);
  const { rate } = useRateCard();

  const current = cards[index];
  const total = cards.length;

  const flip = useCallback(() => setFlipped((f) => !f), []);

  const handleRate = useCallback(
    async (rating: Rating) => {
      if (!current) return;
      await rate(current.id, rating);
      setReviewed((n) => n + 1);
      if (index + 1 >= total) {
        setDone(true);
      } else {
        setIndex((i) => i + 1);
        setFlipped(false);
      }
    },
    [current, rate, index, total],
  );

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === " ") { e.preventDefault(); flip(); }
      if (flipped) {
        if (e.key === "1") handleRate("again");
        if (e.key === "2") handleRate("hard");
        if (e.key === "3") handleRate("good");
        if (e.key === "4") handleRate("easy");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [flip, flipped, handleRate]);

  if (done) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 20,
          padding: 32,
        } as CSSProperties}
      >
        <div
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 13,
            letterSpacing: "0.16em",
            color: "var(--ops-ok)",
          } as CSSProperties}
        >
          SESSION COMPLETE · {reviewed} CARDS REVIEWED
        </div>
        <OpsButton onClick={onBack}>← DOCUMENT</OpsButton>
      </div>
    );
  }

  if (!current) return null;
  const progress = ((index) / total) * 100;

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "20px 16px",
        gap: 20,
      } as CSSProperties}
    >
      {/* Back + progress */}
      <div style={{ width: "100%", maxWidth: 640 } as CSSProperties}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 } as CSSProperties}>
          <button
            onClick={onBack}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontFamily: "var(--ops-mono)",
              fontSize: 9,
              letterSpacing: "0.14em",
              color: "var(--ops-fg-dim)",
              padding: 0,
            } as CSSProperties}
          >
            ← DOCUMENT
          </button>
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 9,
              letterSpacing: "0.12em",
              color: "var(--ops-fg-dim)",
            } as CSSProperties}
          >
            {index + 1} OF {total}
          </span>
        </div>
        {/* Progress bar */}
        <div style={{ height: 2, background: "var(--ops-line)", borderRadius: 1 } as CSSProperties}>
          <div
            style={{
              height: "100%",
              width: `${progress}%`,
              background: accentColor,
              borderRadius: 1,
              transition: "width 300ms ease",
            } as CSSProperties}
          />
        </div>
      </div>

      {/* Card surface */}
      <div
        style={{
          width: "100%",
          maxWidth: 640,
          perspective: "1000px",
          flexShrink: 0,
        } as CSSProperties}
      >
        <div
          onClick={flip}
          style={{
            position: "relative",
            height: 260,
            transformStyle: "preserve-3d",
            transition: "transform 400ms ease",
            transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
            cursor: "pointer",
          } as CSSProperties}
        >
          {/* Front */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              backfaceVisibility: "hidden",
              WebkitBackfaceVisibility: "hidden",
              background: "var(--ops-bg-elevated)",
              border: `1px solid ${accentColor}44`,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: 32,
              gap: 16,
            } as CSSProperties}
          >
            <span
              style={{
                fontSize: 8,
                fontFamily: "var(--ops-mono)",
                letterSpacing: "0.2em",
                color: accentColor,
              } as CSSProperties}
            >
              QUESTION
            </span>
            <p
              style={{
                fontSize: 16,
                fontFamily: "var(--ops-sans)",
                color: "var(--ops-fg)",
                textAlign: "center",
                lineHeight: 1.5,
                margin: 0,
              } as CSSProperties}
            >
              {current.front}
            </p>
            <span
              style={{
                fontSize: 8,
                fontFamily: "var(--ops-mono)",
                color: "var(--ops-fg-faint)",
                letterSpacing: "0.12em",
                marginTop: 8,
              } as CSSProperties}
            >
              PRESS SPACE OR CLICK TO FLIP
            </span>
          </div>

          {/* Back */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              backfaceVisibility: "hidden",
              WebkitBackfaceVisibility: "hidden",
              transform: "rotateY(180deg)",
              background: "var(--ops-bg-elevated)",
              border: `1px solid ${accentColor}88`,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: 32,
              gap: 16,
            } as CSSProperties}
          >
            <span
              style={{
                fontSize: 8,
                fontFamily: "var(--ops-mono)",
                letterSpacing: "0.2em",
                color: accentColor,
              } as CSSProperties}
            >
              ANSWER
            </span>
            <p
              style={{
                fontSize: 15,
                fontFamily: "var(--ops-sans)",
                color: "var(--ops-fg)",
                textAlign: "center",
                lineHeight: 1.6,
                margin: 0,
              } as CSSProperties}
            >
              {current.back}
            </p>
          </div>
        </div>
      </div>

      {/* Rating buttons — only shown after flip */}
      <div
        style={{
          width: "100%",
          maxWidth: 640,
          display: "flex",
          gap: 8,
          opacity: flipped ? 1 : 0,
          pointerEvents: flipped ? "auto" : "none",
          transition: "opacity 200ms",
        } as CSSProperties}
      >
        {RATINGS.map(({ label, rating, color, key }) => (
          <button
            key={rating}
            onClick={() => handleRate(rating)}
            style={{
              flex: 1,
              padding: "10px 0",
              background: "transparent",
              border: `1px solid ${color}`,
              cursor: "pointer",
              fontFamily: "var(--ops-mono)",
              fontSize: 9,
              letterSpacing: "0.14em",
              color,
              transition: "background 120ms",
            } as CSSProperties}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = `${color}18`;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
            }}
          >
            {label}
            <span
              style={{
                display: "block",
                fontSize: 7,
                marginTop: 2,
                color: `${color}99`,
              } as CSSProperties}
            >
              [{key}]
            </span>
          </button>
        ))}
      </div>

      <div
        style={{
          fontSize: 8,
          fontFamily: "var(--ops-mono)",
          color: "var(--ops-fg-faint)",
          letterSpacing: "0.1em",
          textAlign: "center",
        } as CSSProperties}
      >
        SPACE · FLIP &nbsp;&nbsp; 1 · AGAIN &nbsp;&nbsp; 2 · HARD &nbsp;&nbsp; 3 · GOOD &nbsp;&nbsp; 4 · EASY
      </div>
    </div>
  );
}

const RATINGS: { label: string; rating: Rating; color: string; key: string }[] = [
  { label: "AGAIN", rating: "again", color: "var(--ops-crit)", key: "1" },
  { label: "HARD", rating: "hard", color: "var(--ops-amber)", key: "2" },
  { label: "GOOD", rating: "good", color: "var(--ops-ok)", key: "3" },
  { label: "EASY", rating: "easy", color: "#6FCF7F99", key: "4" },
];

// ═══════════════════════════════════════════════════════════════════════════════
// WORKSPACE / CONFIG / LOGS tabs (same as generic page)
// ═══════════════════════════════════════════════════════════════════════════════

interface WorkspaceTabProps {
  identity: NonNullable<ReturnType<typeof getAgentIdentity>>;
  inProgress: Task[];
  todo: Task[];
  completed: Task[];
  loading: boolean;
  onTaskClick: (t: Task) => void;
}

function WorkspaceTab({ identity, inProgress, todo, completed, loading, onTaskClick }: WorkspaceTabProps) {
  if (loading) {
    return (
      <div style={{ padding: 20, color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)", fontSize: 11 } as CSSProperties}>
        Loading…
      </div>
    );
  }

  if (inProgress.length === 0 && todo.length === 0 && completed.length === 0) {
    return <Hatch label="NO TASKS ASSIGNED" height={120} className="m-5" />;
  }

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 } as CSSProperties}>
      {inProgress.length > 0 && (
        <div>
          <SubH trailing={<Dot kind="ok" pulse />}>IN PROGRESS · {inProgress.length}</SubH>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 } as CSSProperties}>
            {inProgress.map((t) => (
              <MiniTaskCard key={t.id} task={t} identity={identity} onClick={() => onTaskClick(t)} />
            ))}
          </div>
        </div>
      )}
      {todo.length > 0 && (
        <div>
          <SubH>QUEUED · {todo.length}</SubH>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 } as CSSProperties}>
            {todo.map((t) => (
              <MiniTaskCard key={t.id} task={t} identity={identity} onClick={() => onTaskClick(t)} />
            ))}
          </div>
        </div>
      )}
      {completed.length > 0 && (
        <div>
          <SubH>COMPLETED · {completed.length}</SubH>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8, opacity: 0.55 } as CSSProperties}>
            {completed.slice(0, 12).map((t) => (
              <MiniTaskCard key={t.id} task={t} identity={identity} onClick={() => onTaskClick(t)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MiniTaskCard({
  task,
  identity,
  onClick,
}: {
  task: Task;
  identity: NonNullable<ReturnType<typeof getAgentIdentity>>;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "var(--ops-bg-elevated)",
        border: "1px solid var(--ops-line)",
        borderLeft: `2px solid ${identity.colorHex}`,
        padding: "8px 10px",
        cursor: "pointer",
        borderRadius: 2,
      } as CSSProperties}
    >
      <div style={{ fontSize: 12, color: "var(--ops-fg)", lineHeight: 1.4, fontFamily: "var(--ops-sans)", marginBottom: 4 } as CSSProperties}>
        {task.title}
      </div>
      <div style={{ fontSize: 9, color: "var(--ops-fg-faint)", fontFamily: "var(--ops-mono)", letterSpacing: "0.08em" } as CSSProperties}>
        {task.kanban.toUpperCase()}
        {task.dueDate && (
          <span style={{ marginLeft: 8 } as CSSProperties}>
            DUE {new Date(task.dueDate).toLocaleDateString([], { month: "short", day: "numeric" })}
          </span>
        )}
      </div>
    </div>
  );
}

function ConfigTab({
  identity,
  agentDef,
}: {
  identity: NonNullable<ReturnType<typeof getAgentIdentity>>;
  agentDef: { instructions?: string; capabilities?: string[] } | undefined;
}) {
  return (
    <div
      style={{
        padding: 16,
        display: "grid",
        gridTemplateColumns: "1fr 300px",
        gap: 14,
        height: "100%",
        overflow: "auto",
      } as CSSProperties}
    >
      <Panel title="AGENT CONFIG · JSON">
        <pre style={{ fontFamily: "var(--ops-mono)", fontSize: 10, color: "var(--ops-fg-mute)", lineHeight: 1.7, whiteSpace: "pre-wrap", wordBreak: "break-word" } as CSSProperties}>
          {JSON.stringify({ id: identity.id, name: identity.name, role: identity.role, model: identity.model, tagline: identity.tagline, ...(agentDef ? { capabilities: agentDef.capabilities ?? [], instructions: agentDef.instructions ?? "" } : {}) }, null, 2)}
        </pre>
      </Panel>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 } as CSSProperties}>
        <Panel title="MODEL">
          <KV label="ASSIGNED">{identity.model}</KV>
          <KV label="ROUTING">
            {identity.model.includes("opus") ? "complex / risky" : identity.model.includes("sonnet") ? "default subsystem" : "high-frequency utility"}
          </KV>
        </Panel>
        <Panel title="CAPABILITIES">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 } as CSSProperties}>
            {(agentDef?.capabilities ?? []).length > 0 ? (
              (agentDef?.capabilities ?? []).map((cap) => <Tag key={cap}>{cap}</Tag>)
            ) : (
              <span style={{ fontSize: 10, color: "var(--ops-fg-faint)", fontFamily: "var(--ops-mono)" } as CSSProperties}>— none defined —</span>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

interface LogEntry {
  id: string;
  actor: string;
  summary: string;
  timestamp: string;
}

function LogsTab({
  identity,
  events,
}: {
  identity: NonNullable<ReturnType<typeof getAgentIdentity>>;
  events: LogEntry[];
}) {
  if (events.length === 0) {
    return (
      <div style={{ padding: 16 } as CSSProperties}>
        <Hatch label={`NO LOG ENTRIES · ${identity.name}`} height={120} />
      </div>
    );
  }

  return (
    <div style={{ padding: 14 } as CSSProperties}>
      <Panel
        title={`LOGS · ${identity.name}`}
        leading={<Dot kind="ok" pulse />}
        trailing={
          <span style={{ fontSize: 9, color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)", letterSpacing: "0.1em" } as CSSProperties}>
            TAIL={events.length}
          </span>
        }
        flushBody
      >
        <div style={{ padding: "6px 14px", fontFamily: "var(--ops-mono)", fontSize: 11, lineHeight: 1.7 } as CSSProperties}>
          {events.map((evt, i) => (
            <div
              key={evt.id}
              style={{
                display: "grid",
                gridTemplateColumns: "80px 1fr",
                gap: 10,
                padding: "2px 0",
                borderBottom: "1px dashed var(--ops-line-faint)",
                opacity: 1 - i * 0.015,
              } as CSSProperties}
            >
              <span style={{ color: "var(--ops-fg-faint)" } as CSSProperties}>
                {new Date(evt.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </span>
              <span style={{ color: "var(--ops-fg-mute)" } as CSSProperties}>{evt.summary}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

// ─── Tiny primitives ──────────────────────────────────────────────────────────

function MonoText({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: CSSProperties;
}) {
  return (
    <span
      style={{
        fontFamily: "var(--ops-mono)",
        fontSize: 10,
        letterSpacing: "0.1em",
        color: "var(--ops-fg-dim)",
        ...style,
      } as CSSProperties}
    >
      {children}
    </span>
  );
}

function MonoLabel({ children }: { children: string }) {
  return (
    <div
      style={{
        fontFamily: "var(--ops-mono)",
        fontSize: 8,
        letterSpacing: "0.16em",
        color: "var(--ops-fg-faint)",
      } as CSSProperties}
    >
      {children}
    </div>
  );
}
