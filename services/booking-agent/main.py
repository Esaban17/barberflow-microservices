"""booking-agent :9001 — agenda y cancela citas de BarberFlow por A2A (tarea 33).

Su Agent Card se sirve en /.well-known/agent-card.json y /.well-known/agent.json
(ver docs/a2a-mcp-api-notes.md). La lógica no toca users-svc/booking-svc
directamente: sus dos skills llaman a las tools de `barberflow-mcp`
(`shared/mcp_client.call_tool`), igual que pide el enunciado ("skills vía MCP").

Interpretación de la instrucción en lenguaje natural: nada de LLM aquí —eso es
trabajo del `orchestrator` (tarea 35)—, solo un matching simple de día de la
semana + palabras del nombre del servicio contra los slots libres que ya trae
`get_available_slots`. Es intencionalmente simple: el objetivo de la tarea es
demostrar la delegación A2A -> MCP -> microservicio, no un NLU sofisticado.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import date, timedelta

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part, Role
from a2a.utils.constants import TransportProtocol

from shared.a2a_app import build_a2a_app
from shared.logging import get_logger
from shared.mcp_client import McpToolFailed, call_tool

SERVICE_NAME = os.getenv("SERVICE_NAME", "booking-agent")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "9001"))
SERVICE_ADDRESS = os.getenv("SERVICE_ADDRESS", "booking-agent")

log = get_logger()

_WEEKDAYS = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}


def _agent_text_message(text: str) -> Message:
    return Message(message_id=str(uuid.uuid4()), role=Role.ROLE_AGENT, parts=[Part(text=text)])


def _next_weekday(text_low: str) -> date | None:
    """Próxima fecha (hoy incluido) que caiga en el día de semana mencionado."""
    if "hoy" in text_low:
        return date.today()
    if "mañana" in text_low or "manana" in text_low:
        return date.today() + timedelta(days=1)
    for name, target in _WEEKDAYS.items():
        if name in text_low:
            today = date.today()
            delta = (target - today.weekday()) % 7
            return today + timedelta(days=delta)
    return None


def _pick_slot(slots: list[dict], text: str) -> dict | None:
    """Elige el slot libre que mejor coincide con el texto: día + palabras del servicio."""
    text_low = text.lower()
    candidates = slots
    target_date = _next_weekday(text_low)
    if target_date is not None:
        same_day = [s for s in candidates if s["starts_at"].startswith(target_date.isoformat())]
        if same_day:
            candidates = same_day

    def score(slot: dict) -> int:
        words = set(re.findall(r"[a-záéíóúñ]+", slot["service_name"].lower()))
        return sum(1 for w in words if len(w) > 3 and w in text_low)

    ranked = sorted(candidates, key=lambda s: (-score(s), s["starts_at"]))
    return ranked[0] if ranked else None


class BookingAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        text = context.get_user_input()
        log.info("booking_agent_request", text=text)

        cancel_match = re.search(r"cancel\w*.*?(\d+)", text, re.IGNORECASE)
        try:
            if cancel_match:
                appointment_id = int(cancel_match.group(1))
                result = await call_tool("cancel_booking", {"appointment_id": appointment_id})
                reply = f"Cita {result['id']} cancelada."
            else:
                slots = await call_tool("get_available_slots", {})
                slot = _pick_slot(slots, text)
                if slot is None:
                    await event_queue.enqueue_event(
                        _agent_text_message("No encontré un horario disponible que coincida con tu pedido.")
                    )
                    return
                booking = await call_tool("create_booking", {"slot_id": slot["id"]})
                reply = (
                    f"Cita creada: {booking['slot']['service_name']} con "
                    f"{booking['slot']['barber_name']} el {booking['slot']['starts_at']} "
                    f"(id {booking['id']}, notificación: {booking['notification']})."
                )
        except McpToolFailed as exc:
            log.warning("booking_agent_mcp_failed", error=str(exc))
            reply = f"No pude completar la solicitud: {exc}"

        await event_queue.enqueue_event(_agent_text_message(reply))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # No hay tareas de larga duración que cancelar: cada request es síncrono.
        pass


AGENT_CARD = AgentCard(
    name="booking-agent",
    description="Agenda y cancela citas de la barbería BarberFlow por delegación A2A.",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=False),
    supported_interfaces=[
        AgentInterface(
            url=f"http://{SERVICE_ADDRESS}:{SERVICE_PORT}",
            protocol_binding=TransportProtocol.JSONRPC,
        ),
    ],
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="create_booking",
            name="create_booking",
            description=(
                "Reserva un horario de la barbería a partir de una instrucción en "
                "lenguaje natural (día de la semana + tipo de servicio)."
            ),
            tags=["booking", "create_booking"],
            examples=["Resérvame un corte + barba el viernes"],
        ),
        AgentSkill(
            id="cancel_booking",
            name="cancel_booking",
            description="Cancela una cita existente dado su id.",
            tags=["booking", "cancel_booking"],
            examples=["Cancela la cita 5"],
        ),
    ],
)

app = build_a2a_app(
    service_name=SERVICE_NAME,
    service_port=SERVICE_PORT,
    agent_card=AGENT_CARD,
    executor=BookingAgentExecutor(),
)
