import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Empaqueta el servidor y solo sus dependencias reales: la imagen final del
  // Dockerfile se queda en unas decenas de MB en vez de arrastrar node_modules.
  output: "standalone",
};

export default nextConfig;
