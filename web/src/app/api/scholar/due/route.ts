import { NextResponse } from "next/server";
import { backendBaseUrl, backendHeaders } from "@/lib/jarvis-backend";

export async function GET() {
  try {
    const res = await fetch(`${backendBaseUrl()}/api/scholar/due`, {
      cache: "no-store",
      headers: backendHeaders(),
    });
    const data: unknown = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
