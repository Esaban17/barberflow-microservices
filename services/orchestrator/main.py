"""orchestrator :9000 — interpreta una instrucción y delega en los agentes A2A (tarea 35).

Flujo: `POST /instruct {"text": "..."}` ->
  1. Descubre los agentes de `AGENT_URLS` (sus Agent Cards, no Consul: los
     agentes A2A no están en el contrato REST de `docs/API.md` y esto es
     justamente lo que pide el enunciado: "descarga las cards y elige por
     skills").
  2. Decide qué skill(s) aplican a la instrucción. Con `ANTHROPIC_API_KEY`
     configurada se lo pregunta a Claude; sin ella —o si Claude falla— cae a
     un parser por palabras clave, para que la demo nunca dependa de la red
     ni de una API key (tarea 35, nota de ejecución).
  3. Llama a cada agente elegido por A2A (`message/send`) y agrega las
     respuestas. Si se pidió reservar y notificar, el resultado de la reserva
     se inyecta en el texto que recibe notification-agent, para que la
     notificación no sea genérica sino que cite la cita real creada.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from a2a.client.client import ClientConfig
from a2a.client.client_factory import create_client
from a2a.types import Message, Part, Role, SendMessageRequest

from shared.consul import registered
from shared.db import add_health_routes
from shared.logging import (
    CorrelationIdMiddleware,
    configure_logging,
    correlation_headers,
    get_logger,
)

SERVICE_NAME = os.getenv("SERVICE_NAME", "orchestrator")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "9000"))
CARD_TIMEOUT = 3.0

configure_logging(SERVICE_NAME)
log = get_logger()


@dataclass
class AgentInfo:
    url: str
    skills: list[dict]  # [{"id", "name", "description", "tags"}, ...]


# ── descubrimiento de agentes por su Agent Card ─────────────────────────────


async def discover_agents() -> list[AgentInfo]:
    """Lee AGENT_URLS y descarga la Agent Card de cada uno."""
    raw = os.environ.get("AGENT_URLS", "")
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    agents: list[AgentInfo] = []
    async with httpx.AsyncClient(timeout=CARD_TIMEOUT) as client:
        for url in urls:
            try:
                response = await client.get(f"{url}/.well-known/agent-card.json")
                response.raise_for_status()
                card = response.json()
                agents.append(AgentInfo(url=url, skills=card.get("skills", [])))
            except httpx.HTTPError as exc:
                log.warning("orchestrator_agent_card_unreachable", url=url, error=str(exc))
    return agents


def agent_for_skill(agents: list[AgentInfo], skill_id: str) -> AgentInfo | None:
    for agent in agents:
        for skill in agent.skills:
            if skill["id"] == skill_id or skill_id in skill.get("tags", []):
                return agent
    return None


# ── interpretación de la instrucción ─────────────────────────────────────────

# skill -> (palabras clave, para el fallback sin ANTHROPIC_API_KEY)
_KEYWORDS = {
    "create_booking": ["resery", "resérv", "reserv", "agenda", "agénda", "cita"],
    "cancel_booking": ["cancela", "cancelar"],
    "send_notification": ["avis", "avís", "notif"],
}


def keyword_plan(text: str) -> list[str]:
    """Fallback sin LLM: qué skills aplican, por presencia de palabras clave."""
    text_low = text.lower()
    plan = []
    if any(k in text_low for k in _KEYWORDS["cancel_booking"]):
        plan.append("cancel_booking")
    elif any(k in text_low for k in _KEYWORDS["create_booking"]):
        plan.append("create_booking")
    if any(k in text_low for k in _KEYWORDS["send_notification"]):
        plan.append("send_notification")
    return plan


async def llm_plan(text: str, agents: list[AgentInfo]) -> list[str] | None:
    """Le pregunta a Claude qué skills aplican. None si no hay key o algo falla."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic  # import perezoso: no debe fallar el arranque sin la key

        skills_catalog = [
            {"id": s["id"], "description": s.get("description", "")}
            for agent in agents
            for s in agent.skills
        ]
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "Estas son las skills disponibles (id y descripción), en JSON: "
                    f"{json.dumps(skills_catalog, ensure_ascii=False)}\n\n"
                    f"Instrucción del usuario: {text!r}\n\n"
                    "Responde ÚNICAMENTE un array JSON con los ids de las skills que "
                    "aplican, en el orden en que deben ejecutarse (por ejemplo si hay que "
                    "reservar y luego avisar, primero la de reservar). Sin texto extra."
                ),
            }],
        )
        raw = response.content[0].text.strip()
        plan = json.loads(raw)
        if isinstance(plan, list) and all(isinstance(s, str) for s in plan):
            return plan
    except Exception as exc:  # cualquier fallo del LLM cae al parser por keywords
        log.warning("orchestrator_llm_failed", error=str(exc))
    return None


async def build_plan(text: str, agents: list[AgentInfo]) -> tuple[list[str], str]:
    plan = await llm_plan(text, agents)
    if plan:
        return plan, "llm"
    return keyword_plan(text), "keywords"


# ── llamar a un agente por A2A ───────────────────────────────────────────────


async def send_to_agent(agent_url: str, text: str) -> str:
    """message/send al agente; devuelve el texto de su respuesta.

    Propaga el mismo `x-correlation-id` del request que llegó a /instruct: sin
    esto, cada agente vería un id distinto y la tarea 36 no podría mostrar la
    delegación paso a paso en los logs.
    """
    http_client = httpx.AsyncClient(headers=correlation_headers())
    client = await create_client(agent_url, client_config=ClientConfig(httpx_client=http_client))
    message = Message(message_id=str(uuid.uuid4()), role=Role.ROLE_USER, parts=[Part(text=text)])
    request = SendMessageRequest(message=message)
    reply_text = ""
    async for response in client.send_message(request):
        if response.HasField("message"):
            reply_text = "".join(p.text for p in response.message.parts if p.text)
    return reply_text or "(el agente no devolvió texto)"


# ── app HTTP ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with registered(SERVICE_NAME, SERVICE_PORT):
        yield


app = FastAPI(title="orchestrator", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
add_health_routes(app)


class InstructionIn(BaseModel):
    text: str


@app.post("/instruct")
async def instruct(body: InstructionIn) -> dict:
    agents = await discover_agents()
    if not agents:
        raise HTTPException(status_code=503, detail="Ningún agente A2A disponible (AGENT_URLS)")

    plan, plan_source = await build_plan(body.text, agents)
    log.info("orchestrator_plan", text=body.text, plan=plan, source=plan_source)

    steps: list[dict] = []
    booking_reply: str | None = None
    for skill_id in plan:
        agent = agent_for_skill(agents, skill_id)
        if agent is None:
            steps.append({"skill": skill_id, "error": "ningún agente expone esta skill"})
            continue

        step_text = body.text
        if skill_id == "send_notification" and booking_reply:
            step_text = f"{body.text}. Resultado de la reserva: {booking_reply}"

        reply = await send_to_agent(agent.url, step_text)
        if skill_id == "create_booking":
            booking_reply = reply
        steps.append({"skill": skill_id, "agent": agent.url, "reply": reply})

    return {"plan_source": plan_source, "plan": plan, "steps": steps}
