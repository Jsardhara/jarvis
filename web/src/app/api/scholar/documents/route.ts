import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.JARVIS_API_URL ?? "http://localhost:8001";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/api/scholar/documents`, { cache: "no-store" });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.formData();
    const res = await fetch(`${BACKEND}/api/scholar/documents`, {
      method: "POST",
      body,
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
