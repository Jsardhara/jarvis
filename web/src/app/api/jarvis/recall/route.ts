import { proxyToBackend } from "@/lib/jarvis-backend";

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();
  return proxyToBackend("/api/jarvis/recall", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
