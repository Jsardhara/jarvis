"use client";

import { AgentWorkspaceShell } from "@/components/atlas/agents/AgentWorkspaceShell";
import { TraderWidgets } from "@/components/atlas/agents/TraderWidgets";

export default function TraderPage() {
  return (
    <AgentWorkspaceShell
      agentId="trader"
      displayName="TRADER"
      accentColor="var(--atlas-trader, #E0859E)"
      widgets={<TraderWidgets agentId="trader" />}
    />
  );
}
