import { proxyToBackend } from "@/lib/jarvis-backend";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const qs = url.search;
  return proxyToBackend(`/api/jarvis/turns${qs}`, { method: "GET" });
}
