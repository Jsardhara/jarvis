"use client";

import { CSSProperties, useMemo, useState } from "react";
import type { DragEndEvent } from "@dnd-kit/core";
import { Plus } from "lucide-react";
import {
  BoardDndWrapper,
  BoardPanels,
  useTaskHandlers,
  useSelection,
} from "@/components/board-view";
import { BulkActionBar } from "@/components/bulk-action-bar";
import { useTasks, useGoals, useProjects, useDecisions } from "@/hooks/use-data";
import { useActiveRunsContext as useActiveRuns } from "@/providers/active-runs-provider";
import { useFastTaskPoll } from "@/hooks/use-fast-task-poll";
import type { Task, KanbanStatus } from "@/lib/types";
import { Tag, AgentGlyph, Dot, OpsButton, getAgentIdentity, SUBSYSTEM_AGENTS } from "@/components/ops";
import { useDraggable, useDroppable } from "@dnd-kit/core";

// ─── Column config ────────────────────────────────────────────────────────────

interface OpsColumn {
  id: string;
  label: string;
  sub: string;
  accentVar: string;
  filter: (task: Task, runningIds: Set<string>, blockedIds: Set<string>) => boolean;
}

const OPS_COLUMNS: OpsColumn[] = [
  {
    id: "inbox",
    label: "INBOX",
    sub: "unrouted",
    accentVar: "var(--ops-info)",
    filter: (t) => t.assignedTo == null && t.kanban === "not-started",
  },
  {
    id: "classified",
    label: "CLASSIFIED",
    sub: "assigned",
    accentVar: "var(--ops-info)",
    filter: (t) => t.assignedTo != null && t.kanban === "not-started",
  },
  {
    id: "dispatched",
    label: "DISPATCHED",
    sub: "queued",
    accentVar: "var(--ops-amber)",
    filter: (t, running) => t.kanban === "in-progress" && !running.has(t.id),
  },
  {
    id: "active",
    label: "ACTIVE",
    sub: "running",
    accentVar: "var(--ops-amber)",
    filter: (t, running) => t.kanban === "in-progress" && running.has(t.id),
  },
  {
    id: "blocked",
    label: "BLOCKED",
    sub: "dependencies",
    accentVar: "var(--ops-crit)",
    filter: (t, _running, blocked) => blocked.has(t.id),
  },
  {
    id: "done",
    label: "DONE",
    sub: "completed",
    accentVar: "var(--ops-ok)",
    filter: (t) => t.kanban === "done",
  },
];

// ─── Priority color ───────────────────────────────────────────────────────────

function priorityColor(p: string | null | undefined): string {
  if (p === "p0") return "var(--ops-crit)";
  if (p === "p1") return "var(--ops-amber)";
  if (p === "p2") return "var(--ops-info)";
  return "var(--ops-fg-faint)";
}

// ─── Ops task card ────────────────────────────────────────────────────────────

interface OpsTaskCardProps {
  task: Task;
  isRunning: boolean;
  onOpen: () => void;
  onRun?: (id: string) => void;
  pendingDecisionTaskIds: Set<string>;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
}

