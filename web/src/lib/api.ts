/** Tiny fetch helpers for the Jarvis API at /api/*. */
export type InboxEvent = {
  ts: string;
  agent: string;
  severity: "info" | "warn" | "alert";
  summary: string;
  ref: Record<string, unknown>;
};

export type Task = {
  id: string;
  title: string;
  due: string | null;
  tags: string[];
  status: "open" | "done" | "cancelled";
  created: string;
  updated: string;
};

export type DispatchResponse = {
  intent: { primary: string; confidence: number; rationale: string; parallel: string[] };
  context: { inbox: InboxEvent[]; tasks: Task[] };
  responses: Record<
    string,
    {
      agent: string;
      intent: string;
      action: string;
      result: Record<string, unknown>;
      follow_ups: string[];
      confidence: number;
      needs_confirm: boolean;
    }
  >;
  needs_confirm: boolean;
};

const ok = async <T>(res: Response): Promise<T> => {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
};

export const fetcher = <T>(url: string): Promise<T> => fetch(url).then((r) => ok<T>(r));

export async function dispatch(request: string): Promise<DispatchResponse> {
  const r = await fetch("/api/dispatch", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ request }),
  });
  return ok<DispatchResponse>(r);
}

export async function createTask(title: string, tags: string[] = []): Promise<Task> {
  const r = await fetch("/api/tasks", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title, tags }),
  });
  return ok<Task>(r);
}

export async function patchTask(id: string, fields: Partial<Task>): Promise<Task> {
  const r = await fetch(`/api/tasks/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(fields),
  });
  return ok<Task>(r);
}

// ─── Mission control: agents + history + confirmations ───

export type VerificationDict = {
  status: "verified" | "inference" | "unknown" | "post_state_checked";
  evidence?: string;
  checked_at?: string;
};

export type AgentResponseEnvelope = {
  agent: string;
  intent: string;
  action: string;
  result: Record<string, unknown>;
  follow_ups: string[];
  confidence: number;
  needs_confirm: boolean;
  request_id: string;
  ts: string;
  /** Tier 1-5; default 5 until back ships classify.py */
  tier?: number;
  /** Verification status; default {status:"unknown"} until back ships verify.py */
  verification?: VerificationDict;
};

export type AgentDescriptor = {
  name: string;
  description: string;
  actions: string[];
};

export type AgentLogEntry = {
  ts: string;
  request_id: string;
  agent: string;
  action: string;
  status: "ok" | "error" | "proposed";
  duration_ms: number;
  confidence: number;
  needs_confirm: boolean;
  summary: string;
  error: string | null;
};

export type Confirmation = {
  id: string;
  ts: string;
  agent: string;
  intent: string;
  args: Record<string, unknown>;
  summary: string;
  status: "pending" | "approved" | "rejected";
  resolved_ts: string | null;
  resolved_result: Record<string, unknown> | null;
};

export type TraceEvent = {
  type:
    | "router.classified"
    | "agent.start"
    | "agent.done"
    | "agent.error"
    | "confirmation.created"
    | "confirmation.resolved"
    | "dispatch";
  request_id: string;
  ts: string;
  agent: string | null;
  payload: Record<string, unknown>;
};

export async function listAgents(): Promise<AgentDescriptor[]> {
  const r = await fetch("/api/agents");
  return (await ok<{ agents: AgentDescriptor[] }>(r)).agents;
}

export async function dispatchAgent(
  name: string,
  body: { action?: string; args?: Record<string, unknown>; text?: string }
): Promise<AgentResponseEnvelope> {
  const r = await fetch(`/api/agents/${name}/dispatch`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return ok<AgentResponseEnvelope>(r);
}

export async function agentHistory(name: string, limit = 20): Promise<AgentLogEntry[]> {
  const r = await fetch(`/api/agents/${name}/history?limit=${limit}`);
  return (await ok<{ entries: AgentLogEntry[] }>(r)).entries;
}

export async function listConfirmations(status: "pending" | "approved" | "rejected" = "pending"): Promise<Confirmation[]> {
  const r = await fetch(`/api/confirmations?status=${status}`);
  return (await ok<{ confirmations: Confirmation[] }>(r)).confirmations;
}

export async function approveConfirmation(id: string): Promise<Confirmation> {
  const r = await fetch(`/api/confirmations/${id}/approve`, { method: "POST" });
  return ok<Confirmation>(r);
}

export async function rejectConfirmation(id: string): Promise<Confirmation> {
  const r = await fetch(`/api/confirmations/${id}/reject`, { method: "POST" });
  return ok<Confirmation>(r);
}
