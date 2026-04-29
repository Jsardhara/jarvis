"use client";

import { CSSProperties, useState } from "react";
import { useParams } from "next/navigation";
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
import { useTasks, useActivityLog } from "@/hooks/use-data";
import { useActiveRunsContext as useActiveRuns } from "@/providers/active-runs-provider";
import { useFastTaskPoll } from "@/hooks/use-fast-task-poll";
import { TaskDetailPanel } from "@/components/task-detail-panel";
import { useGoals, useProjects, useAgents } from "@/hooks/use-data";
import type { Task } from "@/lib/types";
import type { TaskFormData } from "@/components/task-form";

// ─── Tabs ─────────────────────────────────────────────────────────────────────

const TABS = [
  { id: "workspace", label: "WORKSPACE" },
  { id: "config", label: "CONFIG" },
  { id: "memory", label: "MEMORY" },
  { id: "logs", label: "LOGS" },
] as const;
type TabId = (typeof TABS)[number]["id"];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AgentDetailPage() {
  const params = useParams();
  const roleId = params.role as string;

  const identity = getAgentIdentity(roleId);

  const { tasks, loading, update: updateTask, remove: deleteTask, refetch } = useTasks();
  const { goals } = useGoals();
  const { projects } = useProjects();
  const { agents } = useAgents();
  const { events } = useActivityLog();
  const { runningTaskIds } = useActiveRuns();
  useFastTaskPoll(runningTaskIds.size > 0, refetch);

  const [tab, setTab] = useState<TabId>("workspace");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  // Unknown agent
  if (!identity) {
    return (
      <div style={{ padding: 24 } as CSSProperties}>
        <Hatch label={`AGENT "${roleId.toUpperCase()}" NOT FOUND`} height={120} />
      </div>
    );
  }

  const agentTasks = tasks.filter(
    (t) => t.assignedTo === identity.id,
  );
  const inProgress = agentTasks.filter((t) => t.kanban === "in-progress");
  const todo = agentTasks.filter((t) => t.kanban === "not-started");
  const completed = agentTasks.filter((t) => t.kanban === "done");
  const agentEvents = events.filter((e) => e.actor === identity.id).slice(0, 20);

  // Find the registered agent definition (if any)
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

  const bars = Array.from({ length: 36 }, () => 5 + Math.random() * 32);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      } as CSSProperties}
    >
      {/* ── Header strip ───────────────────────────────────────────────────── */}
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
        {/* left accent rail */}
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

        {/* glyph + name */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
          } as CSSProperties}
        >
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

        {/* activity sparkline */}
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

        {/* stats */}
        <HeaderStat label="ACTIVE" value={String(inProgress.length)} />
        <HeaderStat label="QUEUE" value={String(todo.length)} />
        <HeaderStat label="DONE" value={String(completed.length)} accent="var(--ops-ok)" />

        {/* controls */}
        <div style={{ display: "flex", gap: 6 } as CSSProperties}>
          <OpsButton variant="primary">▶ START</OpsButton>
          <OpsButton variant="danger">◼ PAUSE</OpsButton>
        </div>
      </div>

      {/* ── Tab bar ─────────────────────────────────────────────────────────── */}
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

      {/* ── Tab content ──────────────────────────────────────────────────────── */}
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
        {tab === "config" && (
          <ConfigTab identity={identity} agentDef={agentDef} />
        )}
        {tab === "memory" && (
          <MemoryTab identity={identity} />
        )}
        {tab === "logs" && (
          <LogsTab identity={identity} events={agentEvents} />
        )}
      </div>

      {/* Task detail panel */}
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

