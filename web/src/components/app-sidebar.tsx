"use client";

import Link from "next/link";
import { useState } from "react";
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

// Atlas sub-agent nav entries with their accent CSS var
interface AtlasAgentEntry {
  href: string;
  label: string;
  accentVar: string;
  fallbackColor: string;
}

const ATLAS_AGENT_ENTRIES: AtlasAgentEntry[] = [
  { href: "/atlas/agents/oracle",    label: "Oracle",    accentVar: "--atlas-oracle",    fallbackColor: "#F2D06B" },
  { href: "/atlas/agents/architect", label: "Architect", accentVar: "--atlas-architect", fallbackColor: "#7CB6E8" },
  { href: "/atlas/agents/guardian",  label: "Guardian",  accentVar: "--atlas-guardian",  fallbackColor: "#6FCF7F" },
  { href: "/atlas/agents/trader",    label: "Trader",    accentVar: "--atlas-trader",    fallbackColor: "#E0859E" },
  { href: "/atlas/agents/sage",      label: "Sage",      accentVar: "--atlas-sage",      fallbackColor: "#B98CE0" },
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

// ─── Atlas agent leaf item ────────────────────────────────────────────────────

interface AtlasAgentItemProps {
  entry: AtlasAgentEntry;
  active: boolean;
  onClick?: () => void;
}

function AtlasAgentItem({ entry, active, onClick }: AtlasAgentItemProps) {
  return (
    <Link
      href={entry.href}
      onClick={onClick}
      className={cn("ops-nav-item ops-nav-item--indented", active && "ops-nav-item-active")}
      data-testid={`atlas-agent-link-${entry.label.toLowerCase()}`}
    >
      {/* Accent dot using the per-agent CSS var */}
      <span
        aria-hidden
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: `var(${entry.accentVar}, ${entry.fallbackColor})`,
          flexShrink: 0,
          marginRight: 2,
        }}
      />
      <span style={{ flex: 1 }}>{entry.label}</span>
    </Link>
  );
}

// ─── Atlas collapsible agents group ──────────────────────────────────────────

interface AtlasAgentsGroupProps {
  pathname: string;
  onClick?: () => void;
}

function AtlasAgentsGroup({ pathname, onClick }: AtlasAgentsGroupProps) {
  // Open by default when any agent sub-page is active
  const anyAgentActive = ATLAS_AGENT_ENTRIES.some((e) => isActive(pathname, e.href));
  const [open, setOpen] = useState(anyAgentActive);

  const groupActive = anyAgentActive;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        data-testid="atlas-agents-group-toggle"
        className={cn("ops-nav-item ops-nav-item--group-toggle", groupActive && "ops-nav-item-active")}
        style={{ width: "100%", textAlign: "left", background: "none", border: "none", cursor: "pointer" }}
      >
        <span className="ops-nav-glyph" aria-hidden>{open ? "▾" : "▸"}</span>
        <span style={{ flex: 1 }}>Agents</span>
      </button>

      {open && (
        <div data-testid="atlas-agents-group">
          {ATLAS_AGENT_ENTRIES.map((entry) => (
            <AtlasAgentItem
              key={entry.href}
              entry={entry}
              active={isActive(pathname, entry.href)}
              onClick={onClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Atlas section ────────────────────────────────────────────────────────────

interface AtlasSectionProps {
  pathname: string;
  onClick?: () => void;
}

function AtlasSection({ pathname, onClick }: AtlasSectionProps) {
  return (
    <NavSection label="ATLAS">
      <NavItem
        href="/atlas"
        label="Overview"
        glyph="◈"
        active={pathname === "/atlas"}
        onClick={onClick}
      />
      <NavItem
        href="/atlas/pipeline"
        label="Pipeline"
        glyph="⇢"
        active={isActive(pathname, "/atlas/pipeline")}
        onClick={onClick}
      />
      <NavItem
        href="/atlas/network"
        label="Network"
        glyph="⬡"
        active={isActive(pathname, "/atlas/network")}
        onClick={onClick}
      />
      <NavItem
        href="/atlas/trades"
        label="Trades"
        glyph="⇄"
        active={isActive(pathname, "/atlas/trades")}
        onClick={onClick}
      />
      <AtlasAgentsGroup pathname={pathname} onClick={onClick} />
    </NavSection>
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

      {/* ATLAS — dedicated nav section with sub-pages */}
      <AtlasSection pathname={pathname} onClick={onClose} />

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
