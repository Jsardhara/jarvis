import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface SubHProps {
  children: ReactNode;
  /** Right-aligned trailing element (count, action). */
  trailing?: ReactNode;
  className?: string;
}

/**
 * Section sub-header — small uppercase tracked label with a fading
 * 1px rule sweeping right. Used between content sections inside a view.
 */
export function SubH({ children, trailing, className }: SubHProps) {
  return (
    <div className={cn("ops-sub-h mb-2.5", className)}>
      <span style={{ order: 0 }}>{children}</span>
      {trailing && <span className="ops-sub-h-trailing">{trailing}</span>}
    </div>
  );
}
