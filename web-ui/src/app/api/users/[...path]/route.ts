import { proxyTo } from "@/lib/bff";

// El BFF nunca se cachea: cada llamada resuelve en Consul y reenvía en vivo.
export const dynamic = "force-dynamic";

const handler = proxyTo("users-svc");

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
};
