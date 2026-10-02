import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  images: { unoptimized: true },
  output: "standalone", // built on the developer PC, shipped to the server as a self-contained folder
  // studio apps are scoped to /s/<slug>/ (with the slash, so studios never overlap): keep that URL, do not redirect it away
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
