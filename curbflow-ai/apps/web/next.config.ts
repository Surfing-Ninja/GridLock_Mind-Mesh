// Next.js configuration placeholder for the CurbFlow AI web app.

import type { NextConfig } from "next";

const apiInternalUrl = process.env.CURBFLOW_API_INTERNAL_URL;

const nextConfig: NextConfig = {
  async rewrites() {
    if (!apiInternalUrl) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${apiInternalUrl}/:path*`,
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
