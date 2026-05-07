"use client";

import { useEffect, useState } from "react";
import { Dot } from "./Dot";
import { Kbd } from "./Kbd";
import { useDaemon } from "@/hooks/use-daemon";
import { useRouter } from "next/navigation";

/** Client-only date string — avoids hydration mismatch on the statusbar. */
function LocalDate() {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    setLabel(
      new Date()
        .toLocaleDateString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
        })
        .toUpperCase()
    );
  }, []);

  if (!label) return <span style={{ opacity: 0 }}>---</span>;
  return <span>{label}</span>;
}

/** Format a next-run ISO string as HH:MM, or "--:--" if missing. */
function fmtNextRun(iso: string | undefined): string {
  if (!iso) return "--:--";
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  } catch {
    return "--:--";
  }
}

/**
 * Statusbar — 28px footer strip occupying grid-area "statusbar".
 *
 * Left items: JARVIS online, SENTINEL next-fire, CTX %, RPM
 * Right items: Kbd shortcuts + local date
 *
 * Daemon next-fire pulled from useDaemon().status.nextScheduledRuns.
 * CTX and RPM are mocked (38% / 12).
 */
export function Statusbar() {
  const { status } = useDaemon();
  const router = useRouter();

  // Pick the earliest next-fire time from the daemon's schedule map
  const nextRuns = Object.values(status.nextScheduledRuns);
  const nextFire =
    nextRuns.length > 0
      ? fmtNextRun(nextRuns.sort()[0])
      : "--:--";

  return (
    <footer className="ops-statusbar">
      {/* ── Left items ── */}
      <span className="flex items-center gap-1.5">
        <Dot kind="ok" pulse />
        <span>
          JARVIS · <b>ONLINE</b>
        </span>
      </span>

      <span>
        SENTINEL · NEXT FIRE <b>{nextFire}</b>
      </span>

      <span>
        CTX <b style={{ color: "var(--ops-fg-mute)" }}>38%</b>
      </span>

      <span>
        RPM <b style={{ color: "var(--ops-fg-mute)" }}>12</b>
      </span>

      {/* ── Spacer ── */}
      <span style={{ flex: 1 }} />

      {/* ── Right shortcuts ── */}
      <span className="flex items-center gap-1">
        <Kbd>⌘K</Kbd>
        <span>COMMAND</span>
      </span>

      <span
        className="flex items-center gap-1 cursor-pointer"
        onClick={() => router.push("/preferences")}
        title="Open preferences"
      >
        <Kbd>⌘\</Kbd>
        <span>TWEAKS</span>
      </span>

      <LocalDate />
    </footer>
  );
}
