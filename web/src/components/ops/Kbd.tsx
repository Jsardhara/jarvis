import { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Keyboard chip — small mono pill for shortcuts. */
export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return <kbd className={cn("ops-kbd", className)}>{children}</kbd>;
}
