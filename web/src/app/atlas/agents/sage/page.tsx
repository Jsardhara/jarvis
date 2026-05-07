"use client";

import { AgentWorkspaceShell } from "@/components/atlas/agents/AgentWorkspaceShell";
import { SageWidgets } from "@/components/atlas/agents/SageWidgets";

export default function SagePage() {
  return (
    <AgentWorkspaceShell
      agentId="sage"
      displayName="SAGE"
      accentColor="var(--atlas-sage, #B98CE0)"
      widgets={<SageWidgets agentId="sage" />}
    />
  );
}
