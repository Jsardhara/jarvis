import { CSSProperties } from "react";

interface CornerTicksProps {
  /** CSS color of the tick borders. Defaults to bright line. */
  accent?: string;
  /** Square pixel size of each tick. */
  size?: number;
}

/**
 * Mission-control bracket frame — four L-shaped 8px ticks at the
 * corners of the parent (which must be position: relative).
 */
export function CornerTicks({
  accent = "var(--ops-line-bright)",
  size = 8,
}: CornerTicksProps) {
  const base: CSSProperties = {
    position: "absolute",
    width: size,
    height: size,
    borderColor: accent,
    borderStyle: "solid",
    pointerEvents: "none",
  };
  return (
    <>
      <span style={{ ...base, top: 0, left: 0, borderWidth: "1px 0 0 1px" }} />
      <span style={{ ...base, top: 0, right: 0, borderWidth: "1px 1px 0 0" }} />
      <span style={{ ...base, bottom: 0, left: 0, borderWidth: "0 0 1px 1px" }} />
      <span style={{ ...base, bottom: 0, right: 0, borderWidth: "0 1px 1px 0" }} />
    </>
  );
}
