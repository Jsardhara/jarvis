"use client";

import { AgentWorkspaceShell } from "@/components/atlas/agents/AgentWorkspaceShell";
import { ArchitectWidgets } from "@/components/atlas/agents/ArchitectWidgets";

export default function ArchitectPage() {
  return (
    <AgentWorkspaceShell
      agentId="architect"
      displayName="ARCHITECT"
      accentColor="var(--atlas-architect, #7CB6E8)"
      widgets={<ArchitectWidgets agentId="architect" />}
    />
  );
}
