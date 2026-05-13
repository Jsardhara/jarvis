import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Constant-time string comparison using XOR.
 * Prevents timing side-channel attacks on token comparison.
 */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

/**
 * Hostnames considered loopback. The Next dev server reports these via the
 * `host` header for requests from the same machine.
 */
const LOOPBACK_HOSTS = new Set([
  "localhost",
  "127.0.0.1",
  "[::1]",
  "::1",
]);

function isLoopbackRequest(request: NextRequest): boolean {
  const host = request.headers.get("host") ?? "";
  // host may include a port: "localhost:3000" → "localhost"
  const hostname = host.split(":")[0]?.toLowerCase() ?? "";
  if (LOOPBACK_HOSTS.has(hostname)) return true;
  // x-forwarded-for is the proxy hint; trust only if loopback already.
  return false;
}

/**
 * Destructive HTTP methods. When `MC_API_TOKEN` is unset we still allow
 * loopback callers (the operator's own browser on localhost) to hit these,
 * but block any LAN/remote caller. Read-only methods (GET, HEAD, OPTIONS)
 * stay open in unconfigured mode for backwards compatibility with `dev:lan`.
 */
const DESTRUCTIVE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * API Authentication Middleware
 *
 * Precedence:
 *   1. If `MC_API_TOKEN` is set, every /api/* request requires a matching
 *      `Authorization: Bearer <token>` header.
 *   2. If `MC_API_TOKEN` is NOT set:
 *        - Loopback callers pass through (single-operator localhost dev).
 *        - Read-only methods from any origin pass through.
 *        - Destructive methods (POST/PUT/PATCH/DELETE) from non-loopback
 *          origins are blocked with 401 — `dev:lan` cannot be hijacked.
 */
export function middleware(request: NextRequest): NextResponse {
  const token = process.env.MC_API_TOKEN;

  if (!token) {
    // Unconfigured mode: tighten only for destructive verbs over LAN.
    if (
      DESTRUCTIVE_METHODS.has(request.method) &&
      !isLoopbackRequest(request)
    ) {
      return NextResponse.json(
        {
          error: "Destructive request blocked",
          details:
            "MC_API_TOKEN is not configured. Set it in .env.local to allow non-loopback callers to perform writes.",
        },
        { status: 401 }
      );
    }
    return NextResponse.next();
  }

  const authHeader = request.headers.get("authorization");
  if (!authHeader) {
    return NextResponse.json(
      { error: "Missing Authorization header" },
      { status: 401 }
    );
  }

  // Expect "Bearer <token>"
  const parts = authHeader.split(" ");
  if (parts.length !== 2 || parts[0] !== "Bearer" || parts[1] === undefined) {
    return NextResponse.json(
      { error: "Invalid Authorization format. Expected: Bearer <token>" },
      { status: 401 }
    );
  }

  if (!timingSafeEqual(parts[1], token)) {
    return NextResponse.json(
      { error: "Invalid API token" },
      { status: 401 }
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/api/:path*",
};
