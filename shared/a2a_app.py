"""Boilerplate común para exponer un `AgentExecutor` como servicio A2A (tareas 33-34).

Cada agente solo escribe su `AgentCard` y su `AgentExecutor`; esto arma el
FastAPI con Consul, salud, logging con correlation_id y las rutas A2A
(Agent Card en las dos rutas que pide el enunciado + JSON-RPC en "/"),
igual que `shared/db.py` y `shared/logging.py` hacen para los tres
microservicios REST.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from fastapi import FastAPI

from shared.consul import registered
from shared.db import add_health_routes
from shared.logging import CorrelationIdMiddleware, configure_logging


def build_a2a_app(
    *,
    service_name: str,
    service_port: int,
    agent_card: AgentCard,
    executor: AgentExecutor,
) -> FastAPI:
    """Arma el FastAPI de un agente A2A: Consul, salud, logs y rutas del protocolo."""
    configure_logging(service_name)

    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with registered(service_name, service_port):
            yield

    app = FastAPI(title=service_name, lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    add_health_routes(app)  # sin `db`: los agentes no tienen base de datos propia

    add_a2a_routes_to_fastapi(
        app,
        # Las dos rutas que pide el enunciado: agent-card.json es la que trae el
        # SDK por defecto, agent.json es compatibilidad con clientes A2A viejos
        # (ver docs/a2a-mcp-api-notes.md).
        agent_card_routes=[
            *create_agent_card_routes(agent_card, card_url="/.well-known/agent-card.json"),
            *create_agent_card_routes(agent_card, card_url="/.well-known/agent.json"),
        ],
        jsonrpc_routes=create_jsonrpc_routes(request_handler, rpc_url="/"),
    )
    return app
