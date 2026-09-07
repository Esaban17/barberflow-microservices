import { NextResponse } from "next/server";

import { ServiceUnavailable, callService, serviceStatus } from "@/lib/consul";

// Tarea 47: panel de estado. Nunca se cachea — cada carga vuelve a preguntarle
// a Consul y a booking-svc en vivo, igual que el resto del BFF.
export const dynamic = "force-dynamic";

const BUSINESS_SERVICES = ["users-svc", "booking-svc", "notif-svc"] as const;

type CircuitInfo = {
  target: string;
  state: "closed" | "open" | "half_open";
  fail_counter: number;
  outbox_pending: number;
};

export async function GET() {
  const services = await Promise.all(BUSINESS_SERVICES.map(serviceStatus));

  let circuit: CircuitInfo | "unavailable" = "unavailable";
  try {
    // El breaker hacia notif-svc lo expone booking-svc (tarea 25): si booking-svc
    // mismo está caído, no hay breaker que mostrar y el panel lo dice tal cual,
    // en vez de simular un estado que no se pudo leer de verdad.
    const upstream = await callService("booking-svc", "/admin/circuit");
    if (upstream.ok) {
      circuit = (await upstream.json()) as CircuitInfo;
    }
  } catch (error) {
    if (!(error instanceof ServiceUnavailable)) throw error;
  }

  return NextResponse.json({
    services,
    circuit,
    checked_at: new Date().toISOString(),
  });
}
