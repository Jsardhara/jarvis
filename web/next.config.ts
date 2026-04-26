import type { NextConfig } from "next";

const config: NextConfig = {
  async rewrites() {
    const api = process.env.JARVIS_API_URL ?? "http://localhost:8765";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default config;
