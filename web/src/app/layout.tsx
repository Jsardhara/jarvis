import type { Metadata } from "next";
import { JetBrains_Mono, Fraunces } from "next/font/google";
import { Shell } from "@/components/Shell";
import { WsProvider } from "@/lib/ws";
import "./globals.css";

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono-loaded",
  display: "swap",
});

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display-loaded",
  display: "swap",
  axes: ["opsz"],
});

export const metadata: Metadata = {
  title: "Jarvis — Mission Control",
  description: "Personal assistant — multi-agent control surface",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${mono.variable} ${display.variable}`}>
      <body>
        <WsProvider>
          <Shell>{children}</Shell>
        </WsProvider>
      </body>
    </html>
  );
}
