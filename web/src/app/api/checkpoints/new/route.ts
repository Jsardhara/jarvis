import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { z } from "zod";
import {
  saveTasks,
  saveGoals,
  saveProjects,
  saveBrainDump,
  saveInbox,
  saveDecisions,
  saveAgents,
  saveSkillsLibrary,
  saveActivityLog,
  mutateActivityLog,
} from "@/lib/data";
import type { ActivityEvent } from "@/lib/types";

const newCheckpointSchema = z.object({
  // Required explicit acknowledgement that nine state files will be wiped.
  confirm: z.literal(true),
  // Optional label written to the activity log for audit.
  label: z.string().min(1).max(120).optional(),
});

type NewCheckpointBody = z.infer<typeof newCheckpointSchema>;

// Default agents for a fresh workspace — the locked-five Jarvis runtime
// agents from CLAUDE.md plus "me" for operator-owned tasks. These IDs match
// `build_default_registry()` in jarvis/agents/registry.py so dispatch from
// the dashboard reaches the same agents the API serves.
const DEFAULT_AGENTS = [
  {
    id: "tempo",
    name: "Tempo",
    icon: "Mail",
    description: "Outlook + iCloud — mail, calendar, tasks",
    instructions: "",
    capabilities: ["mail", "calendar", "tasks", "scheduling"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "scholar",
    name: "Scholar",
    icon: "GraduationCap",
    description: "Academics + study planning",
    instructions: "",
    capabilities: ["assignments", "study-plans", "summarization"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "lens",
    name: "Lens",
    icon: "Search",
    description: "Web research + monitoring",
    instructions: "",
    capabilities: ["web-research", "news", "watchlist", "summarization"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "forge",
    name: "Forge",
    icon: "Code",
    description: "Code-work delegation",
    instructions: "",
    capabilities: ["coding", "testing", "github", "scaffolding"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "atlas",
    name: "Atlas",
    icon: "BarChart3",
    description: "Trading orchestrator",
    instructions: "",
    capabilities: ["portfolio", "strategy", "backtest", "execution"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "me",
    name: "Me",
    icon: "User",
    description: "Tasks I handle myself — decisions, approvals, creative direction",
    instructions: "",
    capabilities: ["decisions", "approvals", "creative-direction"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
];

// POST /api/checkpoints/new — Create a fresh empty workspace.
//
// DESTRUCTIVE: resets nine state files to empty. Per CLAUDE.md confirmation
// policy this must be explicit — callers MUST send `{ confirm: true }` in the
// body. Missing/false confirm returns 400 with no side effects.
//
// The previous version of this endpoint accepted POST with no body and ran
// `exec("pnpm gen:context")` afterward — an RCE pivot when combined with an
// unauthenticated middleware. Both are removed here.
export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: NewCheckpointBody;
  try {
    const raw: unknown = await request.json();
    body = newCheckpointSchema.parse(raw);
  } catch (err) {
    return NextResponse.json(
      {
        error: "Confirmation required",
        details:
          "POST /api/checkpoints/new wipes tasks, goals, projects, brain-dump, inbox, decisions, agents, skills, and activity-log. Send `{ confirm: true }` to proceed.",
        cause: err instanceof Error ? err.message : String(err),
      },
      { status: 400 }
    );
  }

  try {
    await saveTasks({ tasks: [] });
    await saveGoals({ goals: [] });
    await saveProjects({ projects: [] });
    await saveBrainDump({ entries: [] });
    await saveInbox({ messages: [] });
    await saveDecisions({ decisions: [] });
    await saveAgents({ agents: DEFAULT_AGENTS });
    await saveSkillsLibrary({ skills: [] });
    await saveActivityLog({ events: [] });

    // Audit trail: log that a wipe happened so the operator can trace it.
    const auditEvent: ActivityEvent = {
      id: `checkpoint-new-${Date.now()}`,
      type: "milestone_completed",
      actor: "system",
      taskId: null,
      summary: `Workspace reset: ${body.label ?? "fresh workspace"}`,
      details:
        "POST /api/checkpoints/new cleared tasks, goals, projects, brain-dump, inbox, decisions, agents, skills, and activity-log.",
      timestamp: new Date().toISOString(),
    };
    await mutateActivityLog(async (data) => {
      data.events = [auditEvent];
      return data;
    });

    return NextResponse.json({ ok: true, label: body.label ?? null });
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to create new workspace", details: String(err) },
      { status: 500 }
    );
  }
}
