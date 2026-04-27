"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { useWs } from "@/lib/ws";

type Theme = "dark" | "light";

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = localStorage.getItem("jarvis-theme") as Theme | null;
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function StatusBar() {
  const ws = useWs();
  const [now, setNow] = useState<string>(() => new Date().toLocaleTimeString());
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const t = getInitialTheme();
    setTheme(t);
    document.documentElement.dataset.theme = t;
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("jarvis-theme", next);
      return next;
    });
  };

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
      <span className="brand-mc">
        Jarvis{" "}
        <span className="brand-sub">// Mission Control</span>
      </span>
      <span className="sb-pill">
        <span className="dot" data-status={health?.ok ? "done" : "error"} />
        api {health?.ok ? "live" : "down"}
      </span>
      <span className="sb-pill">
        <span
          className="dot"
          data-status={
            ws.status === "connected"
              ? "done"
              : ws.status === "connecting"
              ? "running"
              : "error"
          }
        />
        ws {ws.status}
      </span>
      <span className="sb-spacer" />
      <span className="sb-pill">{now}</span>
      <button
        type="button"
        className="sb-theme-btn"
        onClick={toggleTheme}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      >
        {theme === "dark" ? "☀" : "☾"}
      </button>
    </div>
  );
}
