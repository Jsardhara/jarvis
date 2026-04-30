"use client";

import { AgentWorkspaceShell } from "@/components/atlas/agents/AgentWorkspaceShell";
import { OracleWidgets } from "@/components/atlas/agents/OracleWidgets";

export default function OraclePage() {
  return (
    <AgentWorkspaceShell
      agentId="oracle"
      displayName="ORACLE"
      accentColor="var(--atlas-oracle, #F2D06B)"
      widgets={<OracleWidgets agentId="oracle" />}
    />
  );
}
