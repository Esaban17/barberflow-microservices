"""barberflow-mcp — expone BarberFlow a agentes de IA vía MCP (tareas 28-31).

No tiene base de datos propia: es un cliente más de users-svc/booking-svc/
notif-svc, igual que el resto de BarberFlow (llama por su API, nunca lee su
BD). La identidad con la que opera es un único "usuario demo" (tarea 29):
se loguea una vez contra users-svc con DEMO_USER_EMAIL/DEMO_USER_PASSWORD,
cachea el JWT, y vuelve a loguearse si una llamada responde 401 (token
expirado o rotado).

mcp==2.0.0 no trae `FastMCP` (ver docs/a2a-mcp-api-notes.md): la clase real
es `MCPServer` en `mcp.server.mcpserver`. Se monta como sub-app dentro de un
FastAPI normal para reutilizar `shared/db.add_health_routes` y
`shared/logging.CorrelationIdMiddleware` igual que los otros tres servicios,
en vez de dejar que `MCPServer.run()` arranque su propio servidor.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer

from shared.consul import registered
from shared.db import add_health_routes
from shared.logging import CorrelationIdMiddleware, configure_logging, get_logger
from shared.resilience import ServiceCallFailed, call_service

SERVICE_NAME = os.getenv("SERVICE_NAME", "barberflow-mcp")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
USERS_SVC = "users-svc"
BOOKING_SVC = "booking-svc"
NOTIF_SVC = "notif-svc"

configure_logging(SERVICE_NAME)
log = get_logger()

mcp_server = MCPServer(
    name="barberflow-mcp",
    version="1.0.0",
    instructions=(
        "Agenda y notifica citas de la barbería BarberFlow. Llama primero a "
        "get_available_slots para obtener un slot_id válido antes de create_booking."
    ),
)


# ── identidad del usuario demo (tarea 29) ───────────────────────────────────


class DemoIdentity:
    """Token del usuario demo: se cachea y se renueva solo ante un 401."""

    def __init__(self) -> None:
        self._token: str | None = None

    async def _login(self) -> str:
        response = await call_service(
            USERS_SVC,
            "POST",
            "/login",
            json={
                "email": os.environ["DEMO_USER_EMAIL"],
                "password": os.environ["DEMO_USER_PASSWORD"],
            },
        )
        self._token = response.json()["access_token"]
        log.info("mcp_demo_login")
        return self._token

    async def headers(self, *, force: bool = False) -> dict[str, str]:
        if force or self._token is None:
            await self._login()
        return {"Authorization": f"Bearer {self._token}"}


identity = DemoIdentity()


async def call_as_demo(service: str, method: str, path: str, **kwargs) -> httpx.Response:
    """Como `call_service`, pero autenticado como el usuario demo.

    Un 401 (token vencido o el demo user rotado) relogina una sola vez y
    reintenta; cualquier otro fallo sube tal cual.
    """
    try:
        return await call_service(service, method, path, headers=await identity.headers(), **kwargs)
    except ServiceCallFailed as exc:
        if "-> 401" not in str(exc):
            raise
        log.info("mcp_demo_relogin", reason=str(exc))
        return await call_service(
            service, method, path, headers=await identity.headers(force=True), **kwargs
        )


# ── tools (tareas 30-31) ─────────────────────────────────────────────────────


@mcp_server.tool()
async def get_available_slots(
    date: str | None = None,
    service_id: int | None = None,
    barber_id: int | None = None,
) -> list[dict]:
    """Lista horarios libres y futuros de la barbería.

    `date` en formato YYYY-MM-DD. Los tres filtros son opcionales y se pueden
    combinar. Úsala antes de `create_booking` para obtener un `slot_id` válido.
    """
    params = {
        k: v
        for k, v in {"date": date, "service_id": service_id, "barber_id": barber_id}.items()
        if v is not None
    }
    response = await call_service(BOOKING_SVC, "GET", "/slots", params=params)
    return response.json()


@mcp_server.tool()
async def create_booking(slot_id: int) -> dict:
    """Reserva un horario (un `slot_id` de `get_available_slots`) para el usuario demo.

    Devuelve la cita creada. Si notif-svc no responde, la cita se crea igual
    y el campo `notification` viene en `"pending"` en vez de fallar.
    """
    response = await call_as_demo(BOOKING_SVC, "POST", "/appointments", json={"slot_id": slot_id})
    return response.json()


@mcp_server.tool()
async def cancel_booking(appointment_id: int) -> dict:
    """Cancela una cita del usuario demo y libera su horario."""
    response = await call_as_demo(BOOKING_SVC, "DELETE", f"/appointments/{appointment_id}")
    return response.json()


@mcp_server.tool()
async def send_notification(user_id: int, subject: str, body: str, channel: str = "log") -> dict:
    """Envía una notificación a un usuario (el envío real se simula con un log estructurado)."""
    response = await call_service(
        NOTIF_SVC,
        "POST",
        "/notifications",
        json={"user_id": user_id, "subject": subject, "body": body, "channel": channel},
    )
    return response.json()


@mcp_server.tool()
async def get_notifications(user_id: int) -> list[dict]:
    """Historial de notificaciones enviadas a un usuario, más recientes primero."""
    response = await call_service(NOTIF_SVC, "GET", "/notifications", params={"user_id": user_id})
    return response.json()


# ── app FastAPI: MCP montado en /mcp + salud + Consul ───────────────────────

mcp_app = mcp_server.streamable_http_app(host="0.0.0.0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El sub-app de streamable_http_app trae su propio lifespan (arranca el
    # gestor de sesiones); Starlette no lo propaga solo por montarlo con
    # `app.mount()`, así que hay que entrar a su lifespan_context a mano.
    async with registered(SERVICE_NAME, SERVICE_PORT):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield


app = FastAPI(title="barberflow-mcp", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
add_health_routes(app)  # sin `db`: este servicio no tiene base de datos propia
# Montado en la raíz: streamable_http_app() ya sirve en su propio "/mcp" interno
# (streamable_http_path, por defecto "/mcp"); montarlo también en "/mcp" duplicaría
# el prefijo ("/mcp/mcp"). add_health_routes() se registró antes, así que /healthz
# y /readyz siguen resolviendo ahí y no caen en este mount.
app.mount("/", mcp_app)
