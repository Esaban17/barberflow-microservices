import Link from "next/link";

import { Alert } from "@/components/Alert";
import type { Barber, Service } from "@/lib/api";
import { ServiceUnavailable, callService } from "@/lib/consul";
import { quetzales } from "@/lib/format";

// Catálogo en vivo: no se prerenderiza en el build, donde no hay Consul a mano.
export const dynamic = "force-dynamic";

type Catalog = { services: Service[]; barbers: Barber[]; error: string | null };

/** Lee el catálogo en el servidor, descubriendo booking-svc en Consul. */
async function loadCatalog(): Promise<Catalog> {
  const empty = { services: [], barbers: [] };
  try {
    const [servicesResponse, barbersResponse] = await Promise.all([
      callService("booking-svc", "/services"),
      callService("booking-svc", "/barbers"),
    ]);
    if (!servicesResponse.ok || !barbersResponse.ok) {
      return { ...empty, error: "No pudimos leer el catálogo, intenta de nuevo." };
    }
    return {
      services: (await servicesResponse.json()) as Service[],
      barbers: (await barbersResponse.json()) as Barber[],
      error: null,
    };
  } catch (error) {
    const detail =
      error instanceof ServiceUnavailable
        ? "Servicio no disponible, intenta de nuevo."
        : "No pudimos leer el catálogo, intenta de nuevo.";
    return { ...empty, error: detail };
  }
}

export default async function HomePage() {
  const { services, barbers, error } = await loadCatalog();

  return (
    <div className="space-y-10">
      <section className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">
          Tu corte, a la hora que te queda
        </h1>
        <p className="text-stone-600">
          Escoge el servicio, mira los horarios libres y reserva en menos de un minuto.
        </p>
        <Link
          href="/book"
          className="inline-block rounded-md bg-amber-700 px-4 py-2 text-white hover:bg-amber-800"
        >
          Reservar una cita
        </Link>
      </section>

      {error && <Alert>{error}</Alert>}

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Servicios</h2>
        {services.length === 0 && !error && (
          <p className="text-sm text-stone-500">Todavía no hay servicios cargados.</p>
        )}
        <ul className="grid gap-3 sm:grid-cols-2">
          {services.map((service) => (
            <li
              key={service.id}
              className="rounded-lg border border-stone-200 bg-white p-4"
            >
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="font-medium">{service.name}</h3>
                <span className="font-semibold text-amber-800">
                  {quetzales(service.price)}
                </span>
              </div>
              <p className="mt-1 text-sm text-stone-500">
                {service.duration_min} minutos
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Barberos</h2>
        {barbers.length === 0 && !error && (
          <p className="text-sm text-stone-500">Todavía no hay barberos cargados.</p>
        )}
        <ul className="grid gap-3 sm:grid-cols-3">
          {barbers.map((barber) => (
            <li
              key={barber.id}
              className="rounded-lg border border-stone-200 bg-white p-4"
            >
              <h3 className="font-medium">{barber.name}</h3>
              <p className="mt-1 text-sm text-stone-500">Silla {barber.chair}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
