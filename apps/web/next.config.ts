import type { NextConfig } from "next";

// The browser calls /api/geo/*; Next.js forwards to the geo API so its location stays server-side configuration.
const GEO_API_URL = process.env.GEO_API_URL ?? "https://shadowcast-geo-489356738785.asia-south1.run.app";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/geo/:path*", destination: `${GEO_API_URL}/:path*` }];
  },
};

export default nextConfig;
