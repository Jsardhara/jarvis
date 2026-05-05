"use client";

import { CSSProperties, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Panel,
  AgentGlyph,
  Bars,
  SubH,
  Dot,
  KV,
  Tag,
  OpsButton,
  getAgentIdentity,
  SUBSYSTEM_AGENTS,
} from "@/components/ops";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import type { Task, Project, Goal, DecisionItem, InboxMessage } from "@/lib/types";
import { useDailyCost } from "@/hooks/useDailyCost";
import { useDaemon } from "@/hooks/use-daemon";
import { useActiveRunsContext as useActiveRuns } from "@/providers/active-runs-provider";
import { useFastTaskPoll } from "@/hooks/use-fast-task-poll";
import type { ActivityEvent } from "@/lib/types";
import {
  Plus,
  Mail, HelpCircle, AlertTriangle, Database,
} from "lucide-react";
import dynamic from "next/dynamic";
import type { TaskFormData } from "@/components/task-form";
import { apiFetch } from "@/lib/api-client";
import { showSuccess, showError } from "@/lib/toast";
import { toast } from "sonner";

const CreateTaskDialog = dynamic(
  () => import("@/components/create-task-dialog").then((mod) => ({ default: mod.CreateTaskDialog })),
  { ssr: false },
);
const CreateProjectDialog = dynamic(
  () => import("@/components/create-project-dialog").then((mod) => ({
    default: mod.CreateProjectDialog,
  })),
  { ssr: false },
);

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CommandCenterPage() {
  const { data, loading, error, refetch } = useDashboardData();
  const { isRunning: daemonRunning, status: daemonStatus } = useDaemon();
  const { runningTaskIds } = useActiveRuns();
  const { data: costData } = useDailyCost(7);
  useFastTaskPoll(runningTaskIds.size > 0, refetch);

  const [showCreateTask, setShowCreateTask] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const tasks = data?.tasks ?? [];
  const goals = data?.goals ?? [];
  const projects = data?.projects ?? [];
  const recentEvents = data?.recentActivity ?? [];
  const stats = data?.stats;
  const pendingDecisions = data?.decisions ?? [];
  const unreadMessages = data?.messages ?? [];

  const todayCost = costData.length > 0 ? costData[costData.length - 1]?.totalUsd : null;

  const handleCreateTask = async (formData: TaskFormData) => {
    try {
      const res = await apiFetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...formData,
          dailyActions: [],
          tags: formData.tags.split(",").map((t) => t.trim()).filter(Boolean),
          acceptanceCriteria: formData.acceptanceCriteria
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error("Failed to create task");
      showSuccess("Task created");
      refetch();
    } catch {
      showError("Failed to create task");
    }
  };

  const handleCreateProject = async (formData: {
    name: string;
    description: string;
    color: string;
    tags: string;
    teamMembers?: string[];
  }) => {
    try {
      const res = await apiFetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formData.name,
          description: formData.description,
          status: "active",
          color: formData.color,
          teamMembers: formData.teamMembers ?? [],
          tags: formData.tags.split(",").map((t) => t.trim()).filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error("Failed to create project");
      showSuccess("Project created");
      refetch();
    } catch {
      showError("Failed to create project");
    }
  };

  const handleSeedDemo = async () => {
    setSeeding(true);
    try {
      const res = await fetch("/api/seed-demo", { method: "POST" });
      if (res.ok) {
        toast.success("Demo data loaded! Refreshing...");
        setTimeout(() => window.location.reload(), 500);
      } else {
        toast.error("Failed to load demo data");
      }
    } catch {
      toast.error("Failed to load demo data");
    } finally {
      setSeeding(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 20, color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)", fontSize: 11 } as CSSProperties}>
        Loading…
      </div>
    );
  }

  if (error) {
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
        Error: {error}
      </div>
    );
  }

  return (
    <div
      style={{
        padding: 20,
        display: "flex",
        flexDirection: "column",
        gap: 18,
        minHeight: "100%",
      } as CSSProperties}
    >
      {/* ── Hero strip: orchestrator status ────────────────────────────────── */}
      <div
        className="hero-kpi-5"
        style={{
          background: "var(--ops-bg-panel)",
          border: "1px solid var(--ops-line)",
          padding: "14px 18px 14px 21px",
          position: "relative",
          alignItems: "center",
        } as CSSProperties}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            height: "100%",
            width: 3,
            background: "var(--ops-amber)",
            boxShadow: "0 0 12px var(--ops-amber-glow)",
          } as CSSProperties}
        />
        <div>
          <div
            style={{
              fontFamily: "var(--ops-sans)",
              fontSize: 10,
              letterSpacing: "0.2em",
              color: "var(--ops-amber)",
              marginBottom: 3,
            } as CSSProperties}
          >
            {daemonRunning ? "ORCHESTRATOR · ONLINE" : "ORCHESTRATOR · STANDBY"}
          </div>
          <div
            style={{
              fontFamily: "var(--ops-sans)",
              fontSize: 20,
              fontWeight: 500,
              letterSpacing: "0.04em",
              display: "flex",
              alignItems: "center",
              gap: 10,
            } as CSSProperties}
          >
            COMMAND CENTER
            <Dot kind={daemonRunning ? "ok" : "idle"} pulse={daemonRunning} />
          </div>
          <div
            style={{ fontSize: 10, color: "var(--ops-fg-dim)", marginTop: 2 } as CSSProperties}
          >
            {daemonRunning
              ? `${daemonStatus.activeSessions.length} session${daemonStatus.activeSessions.length !== 1 ? "s" : ""} active · ${daemonStatus.stats.tasksCompleted} completed`
              : "Daemon inactive — autonomous processing disabled"}
          </div>
        </div>
        <HeroStat label="TASKS" value={String(stats?.totalTasks ?? tasks.length)} />
        <HeroStat label="IN PROGRESS" value={String(stats?.inProgressTasks ?? 0)} />
        <HeroStat label="PROJECTS" value={String(stats?.activeProjects ?? projects.filter((p) => p.status === "active").length)} />
        <HeroStat
          label="COST / TODAY"
          value={todayCost != null ? `$${todayCost.toFixed(2)}` : "—"}
          accent="var(--ops-amber)"
        />
      </div>

      {/* ── Quick actions ───────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" } as CSSProperties}>
        <OpsButton onClick={() => setShowCreateTask(true)} style={{ display: "flex", alignItems: "center", gap: 4 } as CSSProperties}>
          <Plus style={{ width: 12, height: 12 } as CSSProperties} /> NEW TASK
        </OpsButton>
        <OpsButton onClick={() => setShowCreateProject(true)} style={{ display: "flex", alignItems: "center", gap: 4 } as CSSProperties}>
          <Plus style={{ width: 12, height: 12 } as CSSProperties} /> NEW PROJECT
        </OpsButton>
        <Link href="/jarvis" style={{ textDecoration: "none" }}>
          <OpsButton variant="primary" style={{ display: "flex", alignItems: "center", gap: 4 } as CSSProperties}>
            TALK TO JARVIS
          </OpsButton>
        </Link>
        {tasks.length === 0 && projects.length === 0 && (
          <OpsButton onClick={handleSeedDemo} disabled={seeding} style={{ display: "flex", alignItems: "center", gap: 4 } as CSSProperties}>
            <Database style={{ width: 12, height: 12 } as CSSProperties} />
            {seeding ? "LOADING…" : "LOAD DEMO"}
          </OpsButton>
        )}
      </div>

      {/* ── Attention required ──────────────────────────────────────────────── */}
      {(pendingDecisions.length > 0 || unreadMessages.length > 0) && (
        <div
          style={{
            border: "1px solid var(--ops-amber)",
            borderLeft: "3px solid var(--ops-amber)",
            background: "rgba(242,160,61,0.05)",
            padding: "10px 14px",
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontSize: 11,
            fontFamily: "var(--ops-mono)",
          } as CSSProperties}
        >
          <AlertTriangle style={{ width: 14, height: 14, color: "var(--ops-amber)", flexShrink: 0 } as CSSProperties} />
          <span style={{ color: "var(--ops-amber)", letterSpacing: "0.1em" } as CSSProperties}>
            ATTENTION REQUIRED
          </span>
          {pendingDecisions.length > 0 && (
            <Link href="/decisions" style={{ textDecoration: "none" }}>
              <Tag kind="amber">
                <HelpCircle style={{ display: "inline", width: 10, height: 10, marginRight: 3 } as CSSProperties} />
                {pendingDecisions.length} DECISION{pendingDecisions.length !== 1 ? "S" : ""}
              </Tag>
            </Link>
          )}
          {unreadMessages.length > 0 && (
            <Link href="/inbox" style={{ textDecoration: "none" }}>
              <Tag kind="info">
                <Mail style={{ display: "inline", width: 10, height: 10, marginRight: 3 } as CSSProperties} />
                {unreadMessages.length} UNREAD
              </Tag>
            </Link>
          )}
        </div>
      )}

      {/* ── Morning briefing ─────────────────────────────────────────────── */}
      <BriefingTile />

      {/* ── Agent fleet ─────────────────────────────────────────────────────── */}
      <AgentFleet tasks={tasks} recentEvents={recentEvents} />

      {/* ── Live activity + system health ───────────────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 300px",
          gap: 12,
          minHeight: 280,
        } as CSSProperties}
      >
        {/* Activity feed */}
        <Panel
          title="LIVE ACTIVITY"
          leading={<Dot kind="ok" pulse />}
          trailing={
            <span style={{ fontSize: 9, color: "var(--ops-fg-dim)", letterSpacing: "0.1em" } as CSSProperties}>
              STREAMING · TAIL=30
            </span>
          }
          flushBody
        >
          <ActivityFeed events={recentEvents} />
        </Panel>

        {/* System health */}
        <Panel title="SYSTEM HEALTH" leading={<Dot kind="ok" pulse />}>
          <KV label="DAEMON">{daemonRunning ? "RUNNING" : "STOPPED"}</KV>
          <KV label="ACTIVE TASKS" accent="var(--ops-info)">{String(stats?.inProgressTasks ?? 0)}</KV>
          <KV label="DONE / SESSION">{String(stats?.doneTasks ?? 0)}</KV>
          <KV label="PROJECTS">{String(stats?.activeProjects ?? 0)}</KV>
          <KV label="DECISIONS" accent={pendingDecisions.length > 0 ? "var(--ops-amber)" : undefined}>
            {String(pendingDecisions.length)} PENDING
          </KV>
          {todayCost != null && (
            <KV label="COST / TODAY" accent="var(--ops-amber)">${todayCost.toFixed(2)}</KV>
          )}
        </Panel>
      </div>

      {/* ── Preserved sections: missions, comms, brain dump ─────────────────── */}
      <PreservedSections
        tasks={tasks}
        projects={projects}
        goals={goals}
        pendingDecisions={pendingDecisions}
        unreadMessages={unreadMessages}
      />

      <CreateTaskDialog
        open={showCreateTask}
        onOpenChange={setShowCreateTask}
        projects={projects}
        goals={goals}
        onSubmit={handleCreateTask}
      />
      <CreateProjectDialog
        open={showCreateProject}
        onOpenChange={setShowCreateProject}
        onSubmit={handleCreateProject}
      />
    </div>
  );
}

