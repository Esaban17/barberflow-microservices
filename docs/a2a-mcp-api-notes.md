# API real de `a2a-sdk==1.1.2` y `mcp==2.0.0`

**Tarea 3.** Estas firmas se sacaron instalando ambos paquetes en un venv limpio
(`pip install a2a-sdk==1.1.2 mcp==2.0.0`) e inspeccionando el código fuente
instalado, no de memoria ni de la documentación pública (que describe versiones
distintas de los dos SDKs). Sirve como referencia para las tareas 28-36.

---

## `mcp==2.0.0`

### Hallazgo principal: no existe `FastMCP`

La clase que en las versiones 1.x del SDK se llamaba `FastMCP`
(`from mcp.server.fastmcp import FastMCP`) en `2.0.0` se renombró a
**`MCPServer`** y vive en `mcp.server.mcpserver`:

```python
from mcp.server.mcpserver import MCPServer

server = MCPServer(name="barberflow-mcp", version="1.0.0")
```

`mcp.server.fastmcp` **no existe** en este paquete — cualquier código o tutorial
que lo importe está escrito para una versión distinta y no corre contra
`mcp==2.0.0`.

### Registrar tools

```python
@server.tool()
async def get_available_slots(date: str | None = None) -> list[dict]:
    """Docstring: se usa como descripción de la tool ante el LLM."""
    ...
```

`tool()` acepta `name`, `title`, `description`, `annotations`, `meta`,
`structured_output` — todos opcionales. Si el parámetro tiene el tipo
`Context` (de `mcp.server.mcpserver`), el framework lo inyecta con acceso a
logging/progreso.

### Levantar con streamable-http

```python
server.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

`run()` es **síncrono** (usa `anyio.run` internamente) y acepta
`"stdio" | "sse" | "streamable-http"`. Para montarlo dentro de una app ASGI
existente en vez de dejar que `run()` arranque su propio servidor:

```python
app = server.streamable_http_app(...)  # Starlette app montable
```

### Config de Claude Desktop (tarea 32)

Con streamable-http el servidor ya es un endpoint HTTP normal
(`http://localhost:8000/mcp` por defecto), así que la entrada en
`claude_desktop_config.json` no usa `command`/`args` como un server stdio, sino
un adaptador que hable HTTP. La opción que funciona sin escribir código propio
es `mcp-remote` (paquete npm, actúa de puente stdio↔HTTP):

```jsonc
{
  "mcpServers": {
    "barberflow": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/mcp"]
    }
  }
}
```

Alternativa para un contenedor Docker corriendo el server: `docker exec -i
barberflow-mcp <script-stdio>` solo sirve si el proceso dentro del contenedor
habla stdio; como aquí corre streamable-http, la vía de `mcp-remote` apuntando
al puerto publicado es la que aplica.

---

## `a2a-sdk==1.1.2`

### Hallazgo principal: los tipos son Protocol Buffers, no Pydantic

`a2a.types.AgentCard`, `AgentSkill`, `AgentCapabilities`, `Message`, etc. son
clases generadas por protobuf (`a2a.types.a2a_pb2`), reexportadas desde
`a2a.types`. Se construyen con kwargs igual que un modelo normal:

```python
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

card = AgentCard(
    name="booking-agent",
    description="Agenda citas de BarberFlow",
    url="http://booking-agent:9001",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=False),
    skills=[
        AgentSkill(id="create_booking", name="create_booking",
                    description="Crea una cita", tags=["booking"]),
    ],
)
```

Como son mensajes protobuf, `inspect.signature()` no funciona sobre ellos
(por eso hay que leer el `.proto` o probar los kwargs directamente).

### Ruta de la Agent Card

`a2a.utils.constants.AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent-card.json"`
— el SDK **solo** trae esa ruta por defecto. La tarea 33/34 pide exponer
**también** `/.well-known/agent.json` (compatibilidad con clientes A2A más
viejos). `create_agent_card_routes()` acepta `card_url`, así que se llama dos
veces:

```python
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes

add_a2a_routes_to_fastapi(
    app,
    agent_card_routes=[
        *create_agent_card_routes(card, card_url="/.well-known/agent-card.json"),
        *create_agent_card_routes(card, card_url="/.well-known/agent.json"),
    ],
    jsonrpc_routes=create_jsonrpc_routes(request_handler, rpc_url="/"),
)
```

### El método `message/send`

Definido en la interfaz abstracta `a2a.server.request_handlers.RequestHandler`:

```python
async def on_message_send(
    self, params: SendMessageRequest, context: ServerCallContext,
) -> Task | Message:
    """Handles the 'message/send' method (non-streaming)."""
```

`DefaultRequestHandler` (en `a2a.server.request_handlers`) ya implementa esta
interfaz completa; recibe el `AgentExecutor` propio del agente:

```python
DefaultRequestHandler(
    agent_executor: AgentExecutor,
    task_store: TaskStore,
    agent_card: AgentCard,
    ...  # queue_manager, push_config_store, etc. — todos opcionales
)
```

Lo único que hay que escribir por agente es el `AgentExecutor`:

```python
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue

class BookingAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # leer el mensaje de context, llamar al MCP server, encolar la respuesta
        ...
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        ...
```

`JsonRpcDispatcher` (usado internamente por `create_jsonrpc_routes`) mapea el
`method` del JSON-RPC al handler mediante un `match`; `'message/send'` cae en
el caso `'SendMessage'` → `on_message_send`.

### Cliente (para el `orchestrator`, tarea 35)

```python
from a2a.client.client_factory import create_client

client = await create_client("http://booking-agent:9001")  # descarga la Agent Card
# por defecto de <url>/.well-known/agent-card.json (relative_card_path lo cambia)
async for response in client.send_message(send_message_request):
    ...
```

`create_client(agent, ...)` acepta una URL (resuelve la card automáticamente)
o un `AgentCard` ya construido. `Client.send_message()` es un
`AsyncIterator[StreamResponse]`, no una llamada única — hay que iterar aunque
el agente responda de una sola vez.

---

## Resumen para las tareas 28-36

| Pieza | API real a usar |
|---|---|
| MCP server (28) | `mcp.server.mcpserver.MCPServer`, `.tool()`, `.run(transport="streamable-http", host=..., port=...)` |
| Claude Desktop (32) | `mcp-remote` apuntando al puerto HTTP publicado (no hay modo stdio nativo) |
| Agent Card (33/34) | `a2a.types.AgentCard/AgentSkill/AgentCapabilities` (protobuf); `create_agent_card_routes(card, card_url=...)` llamado dos veces |
| Lógica del agente (33/34) | Subclase de `a2a.server.agent_execution.AgentExecutor` + `DefaultRequestHandler` |
| Exponer HTTP (33/34) | `add_a2a_routes_to_fastapi(app, agent_card_routes=..., jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"))` |
| Descubrir y llamar agentes (35) | `a2a.client.client_factory.create_client(url)` → `client.send_message(...)` |
