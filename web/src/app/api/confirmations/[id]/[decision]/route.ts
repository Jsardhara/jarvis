import { proxyToBackend } from "@/lib/jarvis-backend";

interface Params {
  params: Promise<{ id: string; decision: string }>;
}

export async function POST(_request: Request, { params }: Params): Promise<Response> {
  const { id, decision } = await params;
  return proxyToBackend(`/api/confirmations/${encodeURIComponent(id)}/${encodeURIComponent(decision)}`, {
    method: "POST",
  });
}
