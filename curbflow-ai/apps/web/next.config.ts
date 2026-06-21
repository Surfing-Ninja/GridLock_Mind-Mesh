// Next.js configuration placeholder for the CurbFlow AI web app.

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/:path*",
      },
    ];
  },
  async redirects() {
    return [
      {
        source: "/patrol-twin",
        destination: "/patrol-digital-twin",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
