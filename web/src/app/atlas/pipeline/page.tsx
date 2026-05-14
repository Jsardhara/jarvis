"use client";

/**
 * /atlas/pipeline — Atlas pipeline swimlane
 *
 * Subscribes to /ws via usePipelineStream, feeds events into
 * PipelineSwimlane. Confirmation gate wires to /api/confirmations/{id}/approve
 * and /api/confirmations/{id}/reject.
 *
 * Spec: docs/design/swimlane.md §2–5
 */

import { useCallback } from "react";
import { BreadcrumbNav } from "@/components/breadcrumb-nav";
import { PipelineSwimlane } from "@/components/PipelineSwimlane";
import { usePipelineStream } from "@/hooks/usePipelineStream";
// MockModeBanner is mounted globally in LayoutShell — see web/src/components/layout-shell.tsx.
import { AgentStatusRow } from "@/components/atlas/AgentStatusRow";
import { apiFetch } from "@/lib/api-client";

async function resolveConfirmation(
  eventId: string,
  decision: "approve" | "reject"
): Promise<void> {
  const requestId = eventId.split(":")[0];
  const endpoint = `/api/confirmations/${requestId}/${decision}`;

  const res = await apiFetch(endpoint, { method: "POST" });
  if (!res.ok) {
    console.error(`[pipeline] confirmation ${decision} failed: HTTP ${res.status}`);
  }
}

export default function AtlasPipelinePage() {
  const { events, connectionState } = usePipelineStream();

  const handleConfirm = useCallback(
    async (eventId: string, decision: "approve" | "reject") => {
      await resolveConfirmation(eventId, decision);
    },
    []
  );

  return (
    <div className="space-y-4">
      <BreadcrumbNav
        items={[
          { label: "Atlas", href: undefined },
          { label: "Pipeline" },
        ]}
      />

      <AgentStatusRow />

      <div className="border border-[color:var(--pipeline-lane-divider)] bg-[color:var(--pipeline-lane-bg)] rounded-none overflow-hidden">
        <PipelineSwimlane
          events={events}
          connectionState={connectionState}
          onConfirm={handleConfirm}
          maxEventsPerLane={80}
        />
      </div>
    </div>
  );
}