// ─── Hero stat ───────────────────────────────────────────────────────────────

function HeroStat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: 9,
          letterSpacing: "0.16em",
          color: "var(--ops-fg-dim)",
          fontFamily: "var(--ops-mono)",
          marginBottom: 3,
        } as CSSProperties}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 22,
          fontWeight: 500,
          fontVariantNumeric: "tabular-nums",
          fontFamily: "var(--ops-mono)",
          color: accent ?? "var(--ops-fg)",
        } as CSSProperties}
      >
        {value}
      </div>
    </div>
  );
}

// ─── Agent fleet ─────────────────────────────────────────────────────────────

function AgentFleet({ tasks, recentEvents }: { tasks: Task[]; recentEvents: ActivityEvent[] }) {
  const agentBars = useMemo(
    () => Object.fromEntries(
      SUBSYSTEM_AGENTS.map((id) => [id, buildAgentBars(id, recentEvents)]),
    ),
    [recentEvents],
  );

  return (
    <div>
      <SubH trailing={
        <span className="ops-faint" style={{ fontSize: 9, letterSpacing: "0.14em" } as CSSProperties}>
          SUB-AGENT FLEET · {SUBSYSTEM_AGENTS.length}
        </span>
      }>
        AGENT FLEET
      </SubH>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 10,
        } as CSSProperties}
      >
        {SUBSYSTEM_AGENTS.map((id) => {
          const identity = getAgentIdentity(id);
          if (!identity) return null;
          const agentTasks = tasks.filter((t) => t.assignedTo === id && t.kanban !== "done");
          const href = id === "atlas" ? "/atlas" : `/team/${id}`;
          return (
            <AgentCard
              key={id}
              identity={identity}
              taskCount={agentTasks.length}
              currentTask={agentTasks.find((t) => t.kanban === "in-progress")?.title}
              href={href}
              bars={agentBars[id] ?? null}
            />
          );
        })}
      </div>
    </div>
  );
}

