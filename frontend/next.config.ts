import type { NextConfig } from "next";

const backendWsBase = process.env.BACKEND_WS_BASE_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [
      {
        source: "/ws",
        destination: `${backendWsBase}/ws`,
      },
    ];
  },
};

export default nextConfig;