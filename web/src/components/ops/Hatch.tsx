import { CSSProperties } from "react";
import { cn } from "@/lib/utils";

interface HatchProps {
  label?: string;
  height?: number;
  className?: string;
}

/** Diagonal-hatched dashed-border placeholder for empty states. */
export function Hatch({ label = "— PLACEHOLDER —", height = 80, className }: HatchProps) {
  const style: CSSProperties = { height };
  return (
    <div
      className={cn(
        "ops-hatch grid place-items-center",
        className
      )}
      style={style}
    >
      <span
        className="font-mono text-[10px] uppercase tracking-[0.18em] text-ops-fg-faint"
      >
        {label}
      </span>
    </div>
  );
}
