import type { NextConfig } from "next";

// Extra origins allowed during dev (LAN IPs, tailnet hostnames). Comma-separated.
// Example: JARVIS_DEV_ORIGINS="http://192.168.1.42:3000,http://my-pc.tailnet-name.ts.net:3000"
const extraDevOrigins = (process.env.JARVIS_DEV_ORIGINS ?? "")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  allowedDevOrigins: [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost",
    "http://127.0.0.1",
    "localhost",
    "127.0.0.1",
    // Tailnet defaults (resolved by hostname). Operator sets JARVIS_DEV_ORIGINS for explicit ones.
    ...extraDevOrigins,
  ],
  devIndicators: false,
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
