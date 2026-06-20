// Next.js configuration placeholder for the CurbFlow AI web app.

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
