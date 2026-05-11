import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Orbitron, Rajdhani } from "next/font/google";
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

const rajdhani = Rajdhani({
  subsets: ["latin"],
  variable: "--font-rajdhani",
  display: "swap",
  weight: ["300", "400", "500", "600", "700"],
});

const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-orbitron",
  display: "swap",
  weight: ["400", "500", "600", "700", "800", "900"],
});

export const metadata: Metadata = {
  title: "JARVIS // HUD MK-VII",
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
  themeColor: "#040d1a",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`dark ${jetbrainsMono.variable} ${rajdhani.variable} ${orbitron.variable}`}
    >
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
