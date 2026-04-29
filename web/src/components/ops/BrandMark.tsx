/**
 * Jarvis brand mark — rotated 22px square outline with a glowing
 * amber dot at center. Used in topbar + chat empty state.
 */
export function BrandMark({ className }: { className?: string }) {
  return <span className={`ops-brand-mark ${className ?? ""}`} aria-hidden="true" />;
}
