import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * Backend API Proxy Configuration
   * Vite의 proxy 설정을 Next.js rewrites로 변환
   */
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    return [
      // WebSocket 프록시
      {
        source: "/ws/:path*",
        destination: `${backendUrl}/ws/:path*`,
      },
      // REST API 프록시
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
