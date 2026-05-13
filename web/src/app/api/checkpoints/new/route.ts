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

// Default agents for a fresh workspace (the 5 built-in roles)
const DEFAULT_AGENTS = [
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
  {
    id: "researcher",
    name: "Researcher",
    icon: "Search",
    description: "Market research, competitive analysis, evaluation",
    instructions: "",
    capabilities: ["web-research", "analysis", "evaluation"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "developer",
    name: "Developer",
    icon: "Code",
    description: "Code, bug fixes, testing, deployment",
    instructions: "",
    capabilities: ["coding", "testing", "debugging", "deployment"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "marketer",
    name: "Marketer",
    icon: "Megaphone",
    description: "Copy, growth strategy, content, SEO",
    instructions: "",
    capabilities: ["copywriting", "seo", "content-strategy", "growth"],
    skillIds: [],
    status: "active" as const,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "business-analyst",
    name: "Business Analyst",
    icon: "BarChart3",
    description: "Strategy, planning, prioritization, financials",
    instructions: "",
    capabilities: ["strategy", "analysis", "planning", "financial-modeling"],
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
