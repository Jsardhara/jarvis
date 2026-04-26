import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Jarvis",
  description: "Personal assistant — multi-agent control surface",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <span className="brand">Jarvis</span>
          <nav>
            <a href="/">Briefing</a>
            <a href="/inbox">Inbox</a>
            <a href="/tasks">Tasks</a>
            <a href="/atlas">ATLAS</a>
            <a href="/console">Console</a>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
