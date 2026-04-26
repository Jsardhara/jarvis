"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { useWs } from "@/lib/ws";

export function StatusBar() {
  const ws = useWs();
  const [now, setNow] = useState<string>(() => new Date().toLocaleTimeString());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(id);
  }, []);

  const { data: health } = useSWR<{ ok: boolean; service: string }>(
    "/api/health",
    fetcher,
    { refreshInterval: 5000 }
  );

  return (
    <div className="mc-statusbar">
      <span className="brand-mc">JARVIS // MISSION CONTROL</span>
      <span className="sb-pill">
        <span className="dot" data-status={health?.ok ? "done" : "error"} />
        api {health?.ok ? "live" : "down"}
      </span>
      <span className="sb-pill">
        <span className="dot" data-status={ws.status === "connected" ? "done" : ws.status === "connecting" ? "running" : "error"} />
        ws {ws.status}
      </span>
      <span className="sb-spacer" />
      <span className="sb-pill">{now}</span>
    </div>
  );
}
