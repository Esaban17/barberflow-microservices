"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert } from "@/components/Alert";
import { SignInRequired } from "@/components/SignInRequired";
import {
  api,
  errorMessage,
  type Appointment,
  type Service,
  type Slot,
} from "@/lib/api";
import { formatDateTime, formatTime, quetzales, todayInGuatemala } from "@/lib/format";
import { useSession } from "@/lib/useSession";

/** Resultado de la última búsqueda de horarios; `key` dice a qué filtro corresponde. */
type SlotsState = { key: string; slots: Slot[]; error: string | null };

export default function BookPage() {
  const session = useSession();
  const [services, setServices] = useState<Service[]>([]);
  const [serviceId, setServiceId] = useState("");
  const [date, setDate] = useState(todayInGuatemala());
  const [found, setFound] = useState<SlotsState>({ key: "", slots: [], error: null });
  const [reserving, setReserving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<Appointment | null>(null);

  // Si la clave del resultado no coincide con el filtro actual, seguimos buscando.
  const filterKey = `${date}|${serviceId}`;
  const loading = found.key !== filterKey;

  useEffect(() => {
    api<Service[]>("/api/booking/services")
      .then(setServices)
      .catch((caught) => setError(errorMessage(caught)));
  }, []);

  useEffect(() => {
    let stale = false;
    const query = new URLSearchParams({ date });
    if (serviceId) query.set("service_id", serviceId);

    api<Slot[]>(`/api/booking/slots?${query}`)
      .then((slots) => {
        if (!stale) setFound({ key: filterKey, slots, error: null });
      })
      .catch((caught) => {
        if (!stale) setFound({ key: filterKey, slots: [], error: errorMessage(caught) });
      });

    return () => {
      stale = true;
    };
  }, [date, serviceId, filterKey]);

  async function reserve(slot: Slot) {
    setReserving(slot.id);
    setError(null);
    try {
      const appointment = await api<Appointment>("/api/booking/appointments", {
        method: "POST",
        body: JSON.stringify({ slot_id: slot.id }),
      });
      setConfirmed(appointment);
      setFound((current) => ({
        ...current,
        slots: current.slots.filter((one) => one.id !== slot.id),
      }));
    } catch (caught) {
      setError(
        errorMessage(caught, {
          409: "Ese horario ya fue tomado.",
          404: "Ese horario ya no está disponible.",
        }),
      );
    } finally {
      setReserving(null);
    }
  }

  const shownError = error ?? found.error;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Reservar</h1>

      {session === undefined && <p className="text-sm text-stone-500">Cargando…</p>}
      {session === null && <SignInRequired />}

      {session && (
        <>
          <div className="flex flex-wrap gap-4">
            <label className="space-y-1">
              <span className="block text-sm text-stone-600">Servicio</span>
              <select
                value={serviceId}
                onChange={(event) => {
                  setServiceId(event.target.value);
                  setError(null);
                }}
                className="rounded-md border border-stone-300 bg-white px-3 py-2"
              >
                <option value="">Todos los servicios</option>
                {services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name} · {quetzales(service.price)}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="block text-sm text-stone-600">Fecha</span>
              <input
                type="date"
                value={date}
                min={todayInGuatemala()}
                onChange={(event) => {
                  setDate(event.target.value);
                  setError(null);
                }}
                className="rounded-md border border-stone-300 bg-white px-3 py-2"
              />
            </label>
          </div>

          {confirmed && (
            <div className="space-y-3 rounded-lg border border-emerald-300 bg-white p-4">
              <h2 className="text-lg font-semibold">Cita confirmada</h2>
              <p className="text-sm text-stone-700">
                {confirmed.slot.service_name} con {confirmed.slot.barber_name} ·{" "}
                {formatDateTime(confirmed.slot.starts_at)}
              </p>
              {confirmed.notification === "pending" ? (
                <Alert tone="warning">
                  Tu cita quedó guardada, pero la notificación está{" "}
                  <strong>pendiente</strong>: el servicio de avisos no respondió y se
                  reintentará solo.
                </Alert>
              ) : (
                <Alert tone="success">
                  Notificación <strong>enviada</strong>: ya tienes la confirmación.
                </Alert>
              )}
              <Link href="/appointments" className="inline-block text-sm underline">
                Ver mis citas
              </Link>
            </div>
          )}

          {shownError && <Alert>{shownError}</Alert>}

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Horarios libres</h2>
            {loading && <p className="text-sm text-stone-500">Buscando horarios…</p>}
            {!loading && !found.error && found.slots.length === 0 && (
              <p className="text-sm text-stone-500">
                No hay horarios libres para esa fecha. Prueba con otro día.
              </p>
            )}
            <ul className="space-y-2">
              {found.slots.map((slot) => (
                <li
                  key={slot.id}
                  className="flex flex-wrap items-center gap-3 rounded-lg border border-stone-200 bg-white p-3"
                >
                  <span className="w-24 font-semibold">{formatTime(slot.starts_at)}</span>
                  <span className="flex-1">
                    {slot.service_name}
                    <span className="text-stone-500"> · {slot.barber_name}</span>
                  </span>
                  <span className="text-amber-800">{quetzales(slot.price)}</span>
                  <button
                    type="button"
                    disabled={reserving !== null}
                    onClick={() => reserve(slot)}
                    className="rounded-md bg-amber-700 px-3 py-1.5 text-sm text-white hover:bg-amber-800 disabled:opacity-50"
                  >
                    {reserving === slot.id ? "Reservando…" : "Reservar"}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
