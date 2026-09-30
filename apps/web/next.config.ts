import type { NextConfig } from "next";

import { GEO_API_URL } from "./src/server/geo";

const nextConfig: NextConfig = {
  // Voice calls are WebSockets, which the rewrite cannot carry: the browser opens them on the geo API directly.
  env: { NEXT_PUBLIC_GEO_URL: GEO_API_URL },
  // The browser calls /api/geo/*; Next.js forwards to the geo API so its location stays server-side configuration.
  async rewrites() {
    return [{ source: "/api/geo/:path*", destination: `${GEO_API_URL}/:path*` }];
  },
  // gRPC-based client: load it from node_modules at runtime rather than bundling it.
  serverExternalPackages: ["@google-cloud/firestore"],
};

export default nextConfig;
