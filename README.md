# BarberFlow — Plataforma de reservas para barbería/peluquería

Sistema de reservas de citas de barbería construido con arquitectura de microservicios:
tres servicios independientes con base de datos propia, service registry con Consul,
un MCP Server para operar el sistema con agentes de IA, y una red de agentes A2A.

> Proyecto del curso **Arquitectura de Componentes y Microservicios** — Universidad Galileo, FISICC.
> El backlog de implementación está en [`docs/BACKLOG.md`](docs/BACKLOG.md) y el checklist
> de la entrega con sus evidencias en [`ENTREGA.md`](ENTREGA.md).

## Arquitectura

```mermaid
graph TD
    subgraph clientes[" "]
        NAV[navegador]
        CD[Claude Desktop<br/>cliente MCP]
        USR[usuario<br/>lenguaje natural]
    end

    subgraph a2a["Agentes A2A — se delegan trabajo entre sí"]
        ORC[orchestrator :9000]
        BAG[booking-agent :9001]
        NAG[notification-agent :9002]
    end

    WEB[web-ui :3000<br/>BFF Next.js]
    MCP[barberflow-mcp :8000<br/>5 tools]
    CONSUL[(consul :8500<br/>service registry)]

    subgraph negocio["Microservicios de negocio — una base cada uno"]
        US[users-svc :8003]
        BS[booking-svc :8001]
        NS[notif-svc :8002]
        UDB[(users-db)]
        BDB[(booking-db)]
        NDB[(notif-db)]
    end

    NAV --> WEB
    CD -->|MCP tools/call| MCP
    USR -->|POST /instruct| ORC
    ORC -->|A2A message/send<br/>elige por skill| BAG
    ORC -->|A2A message/send| NAG
    BAG -->|MCP tools/call| MCP
    NAG -->|MCP tools/call| MCP

    WEB -.->|¿dónde está?| CONSUL
    MCP -.->|¿dónde está?| CONSUL
    BS -.->|¿dónde está?| CONSUL
    US -.->|se registra| CONSUL
    BS -.->|se registra| CONSUL
    NS -.->|se registra| CONSUL

    WEB --> US
    WEB --> BS
    MCP --> US
    MCP --> BS
    MCP --> NS
    BS -->|valida al usuario<br/>por API, nunca por BD| US
    BS -->|notifica: timeout 2s, 3 reintentos,<br/>breaker 3/30s y outbox| NS

    US --> UDB
    BS --> BDB
    NS --> NDB

    style CONSUL fill:#f5f0e8,stroke:#8a7a5c
    style MCP fill:#e8f0f5,stroke:#4a7a8a
    style WEB fill:#f0e8f5,stroke:#7a5c8a
```

Cuatro decisiones sostienen el diagrama:

- **Database per service.** Cada servicio es dueño exclusivo de su base y no hay una sola
  FK que cruce de una a otra. Cuando `booking-svc` necesita validar al usuario que reserva,
  llama a `GET /users/{id}` de `users-svc`; nunca lee `users-db`.
- **Descubrimiento dinámico, cero URLs hardcodeadas.** Nadie guarda la dirección de nadie:
  `shared/consul.py` registra el servicio al arrancar y `discover()` le pregunta a Consul
  por una instancia **sana** (`?passing=true`) en cada llamada. Por eso la rotación de
  credenciales puede hacerse sin downtime (ver más abajo).
- **Resiliencia en el llamador.** `shared/resilience.py` envuelve toda llamada entre
  servicios con timeout de 2s, 3 reintentos con backoff exponencial + jitter y un circuit
  breaker por destino (3 fallos → abierto 30s). Si `notif-svc` no está, la cita se crea
  igual y la notificación queda en el **outbox** de `booking-svc` para reintentarse.
