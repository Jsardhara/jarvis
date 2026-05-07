import { ReactNode } from "react";

interface KVProps {
  label: string;
  /** Optional CSS color override for the value (e.g. amber for emphasis). */
  accent?: string;
  children: ReactNode;
}

/**
 * Label/value row — uppercase tracked label on the left,
 * tabular-nums value on the right, dashed hairline rule below.
 */
export function KV({ label, accent, children }: KVProps) {
  return (
    <div
      className="flex items-baseline justify-between text-[11px] py-[5px]"
      style={{ borderBottom: "1px dashed var(--ops-line)" }}
    >
      <span className="text-[10px] uppercase tracking-[0.1em] text-ops-fg-dim font-mono">
        {label}
      </span>
      <span
        className="ops-mono-num"
        style={{ color: accent ?? "var(--ops-fg)" }}
      >
        {children}
      </span>
    </div>
  );
}
