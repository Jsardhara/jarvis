"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";
import { Dot } from "@/components/ops/Dot";
import { AgentGlyph } from "@/components/ops/AgentGlyph";
import {
  AGENT_IDENTITIES,
  SUBSYSTEM_AGENTS,
} from "@/components/ops/agent-identity";

// ─── Nav data ────────────────────────────────────────────────────────────────

interface NavEntry {
  href: string;
  label: string;
  glyph: string;
  badgeKey?: "unreadInbox" | "pendingDecisions";
}

const CONTROL_LINKS: NavEntry[] = [
  { href: "/jarvis",       label: "Talk to Jarvis", glyph: "◉" },
  { href: "/",             label: "Command Center", glyph: "◇" },
  { href: "/status-board", label: "Status Board",   glyph: "▤" },
];

const COMMS_LINKS: NavEntry[] = [
  { href: "/inbox",     label: "Inbox",     glyph: "□", badgeKey: "unreadInbox" },
  { href: "/decisions", label: "Decisions", glyph: "?", badgeKey: "pendingDecisions" },
];

// ─── Component types ─────────────────────────────────────────────────────────

interface AppSidebarProps {
  /** When true the sidebar is rendered as a slide-in drawer (mobile). */
  collapsed: boolean;
  unreadInbox?: number;
  pendingDecisions?: number;
  isMobile?: boolean;
  onClose?: () => void;
}

type BadgeMap = { unreadInbox: number; pendingDecisions: number };

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

interface NavItemProps {
  href: string;
  label: string;
  glyph: string;
  active: boolean;
  badge?: number;
  onClick?: () => void;
}

function NavItem({ href, label, glyph, active, badge, onClick }: NavItemProps) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        "ops-nav-item",
        active && "ops-nav-item-active"
      )}
    >
      <span className="ops-nav-glyph">{glyph}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {badge != null && badge > 0 && (
        <span className="ops-nav-meta" style={{ color: "var(--ops-amber)" }}>
          {badge}
        </span>
      )}
    </Link>
  );
}

function NavSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="ops-nav-section">
      <div className="ops-nav-label">{label}</div>
      {children}
    </div>
  );
}

// ─── Sidebar footer ──────────────────────────────────────────────────────────

function SidebarFooter() {
  return (
    <div
      style={{
        marginTop: "auto",
        padding: "12px",
        borderTop: "1px solid var(--ops-line)",
        fontSize: 9,
        color: "var(--ops-fg-faint)",
        letterSpacing: "0.1em",
        lineHeight: 1.7,
        fontFamily: "var(--ops-mono)",
      }}
    >
      <div>v0.9 · build 001</div>
      <div>2d 14h 22m UPTIME</div>
      <div
        className="flex items-center gap-1"
        style={{ color: "var(--ops-ok)", marginTop: 4 }}
      >
        <Dot kind="ok" pulse />
        ALL SYSTEMS NOMINAL
      </div>
    </div>
  );
}

// ─── Agent rows ──────────────────────────────────────────────────────────────

interface AgentRowProps {
  agentId: typeof SUBSYSTEM_AGENTS[number];
  href: string;
  active: boolean;
  onClick?: () => void;
}

function AgentRow({ agentId, href, active, onClick }: AgentRowProps) {
  const identity = AGENT_IDENTITIES[agentId];
  const agentColorStyle = {
    "--agent-color": identity.colorHex,
  } as CSSProperties;

  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        "ops-nav-item ops-nav-item-agent",
        active && "ops-nav-item-active"
      )}
      style={agentColorStyle}
    >
      <AgentGlyph agent={identity} size={16} />
      <span style={{ flex: 1 }}>{identity.name}</span>
      <span className="ops-nav-meta">
        <Dot kind="ok" />
      </span>
    </Link>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function AppSidebar({
  collapsed,
  unreadInbox = 0,
  pendingDecisions = 0,
  isMobile = false,
  onClose,
}: AppSidebarProps) {
  const pathname = usePathname();
  const badges: BadgeMap = { unreadInbox, pendingDecisions };

  const sentinelIdentity = AGENT_IDENTITIES.sentinel;
  // /sentinel page not yet created — fall back to /atlas
  const sentinelHref = "/atlas";

  const sidebarContent = (
    <>
      {/* CONTROL */}
      <NavSection label="CONTROL">
        {CONTROL_LINKS.map((entry) => (
          <NavItem
            key={entry.href}
            href={entry.href}
            label={entry.label}
            glyph={entry.glyph}
            active={isActive(pathname, entry.href)}
            onClick={onClose}
          />
        ))}
      </NavSection>

      {/* COMMS */}
      <NavSection label="COMMS">
        {COMMS_LINKS.map((entry) => (
          <NavItem
            key={entry.href}
            href={entry.href}
            label={entry.label}
            glyph={entry.glyph}
            active={isActive(pathname, entry.href)}
            badge={entry.badgeKey ? badges[entry.badgeKey] : undefined}
            onClick={onClose}
          />
        ))}
      </NavSection>

      {/* SUB-AGENTS */}
      <NavSection label="SUB-AGENTS">
        {SUBSYSTEM_AGENTS.map((id) => {
          const agentHref =
            id === "atlas" ? "/atlas" :
            id === "scholar" ? "/scholar" :
            `/team/${id}`;
          return (
            <AgentRow
              key={id}
              agentId={id}
              href={agentHref}
              active={isActive(pathname, agentHref)}
              onClick={onClose}
            />
          );
        })}
      </NavSection>

      {/* DAEMON */}
      <NavSection label="DAEMON">
        <Link
          href={sentinelHref}
          onClick={onClose}
          className={cn(
            "ops-nav-item ops-nav-item-agent",
            isActive(pathname, sentinelHref) && "ops-nav-item-active"
          )}
          style={{
            "--agent-color": sentinelIdentity.colorHex,
          } as CSSProperties}
        >
          <AgentGlyph agent={sentinelIdentity} size={16} />
          <span style={{ flex: 1 }}>SENTINEL</span>
          <span className="ops-nav-meta">
            <Dot kind="info" pulse />
          </span>
        </Link>
      </NavSection>

      <SidebarFooter />
    </>
  );

  // Mobile — slide-in drawer
  if (isMobile) {
    return (
      <aside
        className={cn(
          "ops-sidebar fixed left-0 top-0 z-50 h-full w-[220px] transition-transform duration-200",
          collapsed ? "-translate-x-full" : "translate-x-0"
        )}
      >
        {sidebarContent}
      </aside>
    );
  }

  // Desktop — fixed in grid
  return (
    <aside className="ops-sidebar">
      {sidebarContent}
    </aside>
  );
}
