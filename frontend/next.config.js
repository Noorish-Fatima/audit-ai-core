/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        // Server-side proxy: must use the Docker-internal hostname, NOT
        // NEXT_PUBLIC_API_URL (baked at build time for the browser, which
        // correctly uses localhost from the host). Browser fetch paths
        // already include the full versioned prefix (e.g. /api/v1/auth/login),
        // so pass :path* through untouched to avoid doubling /v1.
        destination: `${process.env.API_INTERNAL_URL || 'http://api:8000'}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;