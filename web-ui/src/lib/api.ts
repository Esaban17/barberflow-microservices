// Cliente del BFF y sesión del navegador.
//
// El navegador nunca habla con un microservicio: todo sale por `/api/...` y es
// Next quien descubre el destino en Consul (ver src/lib/bff.ts).

export type User = {
  id: number;
  email: string;
  full_name: string;
  phone?: string | null;
  role: string;
};

export type Service = { id: number; name: string; duration_min: number; price: number };
export type Barber = { id: number; name: string; chair: number };

export type Slot = {
  id: number;
  barber_id: number;
  barber_name: string;
  service_id: number;
  service_name: string;
  starts_at: string;
  duration_min: number;
  price: number;
};

export type Appointment = {
  id: number;
  user_id: number;
  status: string;
  created_at: string;
  slot: { id: number; starts_at: string; service_name: string; barber_name: string };
  /** Solo en la respuesta de POST /appointments: "sent" o "pending". */
  notification?: "sent" | "pending";
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
};

export type Session = { token: string; user: User };

const SESSION_KEY = "barberflow.session";
/** Evento propio: permite que la cabecera se entere del login/logout sin estado global. */
export const SESSION_EVENT = "barberflow:session";

// ponytail: el JWT se guarda en localStorage, así que queda expuesto a XSS.
// La alternativa segura es una cookie httpOnly emitida por el route handler del
// login; se descartó porque el contrato del BFF exige propagar el header
// `Authorization` que manda el navegador, y para eso el cliente tiene que poder
// leer el token. Si la app llega a producción: mover a cookie httpOnly + SameSite
// y que el proxy inyecte el header desde la cookie.
export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function saveSession(session: Session): void {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession(): void {
  window.localStorage.removeItem(SESSION_KEY);
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Llama al BFF adjuntando el JWT y un correlation-id nuevo por petición. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = getSession();
  const headers = new Headers(init.headers);
  headers.set("x-correlation-id", crypto.randomUUID());
  if (init.body !== undefined) headers.set("content-type", "application/json");
  if (session) headers.set("authorization", `Bearer ${session.token}`);

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "No pudimos contactar al servidor.");
  }

  // Un 401 llevando token es sesión vencida o inválida: al login.
  // Sin token es simplemente una credencial equivocada y lo maneja la pantalla.
  if (response.status === 401 && session) {
    clearSession();
    // Recarga completa a propósito: así no queda estado viejo de la sesión anterior.
    window.location.assign(new URL("/login?vencida=1", window.location.origin));
    throw new ApiError(401, "Tu sesión venció.");
  }

  const payload = (await response.json().catch(() => null)) as
    | (T & { detail?: string })
    | null;

  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : null;
    throw new ApiError(response.status, detail ?? `Error ${response.status}`);
  }
  return payload as T;
}

/**
 * Traduce un error a un mensaje para la pantalla.
 * `overrides` deja que cada pantalla afine un código (p. ej. el 409 al reservar).
 */
export function errorMessage(
  error: unknown,
  overrides: Record<number, string> = {},
): string {
  if (!(error instanceof ApiError)) return "Ocurrió un error inesperado.";
  if (overrides[error.status]) return overrides[error.status];
  if (error.status === 503 || error.status === 502 || error.status === 0) {
    return "Servicio no disponible, intenta de nuevo.";
  }
  if (error.status === 401) return "Tu sesión venció. Vuelve a iniciar sesión.";
  return error.message;
}
