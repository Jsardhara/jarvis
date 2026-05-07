"use client";

import { AgentWorkspaceShell } from "@/components/atlas/agents/AgentWorkspaceShell";
import { GuardianWidgets } from "@/components/atlas/agents/GuardianWidgets";

export default function GuardianPage() {
  return (
    <AgentWorkspaceShell
      agentId="guardian"
      displayName="GUARDIAN"
      accentColor="var(--atlas-guardian, #6FCF7F)"
      widgets={<GuardianWidgets agentId="guardian" />}
    />
  );
}
