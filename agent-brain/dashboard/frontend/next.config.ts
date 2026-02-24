import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy /api/* requests to FastAPI backend (avoids CORS/auth issues in Codespaces)
  async rewrites() {
    const apiUrl = process.env.API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
