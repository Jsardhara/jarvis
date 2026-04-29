import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelProps {
  title?: string;
  /** Slot rendered to the right of the title (badges, counts, actions). */
  trailing?: ReactNode;
  /** Optional leading slot before the title (status dot, glyph). */
  leading?: ReactNode;
  /** Drop default padding on body — useful for tables/lists. */
  flushBody?: boolean;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

/**
 * Operations Black panel — hairline border, sharp corners, monospace
 * uppercase title bar. Composes via leading/trailing slots so each
 * caller stays terse.
 */
export function Panel({
  title,
  trailing,
  leading,
  flushBody = false,
  className,
  bodyClassName,
  children,
}: PanelProps) {
  return (
    <section className={cn("ops-panel", className)}>
      {(title || leading || trailing) && (
        <header className="ops-panel-header">
          {leading}
          {title && <span className="ops-panel-title">{title}</span>}
          {trailing && <span className="ml-auto flex items-center gap-2">{trailing}</span>}
        </header>
      )}
      <div className={cn("ops-panel-body", flushBody && "p-0", bodyClassName)}>
        {children}
      </div>
    </section>
  );
}
