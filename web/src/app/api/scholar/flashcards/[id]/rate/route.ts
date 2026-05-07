import { NextRequest, NextResponse } from "next/server";
import { backendBaseUrl, backendHeaders } from "@/lib/jarvis-backend";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const body: unknown = await req.json();
    const headers = backendHeaders();
    headers.set("Content-Type", "application/json");
    const res = await fetch(`${backendBaseUrl()}/api/scholar/flashcards/${id}/rate`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
