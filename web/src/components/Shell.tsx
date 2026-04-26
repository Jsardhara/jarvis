"use client";

import { usePathname } from "next/navigation";
import { TopNav } from "./TopNav";

interface ShellProps {
  children: React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const pathname = usePathname();
  const fullBleed = pathname === "/";
  return (
    <>
      <TopNav />
      {fullBleed ? children : <main>{children}</main>}
    </>
  );
}