function OpsTaskCard({
  task,
  isRunning,
  onOpen,
  pendingDecisionTaskIds,
  isSelected,
  onToggleSelect,
  // onRun intentionally unused — run flow not wired to ops kanban yet
}: OpsTaskCardProps) {
  const identity = getAgentIdentity(task.assignedTo ?? null);
  const [hovered, setHovered] = useState(false);
  const priority = (task as unknown as Record<string, unknown>).priority as string | undefined;
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: task.id });

  const dragStyle: CSSProperties = transform
    ? { transform: `translate(${transform.x}px, ${transform.y}px)`, zIndex: 50 }
    : {};

  return (
    <div
      ref={setNodeRef}
      style={dragStyle}
      {...attributes}
      {...listeners}
    >
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={(e) => {
          if (e.ctrlKey || e.metaKey) {
            onToggleSelect(task.id);
          } else {
            onOpen();
          }
        }}
        style={{
          background: isSelected
            ? "var(--ops-bg-elevated)"
            : hovered
            ? "var(--ops-bg-hover)"
            : "var(--ops-bg-elevated)",
          border: isSelected
            ? "1px solid var(--ops-amber)"
            : "1px solid var(--ops-line)",
          borderLeft: `2px solid ${priorityColor(priority)}`,
          padding: "8px 10px",
          marginBottom: 6,
          cursor: isDragging ? "grabbing" : "pointer",
          borderRadius: 2,
          transition: "background 100ms",
          userSelect: "none",
          opacity: isDragging ? 0.5 : 1,
        } as CSSProperties}
      >
        {/* top row */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 5,
            fontSize: 9,
            fontFamily: "var(--ops-mono)",
            letterSpacing: "0.12em",
          } as CSSProperties}
        >
          <span style={{ color: "var(--ops-fg-faint)" } as CSSProperties}>
            {task.id.slice(0, 8)}
          </span>
          {priority && (
            <span
              style={{
                color: priorityColor(priority),
                textTransform: "uppercase",
                fontWeight: 600,
              } as CSSProperties}
            >
              {priority}
            </span>
          )}
        </div>

        {/* title */}
        <div
          style={{
            fontSize: 12,
            color: "var(--ops-fg)",
            lineHeight: 1.4,
            marginBottom: 6,
            fontFamily: "var(--ops-sans)",
          } as CSSProperties}
        >
          {task.title}
        </div>

        {/* footer */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            paddingTop: 5,
            borderTop: "1px solid var(--ops-line)",
          } as CSSProperties}
        >
          {identity ? (
            <>
              <AgentGlyph agent={identity} size={12} />
              <span
                style={{
                  fontSize: 9,
                  color: identity.colorHex,
                  fontFamily: "var(--ops-mono)",
                  letterSpacing: "0.08em",
                } as CSSProperties}
              >
                {identity.name}
              </span>
            </>
          ) : (
            <span
              style={{
                fontSize: 9,
                color: "var(--ops-fg-faint)",
                fontFamily: "var(--ops-mono)",
              } as CSSProperties}
            >
              ◇ UNROUTED
            </span>
          )}
          {isRunning && <Dot kind="ok" pulse className="ml-auto" />}
          {pendingDecisionTaskIds.has(task.id) && (
            <Tag kind="amber" className="ml-auto">
              DECISION
            </Tag>
          )}
          {task.dueDate && (
            <span
              style={{
                marginLeft: "auto",
                fontSize: 9,
                color: "var(--ops-fg-faint)",
                fontFamily: "var(--ops-mono)",
              } as CSSProperties}
            >
              {new Date(task.dueDate).toLocaleDateString([], {
                month: "numeric",
                day: "numeric",
              })}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Ops kanban column ────────────────────────────────────────────────────────

interface OpsColumnProps {
  col: OpsColumn;
  tasks: Task[];
  runningTaskIds: Set<string>;
  pendingDecisionTaskIds: Set<string>;
  selected: Set<string>;
  onToggleSelect: (id: string) => void;
  onTaskClick: (task: Task) => void;
  onRun: (id: string) => void;
}

function OpsKanbanColumn({
  col,
  tasks,
  runningTaskIds,
  pendingDecisionTaskIds,
  selected,
  onToggleSelect,
  onTaskClick,
  onRun,
}: OpsColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: col.id });

  return (
    <div
      style={{
        flex: "0 0 240px",
        background: isOver ? "var(--ops-bg-elevated)" : "var(--ops-bg-panel)",
        border: "1px solid var(--ops-line)",
        borderTop: `2px solid ${col.accentVar}`,
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        transition: "background 100ms",
      } as CSSProperties}
    >
      {/* header */}
      <div
        style={{
          padding: "8px 10px",
          borderBottom: "1px solid var(--ops-line)",
          display: "flex",
          alignItems: "center",
          gap: 6,
        } as CSSProperties}
      >
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            letterSpacing: "0.14em",
            color: "var(--ops-fg)",
            fontWeight: 600,
          } as CSSProperties}
        >
          {col.label}
        </span>
        <span
          style={{
            fontSize: 9,
            letterSpacing: "0.1em",
            color: "var(--ops-fg-faint)",
            fontFamily: "var(--ops-mono)",
          } as CSSProperties}
        >
          {col.sub}
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: col.accentVar,
            fontVariantNumeric: "tabular-nums",
          } as CSSProperties}
        >
          {String(tasks.length).padStart(2, "0")}
        </span>
      </div>

      {/* task stack */}
      <div
        ref={setNodeRef}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: 8,
          minHeight: 120,
        } as CSSProperties}
      >
        {tasks.length === 0 ? (
          <div
            style={{
              padding: 14,
              textAlign: "center",
              fontSize: 10,
              color: "var(--ops-fg-faint)",
              letterSpacing: "0.16em",
              border: "1px dashed var(--ops-line)",
              fontFamily: "var(--ops-mono)",
            } as CSSProperties}
          >
            — empty —
          </div>
        ) : (
          tasks.map((t) => (
            <OpsTaskCard
              key={t.id}
              task={t}
              isRunning={runningTaskIds.has(t.id)}
              onOpen={() => onTaskClick(t)}
              onRun={onRun}
              pendingDecisionTaskIds={pendingDecisionTaskIds}
              isSelected={selected.has(t.id)}
              onToggleSelect={onToggleSelect}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function StatusBoardPage() {
  const {
    tasks,
    update: updateTask,
    create: createTask,
    remove: deleteTask,
    bulkUpdate,
    bulkRemove,
    loading,
    error: tasksError,
    refetch,
  } = useTasks();
  const { goals } = useGoals();
  const { projects } = useProjects();
  const { decisions } = useDecisions();
  const { runningTaskIds, runTask } = useActiveRuns();
  useFastTaskPoll(runningTaskIds.size > 0, refetch);

  const [agentFilter, setAgentFilter] = useState<string>("all");

  const pendingDecisionTaskIds = useMemo(
    () =>
      new Set(
        decisions.filter((d) => d.status === "pending" && d.taskId).map((d) => d.taskId as string),
      ),
    [decisions],
  );

  const selection = useSelection();

  const {
    activeTask,
    selectedTask,
    setSelectedTask,
    showCreateTask,
    setShowCreateTask,
    handleDragStart,
    handleDragEnd: baseDragEnd,
    handleUpdateTask,
    handleCreateTask,
    handleDeleteTask,
  } = useTaskHandlers(tasks, updateTask, createTask, deleteTask);

  // Build blocked set: tasks with unfinished blockedBy deps
  const blockedIds = useMemo(() => {
    const set = new Set<string>();
    for (const t of tasks) {
      if (!t.blockedBy || t.blockedBy.length === 0) continue;
      const hasBlocker = t.blockedBy.some((depId) => {
        const dep = tasks.find((d) => d.id === depId);
        return dep && dep.kanban !== "done";
      });
      if (hasBlocker) set.add(t.id);
    }
    return set;
  }, [tasks]);

  // Filter by agent
  const filteredTasks = useMemo(() => {
    if (agentFilter === "all") return tasks;
    return tasks.filter((t) => t.assignedTo === agentFilter);
  }, [tasks, agentFilter]);

  // Derive 6 columns
  const grouped = useMemo(() => {
    const cols: Record<string, Task[]> = {
      inbox: [], classified: [], dispatched: [], active: [], blocked: [], done: [],
    };
    for (const task of filteredTasks) {
      for (const col of OPS_COLUMNS) {
        if (col.filter(task, runningTaskIds, blockedIds)) {
          cols[col.id].push(task);
          break;
        }
      }
    }
    return cols;
  }, [filteredTasks, runningTaskIds, blockedIds]);

  async function handleDragEnd(event: DragEndEvent) {
    baseDragEnd();
    const { active, over } = event;
    if (!over) return;
    const targetColId = String(over.id);
    const task = tasks.find((t) => t.id === active.id);
    if (!task) return;

    // Map column id to kanban status
    const toStatus: Record<string, KanbanStatus> = {
      inbox: "not-started",
      classified: "not-started",
      dispatched: "in-progress",
      active: "in-progress",
      blocked: "in-progress",
      done: "done",
    };
    const newStatus = toStatus[targetColId];
    if (!newStatus || task.kanban === newStatus) return;
    await updateTask(task.id, { kanban: newStatus });
  }

  if (loading) {
    return (
      <div
        style={{
          padding: 20,
          color: "var(--ops-fg-dim)",
          fontFamily: "var(--ops-mono)",
          fontSize: 11,
        } as CSSProperties}
      >
        Loading…
      </div>
    );
  }

  if (tasksError) {
    return (
      <div
        style={{
          padding: 20,
          color: "var(--ops-crit)",
          fontFamily: "var(--ops-mono)",
          fontSize: 11,
          border: "1px solid var(--ops-crit)",
        } as CSSProperties}
      >
        Error: {tasksError}
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      } as CSSProperties}
    >
      {/* filter bar */}
      <div
        style={{
          padding: "8px 16px",
          borderBottom: "1px solid var(--ops-line)",
          background: "var(--ops-bg-deep)",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexWrap: "wrap",
        } as CSSProperties}
      >
        <span
          style={{
            fontSize: 9,
            letterSpacing: "0.18em",
            color: "var(--ops-fg-dim)",
            fontFamily: "var(--ops-mono)",
          } as CSSProperties}
        >
          FILTER
        </span>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" } as CSSProperties}>
          <FilterChip
            active={agentFilter === "all"}
            onClick={() => setAgentFilter("all")}
          >
            ALL · {tasks.length}
          </FilterChip>
          {SUBSYSTEM_AGENTS.map((id) => {
            const identity = getAgentIdentity(id);
            if (!identity) return null;
            const count = tasks.filter((t) => t.assignedTo === id).length;
            return (
              <FilterChip
                key={id}
                active={agentFilter === id}
                onClick={() => setAgentFilter(id)}
                accentColor={identity.colorHex}
              >
                <AgentGlyph agent={identity} size={10} />
                {identity.name} · {count}
              </FilterChip>
            );
          })}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 } as CSSProperties}>
          <OpsButton
            onClick={() => setShowCreateTask(true)}
            style={{ display: "flex", alignItems: "center", gap: 4 } as CSSProperties}
          >
            <Plus style={{ width: 11, height: 11 } as CSSProperties} /> TASK
          </OpsButton>
        </div>
      </div>

      {/* board */}
      <div style={{ flex: 1, overflow: "auto", padding: 12 } as CSSProperties}>
        <BoardDndWrapper
          activeTask={activeTask}
          projects={projects}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <div
            style={{
              display: "flex",
              gap: 10,
              minWidth: "max-content",
              height: "100%",
              minHeight: 480,
            } as CSSProperties}
          >
            {OPS_COLUMNS.map((col) => (
              <OpsKanbanColumn
                key={col.id}
                col={col}
                tasks={grouped[col.id] ?? []}
                runningTaskIds={runningTaskIds}
                pendingDecisionTaskIds={pendingDecisionTaskIds}
                selected={selection.selected}
                onToggleSelect={selection.toggle}
                onTaskClick={setSelectedTask}
                onRun={runTask}
              />
            ))}
          </div>
        </BoardDndWrapper>
      </div>

      <BulkActionBar
        count={selection.count}
        onMarkDone={async () => {
          await bulkUpdate(selection.ids, { kanban: "done" } as Partial<Task>);
          selection.clear();
        }}
        onDelete={async () => {
          await bulkRemove(selection.ids);
          selection.clear();
        }}
        onClear={selection.clear}
      />

      <BoardPanels
        tasks={tasks}
        projects={projects}
        goals={goals}
        selectedTask={selectedTask}
        showCreateTask={showCreateTask}
        onUpdate={handleUpdateTask}
        onDelete={handleDeleteTask}
        onCloseDetail={() => setSelectedTask(null)}
        onCloseCreate={setShowCreateTask}
        onSubmitCreate={handleCreateTask}
      />
    </div>
  );
}

// ─── Filter chip ──────────────────────────────────────────────────────────────

function FilterChip({
  active,
  onClick,
  accentColor,
  children,
}: {
  active: boolean;
  onClick: () => void;
  accentColor?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? "var(--ops-bg-elevated)" : "transparent",
        border: `1px solid ${active ? (accentColor ?? "var(--ops-amber)") : "var(--ops-line)"}`,
        color: active ? (accentColor ?? "var(--ops-amber)") : "var(--ops-fg-mute)",
        padding: "3px 7px",
        fontSize: 9,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        borderRadius: 2,
        fontFamily: "var(--ops-mono)",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: 4,
      } as CSSProperties}
    >
      {children}
    </button>
  );
}
