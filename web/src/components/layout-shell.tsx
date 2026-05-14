"use client";

import { useState, useCallback, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CommandBar } from "@/components/command-bar";
import { SearchDialog } from "@/components/search-dialog";
import { AppSidebar } from "@/components/app-sidebar";
import { KeyboardShortcuts } from "@/components/keyboard-shortcuts";
import { OnboardingDialog } from "@/components/onboarding-dialog";
import { Topbar } from "@/components/ops/Topbar";
import { Statusbar } from "@/components/ops/Statusbar";
import { useSidebar } from "@/hooks/use-sidebar";
import { useConnection } from "@/hooks/use-connection";
import { apiFetch } from "@/lib/api-client";
import { showSuccess, showError } from "@/lib/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ActiveRunsProvider } from "@/providers/active-runs-provider";
import { AtlasDegradedBanner } from "@/components/AtlasDegradedBanner";
import { MockModeBanner } from "@/components/atlas/MockModeBanner";

interface LayoutShellProps {
  children: React.ReactNode;
}

export function LayoutShell({ children }: LayoutShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const { tasks, unreadInbox, pendingDecisions } = useSidebar();
  const { online } = useConnection();

  // Detect mobile viewport and auto-close sidebar
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setSidebarOpen(false);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Auto-close sidebar on mobile when navigating
  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
  }, [pathname, isMobile]);

  const handleCapture = useCallback(async (content: string) => {
    try {
      const res = await apiFetch("/api/brain-dump", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content,
          capturedAt: new Date().toISOString(),
          processed: false,
          convertedTo: null,
          tags: [],
        }),
      });
      if (!res.ok) throw new Error("Failed to capture");
      showSuccess("Entry created");
    } catch {
      showError("Failed to capture entry");
    }
  }, []);

  return (
    <TooltipProvider delayDuration={300}>
      {/* Atlas status banners sit above the grid as 1-line strips.
          Only one renders at a time — MockModeBanner suppresses itself when
          AtlasDegradedBanner is visible to avoid stacked amber noise. */}
      <AtlasDegradedBanner />
      <MockModeBanner />

      {/* Ops Black 4-area grid */}
      <div className="ops-app">
        <Topbar />

        {/* Mobile backdrop */}
        {isMobile && sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <AppSidebar
          collapsed={!sidebarOpen}
          unreadInbox={unreadInbox}
          pendingDecisions={pendingDecisions}
          isMobile={isMobile}
          onClose={() => setSidebarOpen(false)}
        />

        <main id="main-content" className="ops-main">
          {!online && (
            <div
              className="flex items-center justify-center gap-2 py-2 px-3 text-xs"
              style={{
                background: "color-mix(in srgb, var(--ops-crit) 10%, transparent)",
                borderBottom: "1px solid var(--ops-crit)",
                color: "var(--ops-crit)",
                fontFamily: "var(--ops-mono)",
                letterSpacing: "0.06em",
              }}
            >
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ background: "var(--ops-crit)", animation: "ops-pulse-dot 1.4s infinite" }}
              />
              CONNECTION LOST — changes may not save. Retrying automatically...
            </div>
          )}
          <ActiveRunsProvider>
            {children}
          </ActiveRunsProvider>
        </main>

        <Statusbar />
      </div>

      {/* Overlays — rendered outside the grid so they sit above everything */}
      <a href="#main-content" className="skip-to-content">Skip to content</a>
      <KeyboardShortcuts
        onCreateTask={() => {
          // Dispatch a window event the CommandBar / forms can listen for.
          // Also navigate to status-board where the new-task form lives.
          window.dispatchEvent(new CustomEvent("jarvis:new-task"));
          router.push("/status-board?new=task");
        }}
      />
      <OnboardingDialog />
      <SearchDialog />
      <CommandBar
        onCapture={handleCapture}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        isMobile={isMobile}
        tasks={tasks}
        onTaskClick={() => router.push("/status-board")}
      />
    </TooltipProvider>
  );
}
