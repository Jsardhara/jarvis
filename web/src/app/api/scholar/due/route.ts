import { NextResponse } from "next/server";

const BACKEND = process.env.JARVIS_API_URL ?? "http://localhost:8001";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/api/scholar/due`, { cache: "no-store" });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
