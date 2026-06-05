import { proxyToBackend } from "@/lib/jarvis-backend";

interface Params {
  params: Promise<{ id: string }>;
}

export async function POST(_request: Request, { params }: Params): Promise<Response> {
  const { id } = await params;
  return proxyToBackend(`/api/confirmations/${encodeURIComponent(id)}/reject`, {
    method: "POST",
  });
}
