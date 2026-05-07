/**
 * CRT-style 1px scanline overlay — absolutely positioned, pointer-events
 * disabled. Drop into the closest positioned ancestor.
 */
export function Scanline() {
  return <div className="ops-scanline" aria-hidden="true" />;
}