// ─── Workspace tab ────────────────────────────────────────────────────────────

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

  if (inProgress.length === 0 && todo.length === 0 && completed.length === 0) {
    return <Hatch label="NO TASKS ASSIGNED" height={120} className="m-5" />;
  }

  return (
    <div
      style={{
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 14,
      } as CSSProperties}
    >
      {inProgress.length > 0 && (
        <div>
          <SubH trailing={<Dot kind="ok" pulse />}>IN PROGRESS · {inProgress.length}</SubH>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 8,
            } as CSSProperties}
          >
            {inProgress.map((t) => (
              <MiniTaskCard key={t.id} task={t} identity={identity} onClick={() => onTaskClick(t)} />
            ))}
          </div>
        </div>
      )}
      {todo.length > 0 && (
        <div>
          <SubH>QUEUED · {todo.length}</SubH>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 8,
            } as CSSProperties}
          >
            {todo.map((t) => (
              <MiniTaskCard key={t.id} task={t} identity={identity} onClick={() => onTaskClick(t)} />
            ))}
          </div>
        </div>
      )}
      {completed.length > 0 && (
        <div>
          <SubH>COMPLETED · {completed.length}</SubH>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 8,
              opacity: 0.55,
            } as CSSProperties}
          >
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
      <div
        style={{
          fontSize: 12,
          color: "var(--ops-fg)",
          lineHeight: 1.4,
          fontFamily: "var(--ops-sans)",
          marginBottom: 4,
        } as CSSProperties}
      >
        {task.title}
      </div>
      <div
        style={{
          fontSize: 9,
          color: "var(--ops-fg-faint)",
          fontFamily: "var(--ops-mono)",
          letterSpacing: "0.08em",
        } as CSSProperties}
      >
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

// ─── Config tab ───────────────────────────────────────────────────────────────

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
        <pre
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-fg-mute)",
            lineHeight: 1.7,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          } as CSSProperties}
        >
          {JSON.stringify(
            {
              id: identity.id,
              name: identity.name,
              role: identity.role,
              model: identity.model,
              tagline: identity.tagline,
              ...(agentDef
                ? {
                    capabilities: agentDef.capabilities ?? [],
                    instructions: agentDef.instructions ?? "",
                  }
                : {}),
            },
            null,
            2,
          )}
        </pre>
      </Panel>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 } as CSSProperties}>
        <Panel title="MODEL">
          <KV label="ASSIGNED">{identity.model}</KV>
          <KV label="ROUTING">
            {identity.model.includes("opus")
              ? "complex / risky"
              : identity.model.includes("sonnet")
              ? "default subsystem"
              : "high-frequency utility"}
          </KV>
        </Panel>
        <Panel title="CAPABILITIES">
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 4,
            } as CSSProperties}
          >
            {(agentDef?.capabilities ?? []).length > 0 ? (
              (agentDef?.capabilities ?? []).map((cap) => (
                <Tag key={cap}>{cap}</Tag>
              ))
            ) : (
              <span
                style={{
                  fontSize: 10,
                  color: "var(--ops-fg-faint)",
                  fontFamily: "var(--ops-mono)",
                } as CSSProperties}
              >
                — none defined —
              </span>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

// ─── Memory tab ───────────────────────────────────────────────────────────────

function MemoryTab({ identity }: { identity: NonNullable<ReturnType<typeof getAgentIdentity>> }) {
  return (
    <div style={{ padding: 16 } as CSSProperties}>
      <Hatch
        label={`MEMORY · ${identity.name.toUpperCase()} · NO ENTRIES`}
        height={160}
      />
      <div
        style={{
          marginTop: 8,
          fontSize: 9,
          color: "var(--ops-fg-faint)",
          fontFamily: "var(--ops-mono)",
          letterSpacing: "0.12em",
          textAlign: "center",
        } as CSSProperties}
      >
        MEMORY API NOT AVAILABLE · WIRE TO /api/memory WHEN READY
      </div>
    </div>
  );
}

// ─── Logs tab ─────────────────────────────────────────────────────────────────

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
          <span
            style={{
              fontSize: 9,
              color: "var(--ops-fg-dim)",
              fontFamily: "var(--ops-mono)",
              letterSpacing: "0.1em",
            } as CSSProperties}
          >
            TAIL={events.length}
          </span>
        }
        flushBody
      >
        <div
          style={{
            padding: "6px 14px",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            lineHeight: 1.7,
          } as CSSProperties}
        >
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
                {new Date(evt.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
              <span style={{ color: "var(--ops-fg-mute)" } as CSSProperties}>
                {evt.summary}
              </span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
