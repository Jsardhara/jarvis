/**
 * Bearer token validation endpoint.
 *
 * Middleware enforces auth on /api/*; this route just returns 200 if reached.
 * Phone clients call this on boot to verify their stored token is valid.
 */
export async function GET() {
  return Response.json({ ok: true });
}
