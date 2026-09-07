"""notification-agent :9002 — envía notificaciones de BarberFlow por A2A (tarea 34).

Misma forma que booking-agent (tarea 33): Agent Card en las dos rutas de
siempre, y la única skill llama a la tool `send_notification` de
`barberflow-mcp` en vez de hablarle directo a notif-svc.

Como el usuario demo (el que opera todo el MCP server) es el user_id=1, si el
mensaje no trae uno explícito se asume ese — es quien está detrás de toda la
demo de agentes.
"""

from __future__ import annotations

import os
import re
import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part, Role
from a2a.utils.constants import TransportProtocol

from shared.a2a_app import build_a2a_app
from shared.logging import get_logger
from shared.mcp_client import McpToolFailed, call_tool

SERVICE_NAME = os.getenv("SERVICE_NAME", "notification-agent")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "9002"))
SERVICE_ADDRESS = os.getenv("SERVICE_ADDRESS", "notification-agent")
DEFAULT_USER_ID = int(os.getenv("DEFAULT_NOTIFY_USER_ID", "1"))

log = get_logger()


def _agent_text_message(text: str) -> Message:
    return Message(message_id=str(uuid.uuid4()), role=Role.ROLE_AGENT, parts=[Part(text=text)])


def _extract_user_id(text: str) -> int:
    match = re.search(r"usuario\s+(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else DEFAULT_USER_ID


class NotificationAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        text = context.get_user_input()
        log.info("notification_agent_request", text=text)
        user_id = _extract_user_id(text)
        try:
            result = await call_tool(
                "send_notification",
                {
                    "user_id": user_id,
                    "subject": "Aviso de BarberFlow",
                    "body": text,
                    "channel": "log",
                },
            )
            reply = f"Notificación {result['id']} enviada a usuario {user_id}: {result['status']}."
        except McpToolFailed as exc:
            log.warning("notification_agent_mcp_failed", error=str(exc))
            reply = f"No pude enviar la notificación: {exc}"

        await event_queue.enqueue_event(_agent_text_message(reply))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


AGENT_CARD = AgentCard(
    name="notification-agent",
    description="Envía notificaciones a usuarios de BarberFlow por delegación A2A.",
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
            id="send_notification",
            name="send_notification",
            description="Envía una notificación a un usuario de BarberFlow.",
            tags=["notification", "send_notification"],
            examples=["Avísale al usuario 1 que su cita fue confirmada"],
        ),
    ],
)

app = build_a2a_app(
    service_name=SERVICE_NAME,
    service_port=SERVICE_PORT,
    agent_card=AGENT_CARD,
    executor=NotificationAgentExecutor(),
)
