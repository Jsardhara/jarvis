import { proxyToBackend } from "@/lib/jarvis-backend";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  return proxyToBackend(`/api/sentinel/snapshot${url.search}`, { method: "GET" });
}
