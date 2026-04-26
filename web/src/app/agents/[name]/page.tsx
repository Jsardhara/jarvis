"use client";

import { use } from "react";
import useSWR from "swr";
import Link from "next/link";
import { agentHistory, listAgents, type AgentDescriptor, type AgentLogEntry } from "@/lib/api";
import { AgentDrawer } from "@/components/AgentDrawer";

interface PageProps {
  params: Promise<{ name: string }>;
}

export default function AgentDeepDive({ params }: PageProps) {
  const { name } = use(params);
  const { data: agents } = useSWR<AgentDescriptor[]>("agents", listAgents);
  const { data: history } = useSWR<AgentLogEntry[]>(
    `agent-history-deep:${name}`,
    () => agentHistory(name, 100),
    { refreshInterval: 5000 }
  );
  const desc = agents?.find((a) => a.name === name) ?? null;

  return (
    <div style={{ display: "grid", gap: "1rem", padding: "1rem" }}>
      <Link href="/" className="muted">
        ← back to mission control
      </Link>
      <h1 style={{ letterSpacing: "0.16em" }}>{name.toUpperCase()}</h1>
      {desc && <p className="muted">{desc.description}</p>}

      <h2>full history</h2>
      <div className="card mono" style={{ display: "grid", gap: "0.4rem", fontSize: "0.78rem" }}>
        {(history ?? []).length === 0 && <span className="muted">no history yet</span>}
        {(history ?? []).slice().reverse().map((h) => (
          <div key={`${h.request_id}-${h.ts}`} className="row">
            <span className="muted">{new Date(h.ts).toLocaleString()}</span>
            <span>{h.action}</span>
            <span className={`severity severity-${h.status === "error" ? "alert" : "info"}`} />
            <span>{h.duration_ms}ms · {Math.round(h.confidence * 100)}%</span>
          </div>
        ))}
      </div>

      {desc && (
        <AgentDrawer
          agent={desc}
          onClose={() => {
            window.history.back();
          }}
        />
      )}
    </div>
  );
}
