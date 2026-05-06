import { proxyToBackend } from "@/lib/jarvis-backend";

export async function GET(): Promise<Response> {
  return proxyToBackend("/api/watchlist", { method: "GET" });
}

export async function PUT(request: Request): Promise<Response> {
  const body = await request.text();
  return proxyToBackend("/api/watchlist", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
