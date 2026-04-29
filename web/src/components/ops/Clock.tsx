"use client";

import { useEffect, useState } from "react";

const pad = (n: number) => String(n).padStart(2, "0");

/** Live HH:MM:SS UTC clock. Updates once per second. */
export function Clock() {
  const [t, setT] = useState<Date | null>(null);

  useEffect(() => {
    setT(new Date());
    const id = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!t) {
    // Avoid hydration mismatch — render placeholder until client mount.
    return <span className="ops-mono-num">--:--:-- UTC</span>;
  }

  return (
    <span className="ops-mono-num">
      {pad(t.getUTCHours())}:{pad(t.getUTCMinutes())}:{pad(t.getUTCSeconds())} UTC
    </span>
  );
}
