import type { Metadata } from "next";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { LayoutShell } from "@/components/layout-shell";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "sonner";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "JARVIS // OPS",
  description: "Mission control — orchestrator + agent fleet",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`dark ${jetbrainsMono.variable} ${spaceGrotesk.variable}`}>
      <body className="antialiased">
        <ThemeProvider>
          <LayoutShell>{children}</LayoutShell>
          <Toaster
            theme="dark"
            position="bottom-right"
            toastOptions={{
              className: "border-ops-line bg-ops-elevated text-ops-fg",
              style: {
                fontFamily: "var(--ops-mono)",
                fontSize: "11px",
                letterSpacing: "0.04em",
              },
            }}
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
