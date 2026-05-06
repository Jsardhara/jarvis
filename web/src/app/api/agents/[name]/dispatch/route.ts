import { proxyToBackend } from "@/lib/jarvis-backend";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ name: string }> },
): Promise<Response> {
  const { name } = await params;
  const body = await request.text();
  return proxyToBackend(`/api/agents/${encodeURIComponent(name)}/dispatch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
