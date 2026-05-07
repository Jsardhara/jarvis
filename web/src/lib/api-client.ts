/**
 * Authenticated API client for Mission Control.
 *
 * Wraps fetch() with:
 * - Automatic Bearer token injection (NEXT_PUBLIC_MC_API_TOKEN)
 * - Retry with exponential backoff for network errors and 5xx responses
 * - Configurable retry behavior per request
 */

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Extended RequestInit with retry options. */
export interface ApiFetchInit extends RequestInit {
  /** Max retries on network error or 5xx (default: 2 for GET, 0 for mutations). */
  retries?: number;
  /** Base delay in ms before first retry (doubles each attempt, default: 500). */
  retryDelay?: number;
}

/**
 * Fetch wrapper with auth + automatic retry for transient failures.
 *
 * - GET requests retry up to 2 times by default (safe to retry reads).
 * - POST/PUT/DELETE default to 0 retries (mutations need explicit opt-in).
 * - Retries only on network errors and 5xx responses (never on 4xx).
 */
const TOKEN_STORAGE_KEY = "jarvis-token";

/** Read API token. Browser-stored localStorage value wins over build-time env. */
export function getApiToken(): string | null {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    if (stored) return stored;
  }
  return process.env.NEXT_PUBLIC_MC_API_TOKEN ?? null;
}

export function setApiToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearApiToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export async function apiFetch(url: string, init?: ApiFetchInit): Promise<Response> {
  const token = getApiToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const method = (init?.method ?? "GET").toUpperCase();
  const isMutation = method !== "GET" && method !== "HEAD";
  const maxRetries = init?.retries ?? (isMutation ? 0 : 2);
  const baseDelay = init?.retryDelay ?? 500;

  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await fetch(url, { ...init, headers });

      // Only retry on 5xx (server error), never on 4xx (client error)
      if (res.status >= 500 && attempt < maxRetries) {
        await sleep(baseDelay * Math.pow(2, attempt));
        continue;
      }

      return res;
    } catch (err) {
      // Network error (server unreachable, DNS failure, CORS, etc.)
      lastError = err;
      if (attempt < maxRetries) {
        await sleep(baseDelay * Math.pow(2, attempt));
        continue;
      }
    }
  }

  // All retries exhausted — throw the last error
  throw lastError;
}
