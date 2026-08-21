"""booking-svc — agenda de la barbería: servicios, barberos, horarios y citas.

Es el servicio central. Dos cosas se hacen a propósito y no se pueden simplificar:

* La reserva de un horario se decide en un solo `UPDATE ... WHERE NOT is_booked`, así
  que dos peticiones simultáneas al mismo horario dan 201 y 409, nunca dos citas.
* Si notif-svc no responde la cita se crea igual y la notificación cae al outbox, que
  un task en background reintenta cada 15s (tarea 24). Nunca un 500 por eso.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from shared.auth import CurrentUser, require_user, user_id_from_request
from shared.consul import registered
from shared.db import Database, add_health_routes
from shared.logging import CorrelationIdMiddleware, configure_logging, get_logger
from shared.resilience import ServiceCallFailed, call_service, circuit_state

SERVICE_NAME = os.getenv("SERVICE_NAME", "booking-svc")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))
USERS_SVC = "users-svc"
NOTIF_SVC = "notif-svc"
OUTBOX_INTERVAL = 15.0  # segundos entre reintentos del outbox
OUTBOX_BATCH = 20

configure_logging(SERVICE_NAME)
log = get_logger()
db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open()
    worker = asyncio.create_task(outbox_worker())
    async with registered(SERVICE_NAME, SERVICE_PORT):
        try:
            yield
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            await db.close()


app = FastAPI(title="booking-svc", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware, extract_user_id=user_id_from_request)
add_health_routes(app, db)


# ── helpers ──────────────────────────────────────────────────────────────────


def iso(value: datetime) -> str:
    """ISO-8601 en UTC terminado en Z, como pide docs/API.md."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def token_user_id(user: CurrentUser) -> int:
    """El id sale del token, nunca del cuerpo: nadie reserva a nombre de otro."""
    try:
        return int(user.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido o ausente")


SLOT_SELECT = """
    SELECT s.id, s.barber_id, b.name AS barber_name, s.service_id,
           sv.name AS service_name, s.starts_at, sv.duration_min, sv.price
      FROM slots s
      JOIN barbers b ON b.id = s.barber_id
      JOIN services sv ON sv.id = s.service_id
"""

APPOINTMENT_SELECT = """
    SELECT a.id, a.user_id, a.status, a.created_at,
           s.id AS slot_id, s.starts_at, sv.name AS service_name, b.name AS barber_name
      FROM appointments a
      JOIN slots s ON s.id = a.slot_id
      JOIN services sv ON sv.id = s.service_id
      JOIN barbers b ON b.id = s.barber_id
"""


def slot_json(row: dict) -> dict:
    return {**row, "starts_at": iso(row["starts_at"]), "price": float(row["price"])}


def appointment_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "created_at": iso(row["created_at"]),
        "slot": {
            "id": row["slot_id"],
            "starts_at": iso(row["starts_at"]),
            "service_name": row["service_name"],
            "barber_name": row["barber_name"],
        },
    }


# ── catálogo ─────────────────────────────────────────────────────────────────


@app.get("/services")
async def list_services() -> list[dict]:
    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT id, name, duration_min, price FROM services ORDER BY id")
        return [{**r, "price": float(r["price"])} for r in await cur.fetchall()]


@app.get("/barbers")
async def list_barbers() -> list[dict]:
    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT id, name, chair FROM barbers ORDER BY chair")
        return await cur.fetchall()


@app.get("/slots")
async def list_slots(
    date: date | None = None,
    service_id: int | None = None,
    barber_id: int | None = None,
) -> list[dict]:
    """Solo horarios libres y futuros. Los filtros son opcionales y acumulables."""
    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            SLOT_SELECT
            + """
             WHERE NOT s.is_booked
               AND s.starts_at > now()
               AND (%(date)s::date IS NULL
                    OR (s.starts_at AT TIME ZONE 'UTC')::date = %(date)s::date)
               AND (%(service_id)s::int IS NULL OR s.service_id = %(service_id)s::int)
               AND (%(barber_id)s::int IS NULL OR s.barber_id = %(barber_id)s::int)
             ORDER BY s.starts_at
            """,
            {"date": date, "service_id": service_id, "barber_id": barber_id},
        )
        return [slot_json(r) for r in await cur.fetchall()]