- **Dos capas de IA que no son intercambiables.** `barberflow-mcp` expone *herramientas*
  (MCP); los tres agentes se delegan *trabajo* entre sí (A2A) y por dentro son clientes de
  ese MCP. La diferencia, con el flujo real, está en la sección
  [Agent-to-Agent: MCP vs. A2A](#agent-to-agent-mcp-vs-a2a-tarea-39).

## Componentes

| Servicio | Puerto interno | Puerto en el host | Qué hace |
|---|---|---|---|
| `users-svc` | 8003 | `USERS_PORT` (8003) | Registro y autenticación de usuarios (JWT) |
| `booking-svc` | 8001 | `BOOKING_PORT` (8001) | Gestión de citas, servicios de barbería y horarios |
| `notif-svc` | 8002 | `NOTIF_PORT` (8002) | Envío e historial de notificaciones |
| `barberflow-mcp` | 8000 | `MCP_PORT` (8000) | Expone BarberFlow a agentes de IA vía MCP |
| `consul` | 8500 | `CONSUL_PORT` (8500) | Registro y descubrimiento de servicios |
| `orchestrator` | 9000 | `ORCHESTRATOR_PORT` (9000) | Recibe la instrucción y delega en los agentes A2A |
| `booking-agent` | 9001 | `BOOKING_AGENT_PORT` (9001) | Agente A2A especializado en citas |
| `notification-agent` | 9002 | `NOTIFICATION_AGENT_PORT` (9002) | Agente A2A especializado en avisos |
| `web-ui` | 3000 | `WEB_PORT` (3080) | App Next.js: reservar y ver citas, con BFF propio |
| `users-db` · `booking-db` · `notif-db` | 5432 | — (no se publican) | Una base Postgres por servicio, con su propio rol |

El puerto interno es el del enunciado y es fijo. El del host se puede sobrescribir en el
`.env` porque en una máquina de desarrollo es normal tener 8001, 3000 o 5432 ocupados.

## Cómo correr el proyecto

```bash
git clone https://github.com/Esaban17/barberflow-microservices.git
cd barberflow-microservices
cp .env.example .env    # completar los valores (ver notas abajo)
docker compose up --build
```

Cuando termina de levantar:

| Qué | Dónde |
|---|---|
| App web | http://localhost:3080 |
| Panel de estado (Consul + circuit breaker) | http://localhost:3080/status |
| UI de Consul | http://localhost:8500 |
| MCP Server | http://localhost:8000/mcp |
| Orchestrator A2A | `POST http://localhost:9000/instruct` |

Tres cosas que se topan en la práctica:

- **Puertos ocupados.** Todos los puertos del host son overridables en el `.env`
  (`BOOKING_PORT`, `WEB_PORT`, `ORCHESTRATOR_PORT`, …). Si algo ya escucha en el puerto,
  `docker compose` falla con `address already in use`: cambiá esa variable y listo. Ojo con
  los clientes de VPN corporativa, que suelen tomar el 9000.
- **Red que intercepta TLS** (Zscaler y similares): dejá `PIP_TRUSTED_HOST` y
  `NPM_STRICT_SSL=false` en el `.env` o el build falla con `CERTIFICATE_VERIFY_FAILED`.
- **`DEMO_USER_PASSWORD` tiene que ser `demo1234`.** Es la identidad con la que opera el MCP
  Server y su hash está fijo en la semilla de `users-svc`
  ([`services/users-svc/db/01-init.sql`](services/users-svc/db/01-init.sql)); con otro valor
  el MCP responde `users-svc POST /login -> 401`.

### Verificación rápida

Lo que pide el enunciado como entregable del Task 1:

```bash
curl http://localhost:8003/healthz   # → {"status":"ok"}
curl http://localhost:8001/healthz   # → {"status":"ok"}   (8011 si cambiaste BOOKING_PORT)
curl http://localhost:8002/healthz   # → {"status":"ok"}
```

Y para recorrer los 7 checkpoints del enunciado de una sola pasada, sin tocar nada a mano:

```bash
./scripts/demo.sh
```

El script valida Consul, JWT, correlation-id, el circuit breaker abriéndose y cerrándose, y
las tools del MCP Server; deja el sistema como lo encontró. Ver
[Demo en video](#demo-en-video) para la grabación equivalente.

## Demo en video

El repositorio incluye [`video_DEMO_mcp.mp4`](video_DEMO_mcp.mp4) (~65 MB): una llamada real
a `barberflow-mcp` desde Claude como cliente MCP, que cubre los checkpoints 6 y 7 del
enunciado (`get_available_slots` y `create_booking` en lenguaje natural).

Los 7 checkpoints que pide el enunciado, y con qué se comprueba cada uno:

| # | Checkpoint | Cómo se comprueba |
|---|---|---|
| 1 | `docker compose up` → Consul con los servicios en verde | http://localhost:8500 · `docs/evidencias/02-consul-3-servicios.png` |
| 2 | Registrar usuario → login → JWT | `./scripts/demo.sh` (paso 2) |
| 3 | Reservar con el JWT → log JSON con `correlation_id` | `./scripts/demo.sh` (paso 3) · `docs/correlation-id-trace.md` |
| 4 | Derribar `notif-svc` → el sistema responde 201 → breaker abierto | `./scripts/demo.sh` (paso 4) · `docs/evidencias/03-status-breaker-abierto.png` |
| 5 | Levantar `notif-svc` → el breaker cierra y el outbox se vacía | `./scripts/demo.sh` (paso 5) · `docs/evidencias/04-status-todo-verde.png` |
| 6 | Claude lista horarios vía MCP | `video_DEMO_mcp.mp4` · `./scripts/demo.sh` (paso 6) |
| 7 | Claude crea la reserva vía MCP | `video_DEMO_mcp.mp4` · `./scripts/demo.sh` (paso 7) |

Para conectar Claude Desktop al MCP Server, la configuración probada está en
[`docs/a2a-mcp-api-notes.md`](docs/a2a-mcp-api-notes.md#config-de-claude-desktop-tarea-32).

## Del enunciado (FitFlow) a BarberFlow

El enunciado plantea una plataforma de clases fitness; este proyecto implementa el mismo
sistema sobre el dominio de una barbería. La traducción es literal y no cambia ninguna
pieza de arquitectura:

| Enunciado (FitFlow) | BarberFlow |
|---|---|
| clase de fitness | servicio de barbería (corte clásico, corte + barba, afeitado, tinte, cejas) |
| horario de clase | *slot*: barbero + servicio + fecha/hora |
| instructor | barbero |
| reserva de clase | cita (`appointment`) |
| `get_available_classes` | `get_available_slots` |
| `create_booking` / `cancel_booking` | iguales |
| `fitflow-mcp` | `barberflow-mcp` |

## Despliegue en la nube

El `docker-compose.yml` sigue siendo la forma de correr en local. Para desplegar el sistema
completo en Railway —servicios, bases, secretos como Variables del proveedor y Consul en la
nube— el paso a paso está en [`docs/railway-deploy.md`](docs/railway-deploy.md).

## Gestión de secretos y rotación de credenciales (tarea 38)

### Dónde viven los secretos

Todos los secretos (contraseñas de Postgres, `JWT_SECRET`, `DEMO_USER_PASSWORD`,
`ANTHROPIC_API_KEY`) se leen de variables de entorno, nunca están escritos en el
código ni en `docker-compose.yml`. `.env` está en `.gitignore`; lo único que se
commitea es `.env.example` con placeholders (`cambiar`). Ver la auditoría de la
tarea 42 para la verificación de que ningún secreto real llegó al historial de git.

Cada base de datos tiene dos roles (patrón *least privilege*, tarea 14):

- Un **superusuario** (`*_DB_SUPERUSER` / `*_DB_SUPERPASSWORD`) que solo usa el
  entrypoint de Postgres para inicializar el esquema.
- Un **rol de aplicación** (`*_APP_USER` / `*_APP_PASSWORD`) con permisos mínimos
  (`CONNECT`, `USAGE` sobre `public`, DML sobre las tablas — nada de `CREATE`,
  `ALTER` ni `DROP`), creado por `services/<svc>/db/02-init.sh` a partir de
  `APP_DB_USER`/`APP_DB_PASSWORD`. Es este rol el que usa el propio servicio en su
  `DATABASE_URL`, y el que hay que rotar periódicamente o ante una fuga.

### Por qué el procedimiento "obvio" SÍ tiene downtime (medido)

La nota original del backlog para esta tarea decía: crear un rol nuevo con los
mismos grants, cambiar el `DATABASE_URL` del servicio, reiniciarlo con
`docker compose up -d --no-deps <svc>` y luego borrar el rol viejo. Se probó
ese procedimiento tal cual (una sola instancia de `booking-svc`, contra Postgres
real, con un poller externo golpeando `/readyz` cada ~65 ms) y **sí hay una
ventana real sin servicio**: al matar el proceso viejo y levantar el nuevo con
el rol rotado, el poller registró 15 peticiones fallidas seguidas antes de que
el servicio volviera a responder — **≈0.99 s de corte real** (última respuesta
`200` antes del corte → primera `200` después: 1.07 s). Es el resultado
esperado de reemplazar la única réplica de un servicio en el sitio: por un
instante nadie escucha en ese puerto. Documentarlo así, en vez de afirmar
"cero downtime" sin comprobarlo, es el punto de esta tarea.

### El procedimiento que sí cumple "sin que caiga ningún servicio" (probado)

BarberFlow ya tiene las dos piezas necesarias para una rotación real sin caída:
Consul como registro de servicios (varias instancias pueden registrarse bajo el
mismo `Name`) y `shared/resilience.call_service`, que en cada llamada (y en cada
reintento) vuelve a resolver la instancia vía `consul.discover()` — que a su vez
reparte con `random.choice` entre **todas** las instancias sanas. Eso significa
que mientras haya *al menos una* instancia sana de un servicio, sus llamadores
nunca ven un fallo, aunque la instancia que se está rotando esté cayendo en ese
mismo instante. El procedimiento es un rolling/blue-green de un servicio a la vez:

1. Crear el rol nuevo con los mismos grants que el viejo (mismo SQL que corre
   `02-init.sh`, contra la base ya existente):
   ```sql
   CREATE ROLE booking_app_v2 LOGIN PASSWORD '<password-nueva>';
   GRANT USAGE ON SCHEMA public TO booking_app_v2;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO booking_app_v2;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO booking_app_v2;
   ```
2. Levantar **una segunda instancia** del mismo servicio, con el rol nuevo en su
   `DATABASE_URL`, sin tocar la instancia original (que sigue sirviendo con el
   rol viejo):
   ```bash
   docker compose run -d --name barberflow-booking-svc-rotate --no-deps \
     -p 8011:8001 \
     -e DATABASE_URL="postgresql://booking_app_v2:<password-nueva>@booking-db:5432/${BOOKING_DB_NAME}" \
     booking-svc
   ```
   Ambos contenedores se registran en Consul bajo el mismo `Name=booking-svc`
   (cada uno con su propio `service_id`, ver `shared/consul.register`), así que
   apenas el health check del nuevo pasa, Consul lista **dos** instancias sanas.
3. Confirmar que la instancia nueva quedó sana (`GET /readyz` y una consulta real,
   p. ej. `GET /services`, contra su puerto publicado) antes de tocar nada más.
4. Recrear la instancia original con el rol nuevo:
   `docker compose up -d --no-deps booking-svc` (con `BOOKING_APP_USER`/
   `BOOKING_APP_PASSWORD` ya actualizados en `.env` al rol nuevo). Esta instancia
   sí pasa por el mismo corte de ~1 s medido arriba — pero durante ese segundo la
   instancia temporal del paso 2 sigue sana y registrada, así que **no hay ningún
   instante con cero instancias sanas**.
5. Una vez que la instancia original vuelve a responder con el rol nuevo, bajar
   la instancia temporal (`docker compose rm -fs barberflow-booking-svc-rotate`).
6. Recién ahora borrar el rol viejo (`DROP OWNED BY booking_app; DROP ROLE
   booking_app;` tras reasignar lo que sea dueño con `REASSIGN OWNED`).

**Evidencia real de que esto funciona:** se corrió este procedimiento completo
contra Postgres real (dos instancias de `booking-svc` simultáneas, una con el
rol viejo y otra con un rol nuevo, ambas registradas en el mismo service registry),
con un llamador que usó el **mismo** `shared.resilience.call_service` que usan
los demás servicios de BarberFlow entre sí — 400 llamadas reales a
`GET /services` cada 50 ms, sin parar, mientras se mataba la instancia con el
rol viejo y se borraba ese rol a mitad del test:

```
total=400 fails=0
```

Cero fallos en las 400 llamadas. La caída de ~1 s de una instancia sola sigue
ahí (es real y está medida arriba), pero como nunca coincide con "cero
instancias sanas", ningún llamador la nota. Eso es lo que pide el "Done cuando"
de la tarea 38: no que una instancia individual nunca tenga un blip, sino que
ningún servicio de BarberFlow se caiga por la rotación.

## Agent-to-Agent: MCP vs. A2A (tarea 39)

BarberFlow usa dos protocolos distintos para IA, y no son intercambiables:
resuelven problemas distintos.

- **MCP (Model Context Protocol)** — `barberflow-mcp` (puerto 8000) — conecta un
  modelo/cliente de IA (Claude Desktop, el propio `orchestrator`) con
  **herramientas**: funciones puntuales con un esquema de entrada/salida
  (`get_available_slots`, `create_booking`, `cancel_booking`, `send_notification`,
  `get_notifications`). Es una relación **cliente ↔ servidor de herramientas**:
  quien habla MCP no tiene "personalidad" ni mantiene una conversación, solo
  expone o invoca funciones.
- **A2A (Agent2Agent)** — `booking-agent` (9001), `notification-agent` (9002) y
  el `orchestrator` (9000) — conecta **agentes** entre sí: cada uno publica una
  *Agent Card* (`/.well-known/agent-card.json`) que anuncia sus *skills* en
  lenguaje natural, y se les habla con un mensaje de texto libre
  (`message/send`), no con una llamada a función tipada. Es una relación
  **agente ↔ agente**: el `orchestrator` no sabe qué hace `create_booking` por
  dentro, solo sabe que `booking-agent` tiene la skill `create_booking` y le
  delega el mensaje completo.

En BarberFlow un agente A2A **es un cliente de MCP**: `booking-agent` y
`notification-agent` no hablan directo con `booking-svc`/`notif-svc` — traducen
el mensaje en lenguaje natural que reciben por A2A a una llamada a una tool de
`barberflow-mcp` (`shared/mcp_client.call_tool`), y esa tool es la que finalmente
llama al microservicio de negocio vía `shared.resilience.call_service`. MCP es
la capa de "acción sobre el sistema"; A2A es la capa de "delegación entre
agentes que deciden qué acción tomar".

### La grabación de la llamada MCP

[`video_DEMO_mcp.mp4`](video_DEMO_mcp.mp4) muestra esa primera capa en vivo: desde el
cliente de IA (Claude Desktop conectado como cliente MCP) se invocan las tools
`get_available_slots` y `create_booking` de `barberflow-mcp`, igual que las usa
`booking-agent` en el flujo A2A de abajo, pero aquí llamadas directo por Claude como
cliente de herramientas. Ver [Demo en video](#demo-en-video) para los 7 checkpoints.

### Flujo real de un mensaje

```mermaid
sequenceDiagram
    actor U as Usuario
    participant O as orchestrator :9000
    participant BA as booking-agent :9001<br/>(A2A)
    participant NA as notification-agent :9002<br/>(A2A)
    participant MCP as barberflow-mcp :8000<br/>(MCP)
    participant BS as booking-svc :8001
    participant NS as notif-svc :8002

    U->>O: POST /instruct<br/>"Resérvame corte y barba el viernes y avísame"
    Note over O: build_plan(): API de Claude (o keywords si no hay<br/>ANTHROPIC_API_KEY) -> ["create_booking", "send_notification"]
    O->>O: discover_agents()<br/>lee AGENT_URLS, baja las Agent Cards,<br/>empareja skill -> agente
    O->>BA: A2A message/send<br/>"...corte y barba el viernes..."
    BA->>MCP: MCP tools/call get_available_slots
    MCP->>BS: GET /slots (call_service)
    BS-->>MCP: horarios disponibles
    MCP-->>BA: slots (JSON)
    BA->>MCP: MCP tools/call create_booking
    MCP->>BS: POST /appointments (call_service)
    BS-->>MCP: cita creada
    MCP-->>BA: resultado
    BA-->>O: A2A response: "cita creada para el viernes..."
    O->>NA: A2A message/send<br/>"...avísame. Resultado de la reserva: cita creada..."
    NA->>MCP: MCP tools/call send_notification
    MCP->>NS: POST /notifications (call_service)
    NS-->>MCP: notificación registrada
    MCP-->>NA: resultado
    NA-->>O: A2A response: "notificación enviada"
    O-->>U: {"plan": [...], "steps": [...]}
```

El mismo `x-correlation-id` viaja por las tres capas (A2A, MCP y las llamadas
HTTP internas entre microservicios) — ver [`docs/correlation-id-trace.md`](docs/correlation-id-trace.md)
para una traza real capturada de este flujo con un solo `correlation_id` visible
en los logs de los 6 servicios.

_El resto de este README (arquitectura completa, tabla de servicios, mapeo PDF →
barbería) se completa en la tarea 37 del backlog, a cargo de Estuardo._
