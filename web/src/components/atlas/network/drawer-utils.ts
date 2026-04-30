/**
 * Shared types and helpers for AgentInspectorDrawer.
 * Kept separate to keep the component file under 300 lines.
 */

export interface ActivityItem {
  id?: string;
  event_type: string;
  occurred_at?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
}

export interface AgentDetail {
  id?: string;
  display_name?: string;
  name?: string;
  model?: string;
  state?: string;
  agent_status?: string;
  last_heartbeat?: string;
  recent_activity?: ActivityItem[];
}

export interface MemoryEntry {
  key: string;
  value: unknown;
  updated_at?: string;
}

export interface DrawerData {
  detail: AgentDetail | null;
  memory: MemoryEntry[];
}

const FETCH_TIMEOUT_MS = 8_000;

export async function fetchWithTimeout(url: string): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    clearTimeout(timer);
    throw err;
  }
}

export function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

// Tag.tsx only accepts "default" | "amber" | "ok" | "crit" | "info"
export function stateColor(state: string | undefined): "ok" | "amber" | "crit" | undefined {
  if (!state) return undefined;
  const s = state.toLowerCase();
  if (s === "running" || s === "active" || s === "ok") return "ok";
  if (s === "paused" || s === "stale" || s === "warn") return "amber";
  if (s === "error" || s === "failed") return "crit";
  return undefined;
}

export function normalizeMemory(raw: unknown): MemoryEntry[] {
  if (Array.isArray(raw)) return raw as MemoryEntry[];
  const obj = raw as { memory?: MemoryEntry[] };
  return obj?.memory ?? [];
}
