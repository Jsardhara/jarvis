"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Mission Control" },
  { href: "/briefing", label: "Briefing" },
  { href: "/inbox", label: "Inbox" },
  { href: "/tasks", label: "Tasks" },
  { href: "/atlas", label: "ATLAS" },
  { href: "/console", label: "Console" },
];

export function TopNav() {
  const pathname = usePathname();
  // Mission control is full-bleed; suppress the legacy nav there.
  if (pathname === "/") return null;
  return (
    <header className="topbar">
      <span className="brand">Jarvis</span>
      <nav>
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href}>
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