// ─── Agent card ──────────────────────────────────────────────────────────────

/**
 * Build a 12-bucket activity histogram for an agent over the last 24h.
 * Each bucket = 2h window. Returns null when there are no events at all
 * (caller omits the sparkline rather than showing fake data).
 */
function buildAgentBars(agentId: string, events: ActivityEvent[]): number[] | null {
  const now = Date.now();
  const windowMs = 24 * 60 * 60 * 1000;
  const buckets = 12;
  const bucketMs = windowMs / buckets;

  const counts = new Array<number>(buckets).fill(0);
  let total = 0;
  for (const evt of events) {
    if (evt.actor !== agentId) continue;
    const age = now - new Date(evt.timestamp).getTime();
    if (age < 0 || age >= windowMs) continue;
    const idx = Math.min(buckets - 1, Math.floor(age / bucketMs));
    // Reverse: idx 0 = oldest, idx 11 = newest
    counts[buckets - 1 - idx] += 1;
    total += 1;
  }
  if (total === 0) return null;
  // Normalize to 2–32 range for Bars height
  const max = Math.max(...counts, 1);
  return counts.map((c) => 2 + (c / max) * 30);
}

interface AgentCardProps {
  identity: NonNullable<ReturnType<typeof getAgentIdentity>>;
  taskCount: number;
  currentTask?: string;
  href: string;
  bars: number[] | null;
}

