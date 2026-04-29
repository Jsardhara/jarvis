import { ReactNode } from "react";
import { cn } from "@/lib/utils";

type TagKind = "default" | "amber" | "ok" | "crit" | "info";

interface TagProps {
  kind?: TagKind;
  /** Adds a subtle elevated background. */
  solid?: boolean;
  className?: string;
  children: ReactNode;
}

const kindClass: Record<TagKind, string> = {
  default: "",
  amber: "ops-tag-amber",
  ok: "ops-tag-ok",
  crit: "ops-tag-crit",
  info: "ops-tag-info",
};

export function Tag({ kind = "default", solid = false, className, children }: TagProps) {
  return (
    <span
      className={cn(
        "ops-tag",
        kindClass[kind],
        solid && "ops-tag-solid",
        className
      )}
    >
      {children}
    </span>
  );
}
