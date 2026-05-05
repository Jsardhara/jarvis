import { NextRequest, NextResponse } from "next/server";
import { backendBaseUrl, backendHeaders } from "@/lib/jarvis-backend";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const res = await fetch(`${backendBaseUrl()}/api/scholar/documents/${id}/flashcards`, {
      cache: "no-store",
      headers: backendHeaders(),
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const res = await fetch(`${backendBaseUrl()}/api/scholar/documents/${id}/flashcards`, {
      method: "POST",
      cache: "no-store",
      headers: backendHeaders(),
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
