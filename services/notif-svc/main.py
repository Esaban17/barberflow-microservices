"""notif-svc: persiste notificaciones y simula el envío con un log estructurado.

El "envío" real no existe todavía (el PDF lo permite: *"puede ser solo un log por
ahora"*). Lo que sí es real es la traza: cada fila guarda el `correlation_id` del
request que la originó.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg.rows import dict_row
from pydantic import BaseModel

from shared.auth import user_id_from_request
from shared.consul import registered
from shared.db import Database, add_health_routes
from shared.logging import (
    CorrelationIdMiddleware,
    configure_logging,
    get_correlation_id,
    get_logger,
)

SERVICE_NAME = os.getenv("SERVICE_NAME", "notif-svc")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8002"))

configure_logging(SERVICE_NAME)
log = get_logger()
db = Database()


class NotificationIn(BaseModel):
    user_id: int
    subject: str
    body: str
    channel: str = "log"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open()
    try:
        async with registered(SERVICE_NAME, SERVICE_PORT):
            yield
    finally:
        await db.close()


app = FastAPI(title="notif-svc", lifespan=lifespan)
# Este servicio no exige token, pero si llega uno el user_id debe salir en los logs.
app.add_middleware(CorrelationIdMiddleware, extract_user_id=user_id_from_request)
add_health_routes(app, db)


@app.post("/notifications", status_code=201)
async def create_notification(payload: NotificationIn) -> dict:
    async with db.connection() as conn:
        # `correlation_id` se guarda pero no se devuelve: es para los logs, no para la API.
        cur = await conn.cursor(row_factory=dict_row).execute(
            """INSERT INTO notifications (user_id, channel, subject, body, correlation_id)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, user_id, subject, body, channel, status, created_at""",
            (
                payload.user_id,
                payload.channel,
                payload.subject,
                payload.body,
                get_correlation_id(),
            ),
        )
        row = await cur.fetchone()

    # El envío simulado: una línea estructurada con el correlation_id del contexto.
    log.info(
        "notification_sent",
        notification_id=row["id"],
        user_id=row["user_id"],
        channel=row["channel"],
        subject=row["subject"],
    )
    return row


@app.get("/notifications")
async def list_notifications(user_id: int) -> list[dict]:
    """`user_id` sin default: si falta, FastAPI responde 422 solo."""
    async with db.connection() as conn:
        cur = await conn.cursor(row_factory=dict_row).execute(
            """SELECT id, user_id, subject, body, channel, status, created_at
               FROM notifications WHERE user_id = %s
               ORDER BY created_at DESC, id DESC""",
            (user_id,),
        )
        return await cur.fetchall()
