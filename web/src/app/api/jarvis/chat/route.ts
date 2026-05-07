import { proxyToBackend } from "@/lib/jarvis-backend";

/**
 * Streams the FastAPI /api/jarvis/chat NDJSON / SSE response straight through
 * to the browser. proxyToBackend forwards upstream.body without buffering.
 */
export async function POST(request: Request): Promise<Response> {
  const body = await request.text();
  return proxyToBackend("/api/jarvis/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    // @ts-expect-error — Next.js fetch supports duplex but it's not in the lib types yet.
    duplex: "half",
  });
}
