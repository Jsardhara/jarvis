import { cn } from "@/lib/utils";

type DotKind = "ok" | "warn" | "crit" | "info" | "idle";

interface DotProps {
  kind?: DotKind;
  pulse?: boolean;
  className?: string;
}

const kindClass: Record<DotKind, string> = {
  ok: "ops-dot-ok",
  warn: "ops-dot-warn",
  crit: "ops-dot-crit",
  info: "ops-dot-info",
  idle: "ops-dot-idle",
};

/** Status pip — 6px round dot with optional 1.4s pulse. */
export function Dot({ kind = "idle", pulse = false, className }: DotProps) {
  return (
    <span
      className={cn(
        "ops-dot",
        kindClass[kind],
        pulse && "ops-dot-pulse",
        className
      )}
      aria-hidden="true"
    />
  );
}
