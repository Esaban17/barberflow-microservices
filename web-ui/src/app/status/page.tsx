"use client";

import { useEffect, useState } from "react";

import { Alert } from "@/components/Alert";

type ServiceStatus = {
  name: string;
  healthy: boolean;
  instances: number;
  healthyInstances: number;
};

type CircuitInfo = {
  target: string;
  state: "closed" | "open" | "half_open";
  fail_counter: number;
  outbox_pending: number;
};

type StatusResponse = {
  services: ServiceStatus[];
  circuit: CircuitInfo | "unavailable";
  checked_at: string;
};

const POLL_MS = 4_000;

const SERVICE_LABELS: Record<string, string> = {
  "users-svc": "users-svc",
  "booking-svc": "booking-svc",
  "notif-svc": "notif-svc",
};

const CIRCUIT_LABELS: Record<CircuitInfo["state"], string> = {
  closed: "Cerrado (normal)",
  half_open: "Semiabierto (probando)",
  open: "Abierto (cortando llamadas)",
};

function Dot({ color }: { color: "green" | "red" | "yellow" | "stone" }) {
  const classes: Record<typeof color, string> = {
    green: "bg-emerald-500",
    red: "bg-red-500",
    yellow: "bg-amber-500",
    stone: "bg-stone-300",
  };
  return (
    <span
      className={`inline-block h-3 w-3 rounded-full ${classes[color]}`}
      aria-hidden
    />
  );
}

export default function StatusPage() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;

    async function poll() {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) throw new Error(`Error ${response.status}`);
        const payload = (await response.json()) as StatusResponse;
        if (!stale) {
          setData(payload);
          setError(null);
        }
      } catch {
        if (!stale) setError("No se pudo consultar el estado ahora mismo.");
      }
    }

    poll();
    const interval = setInterval(poll, POLL_MS);
    return () => {
      stale = true;
      clearInterval(interval);
    };
  }, []);

  const circuit = data?.circuit;
  const circuitKnown = circuit && circuit !== "unavailable";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Estado del sistema</h1>
        <p className="text-sm text-stone-500">
          Registro en Consul de los 3 microservicios de negocio y estado del
          circuit breaker de booking-svc hacia notif-svc (tarea 47). Se
          actualiza solo cada {POLL_MS / 1000}s.
        </p>
      </div>

      {error && <Alert>{error}</Alert>}

      <section className="rounded-lg border border-stone-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium text-stone-700">
          Servicios registrados en Consul
        </h2>
        {!data ? (
          <p className="text-sm text-stone-500">Consultando…</p>
        ) : (
          <ul className="space-y-2">
            {data.services.map((service) => (
              <li
                key={service.name}
                className="flex items-center gap-3 rounded-md border border-stone-100 px-3 py-2"
              >
                <Dot color={service.healthy ? "green" : "red"} />
                <span className="font-medium">
                  {SERVICE_LABELS[service.name] ?? service.name}
                </span>
                <span className="ml-auto text-sm text-stone-500">
                  {service.healthy
                    ? `${service.healthyInstances}/${service.instances} instancia(s) sana(s)`
                    : service.instances > 0
                      ? "registrado, pero sin instancias sanas"
                      : "sin instancias registradas"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-stone-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium text-stone-700">
          Circuit breaker (booking-svc → notif-svc)
        </h2>
        {!data ? (
          <p className="text-sm text-stone-500">Consultando…</p>
        ) : !circuitKnown ? (
          <div className="flex items-center gap-3">
            <Dot color="stone" />
            <span className="text-sm text-stone-500">
              No se pudo leer — booking-svc no está disponible ahora mismo.
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <Dot
                color={
                  circuit.state === "closed"
                    ? "green"
                    : circuit.state === "half_open"
                      ? "yellow"
                      : "red"
                }
              />
              <span className="font-medium">{CIRCUIT_LABELS[circuit.state]}</span>
            </div>
            <p className="text-sm text-stone-600">
              Objetivo: <code>{circuit.target}</code> · fallos seguidos:{" "}
              {circuit.fail_counter} · notificaciones pendientes en el outbox:{" "}
              {circuit.outbox_pending}
            </p>
            {circuit.state === "open" && (
              <p className="text-sm text-amber-700">
                El breaker está cortando las llamadas a notif-svc: booking-svc
                sigue aceptando reservas y encola las notificaciones en su
                outbox para reintentarlas cuando notif-svc vuelva (tarea 19).
              </p>
            )}
          </div>
        )}
      </section>

      {data && (
        <p className="text-xs text-stone-400">
          Última consulta: {new Date(data.checked_at).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
