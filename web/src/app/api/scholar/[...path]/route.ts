import { proxyToBackend } from "@/lib/jarvis-backend";

/**
 * Catch-all proxy for any /api/scholar/* path that doesn't have a dedicated
 * Next.js route file. More specific route files (documents/, due/, etc.) win
 * over this catch-all by Next's routing precedence.
 */
async function forward(request: Request, path: string[]): Promise<Response> {
  const url = new URL(request.url);
  const target = `/api/scholar/${path.join("/")}${url.search}`;
  const init: RequestInit = { method: request.method };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
    init.headers = { "Content-Type": request.headers.get("content-type") ?? "application/json" };
  }
  return proxyToBackend(target, init);
}

export async function GET(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(request, path);
}

export async function POST(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(request, path);
}

export async function PUT(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(request, path);
}

export async function DELETE(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(request, path);
}