function AgentCard({ identity, taskCount, currentTask, href, bars }: AgentCardProps) {
  const [hovered, setHovered] = useState(false);

  return (
    <Link href={href} style={{ textDecoration: "none" }}>
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          background: "var(--ops-bg-panel)",
          border: `1px solid ${hovered ? identity.colorHex : "var(--ops-line)"}`,
          borderRadius: 2,
          padding: 12,
          position: "relative",
          cursor: "pointer",
          transition: "border-color 120ms",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        } as CSSProperties}
      >
        {/* corner accent */}
        <span
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            width: 24,
            height: 1,
            background: identity.colorHex,
            opacity: 0.5,
          } as CSSProperties}
        />
        <span
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            width: 1,
            height: 24,
            background: identity.colorHex,
            opacity: 0.5,
          } as CSSProperties}
        />

        {/* header */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 } as CSSProperties}>
          <AgentGlyph agent={identity} size={28} />
          <div style={{ flex: 1, minWidth: 0 } as CSSProperties}>
            <div
              style={{
                fontFamily: "var(--ops-sans)",
                fontSize: 13,
                fontWeight: 600,
                letterSpacing: "0.06em",
              } as CSSProperties}
            >
              {identity.name}
            </div>
            <div
              style={{
                fontSize: 9,
                letterSpacing: "0.18em",
                color: "var(--ops-fg-dim)",
                fontFamily: "var(--ops-mono)",
              } as CSSProperties}
            >
              {identity.role}
            </div>
          </div>
          <Dot kind={taskCount > 0 ? "ok" : "idle"} pulse={taskCount > 0} />
        </div>

        <div
          style={{
            fontSize: 10,
            color: "var(--ops-fg-mute)",
            minHeight: 16,
            fontFamily: "var(--ops-sans)",
          } as CSSProperties}
        >
          {currentTask ? (
            <span style={{ color: identity.colorHex } as CSSProperties}>▸ {currentTask}</span>
          ) : (
            identity.tagline
          )}
        </div>

        {bars !== null && (
          <Bars values={bars} color={identity.colorHex} height={24} />
        )}

        {/* metrics row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 4,
            paddingTop: 6,
            borderTop: "1px solid var(--ops-line)",
          } as CSSProperties}
        >
          <MiniMetric label="QUEUE" value={String(taskCount)} />
          <MiniMetric label="MODEL" value={identity.model.includes("opus") ? "opus" : identity.model.includes("sonnet") ? "sonnet" : "haiku"} />
        </div>
      </div>
    </Link>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: 8,
          letterSpacing: "0.14em",
          color: "var(--ops-fg-faint)",
          fontFamily: "var(--ops-mono)",
        } as CSSProperties}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 12,
          fontFamily: "var(--ops-mono)",
          fontVariantNumeric: "tabular-nums",
        } as CSSProperties}
      >
        {value}
      </div>
    </div>
  );
}

// ─── Activity feed ───────────────────────────────────────────────────────────

function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  if (events.length === 0) {
    return (
      <div
        style={{
          padding: "20px 14px",
          fontSize: 10,
          color: "var(--ops-fg-faint)",
          fontFamily: "var(--ops-mono)",
          letterSpacing: "0.1em",
          textAlign: "center",
        } as CSSProperties}
      >
        — NO RECENT ACTIVITY —
      </div>
    );
  }
  return (
    <div
      style={{
        fontFamily: "var(--ops-mono)",
        fontSize: 11,
        lineHeight: 1.7,
        padding: "6px 14px",
      } as CSSProperties}
    >
      {events.slice(0, 30).map((row, i) => {
        const identity = getAgentIdentity(row.actor);
        return (
          <div
            key={row.id}
            style={{
              display: "grid",
              gridTemplateColumns: "76px 88px 1fr 60px",
              gap: 10,
              padding: "2px 0",
              borderBottom: "1px dashed var(--ops-line-faint)",
              opacity: 1 - i * 0.015,
            } as CSSProperties}
          >
            <span style={{ color: "var(--ops-fg-faint)" } as CSSProperties}>
              {new Date(row.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <span
              style={{
                color: identity ? identity.colorHex : "var(--ops-amber)",
                textTransform: "uppercase",
                fontSize: 10,
                letterSpacing: "0.1em",
              } as CSSProperties}
            >
              {row.actor}
            </span>
            <span style={{ color: "var(--ops-fg-mute)" } as CSSProperties}>{row.summary}</span>
            <span style={{ color: "var(--ops-fg-faint)", textAlign: "right" } as CSSProperties}>
              {formatRelativeTime(row.timestamp)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Preserved sections ───────────────────────────────────────────────────────

interface PreservedSectionsProps {
  tasks: Task[];
  projects: Project[];
  goals: Goal[];
  pendingDecisions: DecisionItem[];
  unreadMessages: InboxMessage[];
}

function PreservedSections({ tasks, projects, pendingDecisions, unreadMessages }: PreservedSectionsProps) {
  const activeProjects = projects.filter((p) => p.status === "active");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 } as CSSProperties}>
      {/* Missions */}
      {activeProjects.length > 0 && (
        <div>
          <SubH trailing={
            <Link href="/projects" style={{ textDecoration: "none" }}>
              <span style={{ fontSize: 9, color: "var(--ops-fg-faint)", fontFamily: "var(--ops-mono)", letterSpacing: "0.1em" } as CSSProperties}>VIEW ALL →</span>
            </Link>
          }>
            MISSIONS
          </SubH>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 } as CSSProperties}>
            {activeProjects.slice(0, 6).map((proj) => {
              const projTasks = tasks.filter((t) => t.projectId === proj.id);
              const done = projTasks.filter((t) => t.kanban === "done").length;
              return (
                <Link key={proj.id} href={`/projects/${proj.id}`} style={{ textDecoration: "none" }}>
                  <div
                    style={{
                      background: "var(--ops-bg-panel)",
                      border: "1px solid var(--ops-line)",
                      padding: "10px 12px",
                      borderRadius: 2,
                      cursor: "pointer",
                    } as CSSProperties}
                  >
                    <div style={{ fontSize: 12, fontFamily: "var(--ops-sans)", fontWeight: 600, marginBottom: 4 } as CSSProperties}>
                      {proj.name}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)" } as CSSProperties}>
                      {done}/{projTasks.length} tasks done
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Comms row */}
      {(pendingDecisions.length > 0 || unreadMessages.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 } as CSSProperties}>
          <Link href="/inbox" style={{ textDecoration: "none" }}>
            <Panel title="INBOX" trailing={unreadMessages.length > 0 ? <Tag kind="info">{unreadMessages.length} UNREAD</Tag> : undefined}>
              <span style={{ fontSize: 10, color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)" } as CSSProperties}>
                {unreadMessages.length === 0 ? "— all clear —" : `${unreadMessages.length} message${unreadMessages.length !== 1 ? "s" : ""} waiting`}
              </span>
            </Panel>
          </Link>
          <Link href="/decisions" style={{ textDecoration: "none" }}>
            <Panel title="DECISIONS" trailing={pendingDecisions.length > 0 ? <Tag kind="amber">{pendingDecisions.length} PENDING</Tag> : undefined}>
              <span style={{ fontSize: 10, color: "var(--ops-fg-dim)", fontFamily: "var(--ops-mono)" } as CSSProperties}>
                {pendingDecisions.length === 0 ? "— none pending —" : `${pendingDecisions.length} decision${pendingDecisions.length !== 1 ? "s" : ""} need input`}
              </span>
            </Panel>
          </Link>
        </div>
      )}
    </div>
  );
}

