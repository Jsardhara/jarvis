import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { LayoutShell } from "@/components/layout-shell";
import { ThemeProvider } from "@/components/theme-provider";
import { ServiceWorkerRegister } from "@/components/sw-register";
import { AuthGate } from "@/components/auth-gate";
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
  manifest: "/manifest.webmanifest",
  applicationName: "Jarvis",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Jarvis",
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: "#0a0e14",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`dark ${jetbrainsMono.variable} ${spaceGrotesk.variable}`}>
      <body className="antialiased">
        <ThemeProvider>
          <ServiceWorkerRegister />
          <AuthGate>
            <LayoutShell>{children}</LayoutShell>
          </AuthGate>
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
