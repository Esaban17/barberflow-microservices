// Descubrimiento de servicios contra la HTTP API de Consul.
//
// Espeja `shared/consul.py`: se le pregunta a Consul por las instancias *passing*
// y la lista vacía se trata como fallo esperado (el servicio se cayó y Consul ya
// lo desregistró), nunca como un IndexError que acabaría en un 500 opaco.
//
// Este módulo es SOLO de servidor: `CONSUL_HTTP_ADDR` no lleva prefijo
// NEXT_PUBLIC_, así que nunca puede terminar en el bundle del navegador.

/** Timeout corto: si Consul no responde en 2s, damos el servicio por caído. */
const CONSUL_TIMEOUT_MS = 2_000;
/** Timeout de la llamada al microservicio ya descubierto. */
const SERVICE_TIMEOUT_MS = 8_000;

function consulAddress(): string {
  // Se lee en cada llamada, no al importar: el contenedor la inyecta por entorno.
  return (process.env.CONSUL_HTTP_ADDR ?? "http://consul:8500").replace(/\/+$/, "");
}

/** No hay ninguna instancia sana del servicio buscado (o Consul no responde). */
export class ServiceUnavailable extends Error {
  readonly service: string;

  constructor(service: string, options?: { cause?: unknown }) {
    super(`${service} no disponible`, options);
    this.name = "ServiceUnavailable";
    this.service = service;
  }
}

type ConsulHealthEntry = {
  Node: { Address: string };
  Service: { Address?: string; Port: number };
};

/** Base URL ("http://host:puerto") de una instancia sana del servicio. */
export async function discover(service: string): Promise<string> {
  let instances: ConsulHealthEntry[];
  try {
    const response = await fetch(
      `${consulAddress()}/v1/health/service/${service}?passing=true`,
      { cache: "no-store", signal: AbortSignal.timeout(CONSUL_TIMEOUT_MS) },
    );
    if (!response.ok) throw new Error(`Consul respondió ${response.status}`);
    instances = (await response.json()) as ConsulHealthEntry[];
  } catch (cause) {
    throw new ServiceUnavailable(service, { cause });
  }

  if (instances.length === 0) throw new ServiceUnavailable(service);

  // Reparto simple entre las instancias sanas, igual que shared/consul.py.
  const entry = instances[Math.floor(Math.random() * instances.length)];
  // Consul deja `Service.Address` vacío cuando el servicio hereda la del nodo.
  const host = entry.Service.Address || entry.Node.Address;
  return `http://${host}:${entry.Service.Port}`;
}

/**
 * Llama a un microservicio resolviéndolo antes en Consul.
 * Lanza `ServiceUnavailable` si no hay instancias sanas o si la llamada falla en red.
 */
export async function callService(
  service: string,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const base = await discover(service);
  try {
    return await fetch(`${base}${path}`, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(SERVICE_TIMEOUT_MS),
    });
  } catch (cause) {
    throw new ServiceUnavailable(service, { cause });
  }
}
