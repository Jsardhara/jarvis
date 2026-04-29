import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.JARVIS_API_URL ?? "http://localhost:8001";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const body: unknown = await req.json();
    const res = await fetch(`${BACKEND}/api/scholar/flashcards/${id}/rate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
