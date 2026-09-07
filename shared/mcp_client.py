"""Cliente MCP mínimo para llamar a `barberflow-mcp` desde los agentes A2A.

Cada llamada abre su propia sesión MCP (initialize + tools/call) y la cierra:
para el volumen de esta demo es más simple y seguro que mantener una sesión
persistente compartida entre requests concurrentes de distintos agentes.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from shared.consul import discover
from shared.logging import correlation_headers

MCP_SERVICE_NAME = "barberflow-mcp"


class McpToolFailed(Exception):
    """La tool respondió `isError` o el resultado no se pudo interpretar."""


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Llama a una tool de barberflow-mcp y devuelve su resultado ya parseado.

    Prefiere `structured_content` (lo trae `get_available_slots` y
    `get_notifications`, que devuelven `list[dict]`); si no está —como en
    `create_booking`/`cancel_booking`, que devuelven un `dict` suelto y el SDK
    no les arma schema de salida— cae al primer bloque de texto, que es el
    mismo dict serializado a JSON.
    """
    base_url = await discover(MCP_SERVICE_NAME)
    # Mismo `x-correlation-id` del request en curso (ver shared/resilience.py):
    # sin esto, cada salto A2A -> MCP -> microservicio generaría el suyo propio
    # y la tarea 27/36 no podría seguir el viaje completo en los logs.
    async with httpx.AsyncClient(headers=correlation_headers()) as http_client:
        async with streamable_http_client(f"{base_url}/mcp", http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments or {})

    if result.is_error:
        detail = result.content[0].text if result.content else "error sin detalle"
        raise McpToolFailed(f"{name} -> {detail}")

    if result.structured_content is not None:
        payload = result.structured_content
        # Las tools que devuelven list[dict] se envuelven como {"result": [...]}.
        return payload.get("result", payload) if isinstance(payload, dict) else payload

    if result.content:
        return json.loads(result.content[0].text)

    raise McpToolFailed(f"{name} no devolvió contenido")
