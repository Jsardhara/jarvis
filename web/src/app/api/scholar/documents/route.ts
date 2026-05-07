import { NextRequest, NextResponse } from "next/server";
import { backendBaseUrl, backendHeaders } from "@/lib/jarvis-backend";

export async function GET() {
  try {
    const res = await fetch(`${backendBaseUrl()}/api/scholar/documents`, {
      cache: "no-store",
      headers: backendHeaders(),
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.formData();
    const res = await fetch(`${backendBaseUrl()}/api/scholar/documents`, {
      method: "POST",
      body,
      headers: backendHeaders(),
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