// ─── Morning Briefing tile ────────────────────────────────────────────────────

interface BriefingData {
  markdown: string;
  sections: {
    tempo?: { unread_action: number; top: { subject: string; from?: string }[]; due_today: number; overdue: number };
    scholar?: { next_exam?: { course: string; in_hours: number } | null; weak_top3?: string[]; review_depth?: number };
    atlas?: { pnl_today_usd: number; positions: number; mock?: boolean };
    system?: { dead_letters_24h: number; dispatches_24h: number; cost_today: number };
  };
  metadata: { generated_iso: string; duration_ms: number };
}

function BriefingTile() {
  const [data, setData] = useState<BriefingData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const base = process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765";
        const res = await fetch(`${base}/api/briefing`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body: { data: BriefingData; error: string | null } = await res.json();
        if (!cancelled) {
          if (body.error) setError(body.error);
          else setData(body.data);
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "fetch failed");
      }
    };
    load();
    const id = setInterval(load, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (error) return null;
  if (!data) {
    return (
      <Panel title="MORNING BRIEFING" leading={<Dot kind="info" pulse />}>
        <span style={{ fontSize: 10, color: "var(--ops-fg-dim)" } as CSSProperties}>LOADING…</span>
      </Panel>
    );
  }

  const lines = data.markdown.split("\n");
  const glanceLine = lines.find((l) => l.includes("Today at a glance:"));
  const glance = glanceLine?.replace(/\*\*Today at a glance:\*\*\s*/, "") ?? "";

  return (
    <Panel
      title="MORNING BRIEFING"
      leading={<Dot kind="ok" pulse />}
      trailing={
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{
            fontSize: 10,
            color: "var(--ops-amber)",
            background: "transparent",
            border: "1px solid var(--ops-line-strong)",
            padding: "2px 8px",
            borderRadius: 2,
            letterSpacing: "0.1em",
            cursor: "pointer",
          } as CSSProperties}
        >
          {expanded ? "COLLAPSE" : "EXPAND"}
        </button>
      }
    >
      <div
        style={{
          fontSize: 13,
          color: "var(--ops-amber)",
          letterSpacing: "0.04em",
          marginBottom: expanded ? 12 : 0,
        } as CSSProperties}
      >
        {glance || "no signal"}
      </div>
      {expanded && (
        <pre
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg-mute)",
            whiteSpace: "pre-wrap",
            margin: 0,
            maxHeight: 400,
            overflow: "auto",
          } as CSSProperties}
        >
          {data.markdown}
        </pre>
      )}
    </Panel>
  );
}
