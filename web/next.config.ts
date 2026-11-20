import type { NextConfig } from "next";

const apiMocking = process.env.OGRL_API_MOCKING === "enabled";
const apiOrigin = process.env.OGRL_API_ORIGIN ?? "http://127.0.0.1:8080";

const nextConfig: NextConfig = {
  // Lets a production build run beside `next dev` without sharing .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // RFC 0003 section 2: the web process forwards /v1 and /health to the API.
  // In mock mode the /v1 route handler answers from fixtures instead.
  async rewrites() {
    if (apiMocking) return [];
    return {
      beforeFiles: [
        { source: "/v1/:path*", destination: `${apiOrigin}/v1/:path*` },
        { source: "/health", destination: `${apiOrigin}/health` },
      ],
      afterFiles: [],
      fallback: [],
    };
  },
};

export default nextConfig;
