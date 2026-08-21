"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert } from "@/components/Alert";
import { SignInRequired } from "@/components/SignInRequired";
import { api, errorMessage, type Appointment } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/useSession";

type ListState = { loaded: boolean; appointments: Appointment[]; error: string | null };

export default function AppointmentsPage() {
  const session = useSession();
  const [list, setList] = useState<ListState>({
    loaded: false,
    appointments: [],
    error: null,
  });
  // Se incrementa tras cancelar para volver a pedir la lista al servicio.
  const [reloads, setReloads] = useState(0);
  const [cancelling, setCancelling] = useState<number | null>(null);

  useEffect(() => {
    if (!session) return;
    let stale = false;

    api<Appointment[]>("/api/booking/appointments")
      .then((appointments) => {
        if (!stale) setList({ loaded: true, appointments, error: null });
      })
      .catch((caught) => {
        if (!stale) {
          setList({ loaded: true, appointments: [], error: errorMessage(caught) });
        }
      });

    return () => {
      stale = true;
    };
  }, [session, reloads]);

  async function cancel(appointment: Appointment) {
    setCancelling(appointment.id);
    try {
      await api(`/api/booking/appointments/${appointment.id}`, { method: "DELETE" });
      // Cancelar libera el slot en booking-svc; recargamos para verlo reflejado.
      setReloads((count) => count + 1);
    } catch (caught) {
      setList((current) => ({
        ...current,
        error: errorMessage(caught, {
          409: "Esa cita ya estaba cancelada.",
          403: "Esa cita no es tuya.",
          404: "Esa cita ya no existe.",
        }),
      }));
    } finally {
      setCancelling(null);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Mis citas</h1>

      {session === undefined && <p className="text-sm text-stone-500">Cargando…</p>}
      {session === null && <SignInRequired />}

      {session && (
        <>
          {list.error && <Alert>{list.error}</Alert>}
          {!list.loaded && <p className="text-sm text-stone-500">Cargando tus citas…</p>}
          {list.loaded && !list.error && list.appointments.length === 0 && (
            <p className="text-sm text-stone-500">
              Todavía no tienes citas.{" "}
              <Link href="/book" className="underline">
                Reserva una
              </Link>
              .
            </p>
          )}
          <ul className="space-y-2">
            {list.appointments.map((appointment) => (
              <li
                key={appointment.id}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-stone-200 bg-white p-3"
              >
                <div className="flex-1">
                  <p className="font-medium">
                    {appointment.slot.service_name}
                    <span className="text-stone-500">
                      {" "}
                      · {appointment.slot.barber_name}
                    </span>
                  </p>
                  <p className="text-sm text-stone-600">
                    {formatDateTime(appointment.slot.starts_at)}
                  </p>
                </div>
                {appointment.status === "cancelled" ? (
                  <span className="rounded-md bg-stone-100 px-3 py-1 text-sm text-stone-500">
                    Cancelada
                  </span>
                ) : (
                  <button
                    type="button"
                    disabled={cancelling !== null}
                    onClick={() => cancel(appointment)}
                    className="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                  >
                    {cancelling === appointment.id ? "Cancelando…" : "Cancelar"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