# ── citas ────────────────────────────────────────────────────────────────────


class AppointmentIn(BaseModel):
    slot_id: int


async def ensure_user_exists(user_id: int) -> None:
    """Valida al usuario por la API de users-svc: jamás leyendo users_db."""
    try:
        await call_service(USERS_SVC, "GET", f"/users/{user_id}")
    except ServiceCallFailed as exc:
        # El token es válido pero users-svc no confirma al usuario (404, o está caído).
        raise HTTPException(
            status_code=502, detail="No se pudo validar el usuario en users-svc"
        ) from exc


async def notify(appointment_id: int, payload: dict) -> str:
    """Notifica la cita; si notif-svc no responde la deja en el outbox (tarea 24)."""
    try:
        await call_service(NOTIF_SVC, "POST", "/notifications", json=payload)
        return "sent"
    except ServiceCallFailed as exc:
        # Da igual el motivo (timeout, connection refused, o que Consul ya lo
        # desregistró y no hay instancias): la cita ya está creada y se queda.
        async with db.connection() as conn:
            await conn.execute(
                "INSERT INTO outbox (appointment_id, payload, status, attempts, last_error)"
                " VALUES (%s, %s, 'pending', 1, %s)",
                (appointment_id, Jsonb(payload), str(exc)),
            )
        log.info("notification_queued", appointment_id=appointment_id, error=str(exc))
        return "pending"


