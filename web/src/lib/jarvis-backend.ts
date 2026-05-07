/**
 * Server-side helper for proxying Next.js API routes to the Jarvis FastAPI
 * backend (default `http://localhost:8765`). Adds the bearer token from env
 * on every outbound request so FastAPI's auth middleware accepts it.
 */

const DEFAULT_BACKEND = "http://localhost:8765";

export function backendBaseUrl(): string {
  return process.env.JARVIS_API_URL ?? DEFAULT_BACKEND;
}

function backendToken(): string | null {
  return (
    process.env.JARVIS_API_TOKEN ??
    process.env.MC_API_TOKEN ??
    null
  );
}

/**
 * Build headers for a backend call, forwarding caller-supplied headers and
 * adding the bearer token. The caller's Authorization header is overridden
 * because Next.js middleware already verified it; we use the trusted backend
 * token internally.
 */
export function backendHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  headers.delete("authorization");
  const token = backendToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

/**
 * Proxy a request to the FastAPI backend. Streams the response back as-is
 * so streaming endpoints (e.g. /api/jarvis/chat) work transparently.
 */
export async function proxyToBackend(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const url = `${backendBaseUrl()}${path}`;
  const headers = backendHeaders(init?.headers);
  const upstream = await fetch(url, { ...init, headers });
  // Pass status, headers (minus hop-by-hop), and body straight through.
  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete("transfer-encoding");
  respHeaders.delete("content-encoding");
  respHeaders.delete("connection");
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: respHeaders,
  });
}
