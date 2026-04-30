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
import { MockModeBanner } from "@/components/atlas/MockModeBanner";
import { AgentStatusRow } from "@/components/atlas/AgentStatusRow";

// TODO(C2): The confirmation API contract may diverge once C2 lands.
// Current assumption: separate endpoints /approve and /reject rather than a
// single endpoint with { decision } body. Verify against C2 once merged.
const JARVIS_API =
  process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765";

async function resolveConfirmation(
  eventId: string,
  decision: "approve" | "reject"
): Promise<void> {
  // The event id has the form "{request_id}:{stage}" — extract request_id
  const requestId = eventId.split(":")[0];
  const endpoint = `${JARVIS_API}/api/confirmations/${requestId}/${decision}`;

  const res = await fetch(endpoint, { method: "POST" });
  if (!res.ok) {
    // Log the error but don't throw — the UI should still respond
    // to user action even if the backend is temporarily unavailable.
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
      <MockModeBanner />

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
