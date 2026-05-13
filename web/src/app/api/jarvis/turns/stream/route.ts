import { proxyToBackend } from "@/lib/jarvis-backend";

/**
 * Streams the FastAPI /api/jarvis/turns/stream SSE channel straight
 * through to the browser. Used by useChatTurns to receive push events
 * whenever any process (voice daemon, chat HTTP, terminal) appends a
 * turn to chat_turns.jsonl.
 */
export async function GET(): Promise<Response> {
  return proxyToBackend("/api/jarvis/turns/stream", { method: "GET" });
}
