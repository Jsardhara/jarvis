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
