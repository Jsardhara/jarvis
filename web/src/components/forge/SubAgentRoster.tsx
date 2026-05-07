"use client";

import type { CSSProperties } from "react";

const ROSTER = [
  { id: "planner", role: "PLANS REPO + TASK BREAKDOWN", glyph: "PL" },
  { id: "tdd-guide", role: "WRITES TESTS FIRST", glyph: "TD" },
  { id: "prp-implement", role: "EXECUTES PLAN", glyph: "IM" },
  { id: "code-reviewer", role: "QUALITY GATE", glyph: "CR" },
  { id: "security-reviewer", role: "OWASP / SECRETS GATE", glyph: "SR" },
  { id: "typescript-reviewer", role: "TS-SPECIFIC CHECKS", glyph: "TS" },
  { id: "python-reviewer", role: "PYTHON-SPECIFIC CHECKS", glyph: "PY" },
  { id: "github-ops", role: "OPENS PR", glyph: "GH" },
] as const;

export function SubAgentRoster() {
  const row: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "32px 1fr",
    gap: 10,
    padding: "8px 12px",
    borderBottom: "1px dashed var(--ops-line)",
    fontFamily: "var(--ops-mono)",
    alignItems: "center",
  };

  const glyph: CSSProperties = {
    width: 26,
    height: 22,
    border: "1px solid #6FCF7F",
    color: "#6FCF7F",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 10,
    letterSpacing: "0.08em",
  };

  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {ROSTER.map((a) => (
        <li key={a.id} style={row}>
          <span style={glyph}>{a.glyph}</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span
              style={{
                color: "var(--ops-fg)",
                fontSize: 11,
                letterSpacing: "0.04em",
              }}
            >
              {a.id}
            </span>
            <span
              style={{
                color: "var(--ops-fg-mute)",
                fontSize: 9,
                letterSpacing: "0.06em",
              }}
            >
              {a.role}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
