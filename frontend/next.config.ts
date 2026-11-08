import type { NextConfig } from "next";

// Where the FastAPI backend runs. The browser never calls it directly: `/api/*` on this
// site is forwarded there, so session cookies stay same-site (A-152, D-48).
//
// The rewrite target is fixed when `next build` runs, while server components read
// API_URL when the server runs. So a production build or start without API_URL fails
// here, instead of quietly proxying to localhost. `npm run dev` defaults to port 8000.
const isProduction = process.env.NODE_ENV === "production";
if (isProduction && !process.env.API_URL) {
  throw new Error("Set API_URL (the backend's base URL) for `next build` and `next start`.");
}
const apiUrl = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