@app.post("/appointments", status_code=201)
async def create_appointment(
    body: AppointmentIn, user: CurrentUser = Depends(require_user)
) -> dict:
    user_id = token_user_id(user)
    async with db.connection() as conn:
        cur = await conn.execute("SELECT id FROM slots WHERE id = %s", (body.slot_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Horario inexistente")

    await ensure_user_exists(user_id)

    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Sin carrera: el UPDATE es quien decide. Un SELECT previo dejaría hueco para
        # que dos peticiones simultáneas creyeran las dos que el horario está libre.
        await cur.execute(
            "UPDATE slots SET is_booked = true WHERE id = %s AND NOT is_booked RETURNING id",
            (body.slot_id,),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=409, detail="El horario ya está reservado")
        try:
            await cur.execute(
                "INSERT INTO appointments (user_id, slot_id, status)"
                " VALUES (%s, %s, 'confirmed') RETURNING id",
                (user_id, body.slot_id),
            )
        except psycopg.errors.UniqueViolation as exc:
            # slot_id es UNIQUE y la fila de una cita cancelada no se borra: reservar de
            # nuevo ese horario choca aquí, no en el UPDATE. Ver la nota del PR.
            raise HTTPException(
                status_code=409, detail="El horario ya tiene una cita"
            ) from exc
        appointment_id = (await cur.fetchone())["id"]
        await cur.execute(APPOINTMENT_SELECT + " WHERE a.id = %s", (appointment_id,))
        appointment = appointment_json(await cur.fetchone())

    slot = appointment["slot"]
    notification = await notify(
        appointment["id"],
        {
            "user_id": user_id,
            "subject": "Cita confirmada",
            "body": f"Tu {slot['service_name']} con {slot['barber_name']}"
            f" es el {slot['starts_at']}",
            "channel": "log",
        },
    )
    return {**appointment, "notification": notification}


@app.get("/appointments")
async def list_appointments(
    status: str | None = Query(None, pattern="^(confirmed|cancelled)$"),
    user: CurrentUser = Depends(require_user),
) -> list[dict]:
    """Solo las citas del usuario del token, más recientes primero."""
    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            APPOINTMENT_SELECT
            + """
             WHERE a.user_id = %(user_id)s
               AND (%(status)s::text IS NULL OR a.status = %(status)s::text)
             ORDER BY a.created_at DESC, a.id DESC
            """,
            {"user_id": token_user_id(user), "status": status},
        )
        return [appointment_json(r) for r in await cur.fetchall()]


@app.get("/appointments/{appointment_id}")
async def get_appointment(
    appointment_id: int, user: CurrentUser = Depends(require_user)
) -> dict:
    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(APPOINTMENT_SELECT + " WHERE a.id = %s", (appointment_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Cita inexistente")
    if row["user_id"] != token_user_id(user):
        raise HTTPException(status_code=403, detail="La cita es de otro usuario")
    return appointment_json(row)


@app.delete("/appointments/{appointment_id}")
async def cancel_appointment(
    appointment_id: int, user: CurrentUser = Depends(require_user)
) -> dict:
    user_id = token_user_id(user)
    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # FOR UPDATE: dos DELETE simultáneos no pueden liberar el horario dos veces.
        await cur.execute(
            "SELECT user_id, status, slot_id FROM appointments WHERE id = %s FOR UPDATE",
            (appointment_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Cita inexistente")
        if row["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="La cita es de otro usuario")
        if row["status"] == "cancelled":
            raise HTTPException(status_code=409, detail="La cita ya estaba cancelada")
        # Una sola transacción: cancelar y liberar el horario no pueden quedar a medias.
        await cur.execute(
            "UPDATE appointments SET status = 'cancelled', cancelled_at = now() WHERE id = %s",
            (appointment_id,),
        )
        await cur.execute(
            "UPDATE slots SET is_booked = false WHERE id = %s", (row["slot_id"],)
        )
    return {"id": appointment_id, "status": "cancelled"}


# ── outbox y estado del circuito ─────────────────────────────────────────────


async def flush_outbox() -> None:
    """Reintenta las notificaciones pendientes.

    Con el breaker abierto cada envío falla al instante y sin llegar a la red: es lo
    esperado mientras notif-svc está caído, no un error.
    """
    async with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT id, payload FROM outbox WHERE status = 'pending' ORDER BY id LIMIT %s",
            (OUTBOX_BATCH,),
        )
        pending = await cur.fetchall()

    # La conexión se suelta antes de enviar: cada envío puede llevarse sus 3 reintentos
    # de 2s y no tiene por qué retener una del pool mientras tanto.
    for row in pending:
        try:
            await call_service(NOTIF_SVC, "POST", "/notifications", json=row["payload"])
            sql = ("UPDATE outbox SET status = 'sent', sent_at = now(),"
                   " attempts = attempts + 1, last_error = NULL WHERE id = %s")
            params: tuple = (row["id"],)
        except ServiceCallFailed as exc:
            sql = "UPDATE outbox SET attempts = attempts + 1, last_error = %s WHERE id = %s"
            params = (str(exc), row["id"])
        async with db.connection() as conn:
            await conn.execute(sql, params)


async def outbox_worker() -> None:
    """Task del lifespan: vacía el outbox cada 15s. Ningún fallo puede matarlo.

    ponytail: un solo proceso lo recorre en serie, así que no hace falta bloquear las
    filas; con varias réplicas de booking-svc haría falta FOR UPDATE SKIP LOCKED.
    """
    while True:
        await asyncio.sleep(OUTBOX_INTERVAL)
        try:
            await flush_outbox()
        except Exception as exc:
            log.warning("outbox_flush_failed", error=f"{type(exc).__name__}: {exc}")


@app.get("/admin/circuit")
async def admin_circuit() -> dict:
    """Estado del breaker hacia notif-svc y pendientes del outbox (tarea 25)."""
    async with db.connection() as conn:
        cur = await conn.execute("SELECT count(*) FROM outbox WHERE status = 'pending'")
        (pending,) = await cur.fetchone()
    return {
        "target": NOTIF_SVC,
        **circuit_state(NOTIF_SVC),
        "outbox_pending": pending,
    }
