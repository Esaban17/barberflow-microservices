# BarberFlow — Backlog de implementación

**Proyecto:** plataforma de reservas para barbería/peluquería con arquitectura de microservicios
**Curso:** Arquitectura de Componentes y Microservicios — Universidad Galileo, FISICC
**Base:** `proyecto-FitFlow_Proyecto_Mejorado.pdf` (dominio adaptado: de clases de fitness a servicios de barbería)
**Equipo:** `AM` = Andre Morales · `ES` = Estuardo Sabán

---

## Resumen

| | |
|---|---|
| Total de tareas | **42** |
| Andre Morales (AM) | 21 |
| Estuardo Sabán (ES) | 21 |
| Fases | 10 (se ejecutan en orden; dentro de una fase, lo que no comparte dependencia va en paralelo) |
| Rúbrica cubierta | 110 pts + 15 extra (despliegue cloud) |

El reparto AM/ES se hizo **al azar** (`random.shuffle` balanceado), no por afinidad técnica. Cada tarea se
replica como *issue* en el repositorio de GitHub (tarea 2) para que la entrega sea trazable.

### Estado de avance

Actualizado al 20 de agosto de 2026. Un PR por tarea; el historial queda como evidencia de la entrega.

| # | Tarea | Asig. | Estado | PR |
|---|---|---|---|---|
| 1 | Scaffold, `.gitignore`, `.env.example` | AM | ✅ Hecho | commit inicial |
| 2 | Repo público en GitHub | ES | ✅ Hecho | commit inicial |
| 4 | `docker-compose.yml` base + red + Consul | ES | ✅ Hecho | [#1](https://github.com/Esaban17/barberflow-microservices/pull/1) |
| 7 | `shared/auth.py` — JWT HS256 + 401 | ES | ✅ Hecho | [#2](https://github.com/Esaban17/barberflow-microservices/pull/2) |
| 6 | `shared/db.py` — pool + healthz/readyz | ES | ✅ Hecho | [#3](https://github.com/Esaban17/barberflow-microservices/pull/3) |
| 5 | `shared/logging.py` — JSON + correlation-id | ES | ✅ Hecho | [#4](https://github.com/Esaban17/barberflow-microservices/pull/4) |
| 8 | `shared/consul.py` — registro y descubrimiento | ES | ✅ Hecho | [#5](https://github.com/Esaban17/barberflow-microservices/pull/5) |
| 9 | `shared/resilience.py` | ES | 🔄 En curso | — |
| 23 | TTL real de desregistro de Consul | ES | 🔄 En curso | — |

**Bloqueadas por AM:** todas las demás tareas de ES (11, 13, 16, 21, 24, 26, 28, 29, 31, 32, 37, 38, 40)
dependen de entregables de Andre — los `init.sql` de las tres bases (10, 14, 20), los Dockerfiles y el
registro en Consul de cada servicio (12, 18, 22), y la nota de API del `a2a-sdk` (3).

**Hallazgo que corrige el enunciado:** Consul 1.17 impone un mínimo de 1 minuto a
`deregister_critical_service_after`, así que los 30s que pide el PDF no se cumplen: eleva el valor en
silencio y solo lo registra en el log del agente. Las tareas 24, 26 y 40 deben planificar su espera contra
el número real (ver `docs/consul-ttl.md`, tarea 23).

### Cobertura de la rúbrica

| Criterio del PDF | Pts | Tareas |
|---|---|---|
| Los 3 servicios corren con `docker compose up` y tienen DB propia | 20 | 1, 4, 6, 10–22 |
| Los servicios se registran en Consul y se descubren dinámicamente | 20 | 8, 12, 18, 22, 23 |
| MCP Server funciona: Claude puede crear una reserva | 20 | 3, 28–32 |
| Circuit breaker demostrado: notif-svc cae, el sistema sigue | 20 | 9, 19, 24, 25, 26, 27 |
| JWT implementado + secretos fuera del código | 10 | 1, 5, 7, 11, 16, 29, 38, 42 |
| Agent-to-Agent | 20 | 3, 33–36, 39 |
| **Extra** — despliegue cloud | +15 | 41 |

### Convenciones de dominio (PDF → BarberFlow)

| PDF (FitFlow) | BarberFlow |
|---|---|
| clase de fitness | servicio de barbería (corte clásico, corte + barba, afeitado, tinte, cejas) |
| horario de clase | *slot*: barbero + servicio + fecha/hora |
| instructor | barbero |
| `get_available_classes` | `get_available_slots` |
| `create_booking` / `cancel_booking` | iguales (cita) |

---

## Fase 1 — Scaffold y repositorio

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 1 | Estructura de carpetas + `.gitignore` (`.env`, `__pycache__`, `.venv`) + `.env.example` con placeholders de **todos** los secretos | AM | — | La estructura coincide con el plan y `.env.example` no tiene ningún valor real |
| 2 | `git init`, commit inicial, `gh repo create Esaban17/barberflow-microservices --public` + push + issues del backlog | ES | 1 | Repo público existe, `git status` no lista `.env`, `.env.example` sí está trackeado |
| 3 | venv con las libs pineadas y **leer los paquetes instalados** `a2a-sdk==1.1.2` y `mcp==2.0.0` para fijar su API real (clases, ruta de la card, `message/send`) | AM | — | Nota en `docs/` con las firmas reales que usarán las fases 7 y 8 |
| 4 | Mapa de puertos con override (`${BOOKING_PORT:-8001}`) y `docker-compose.yml` base (red + Consul) | ES | 1 | `docker compose config` es válido y ningún puerto choca con lo que ya corre en la máquina |

## Fase 2 — `shared/` (base común de los 6 servicios)

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 5 | `shared/logging.py`: structlog JSON + contextvar + middleware que genera/propaga `x-correlation-id` y **decodifica el JWT ahí mismo** para tener `user_id` en la línea del request | ES | 1 | El log emite `timestamp, level, service, event, correlation_id, user_id` |
| 6 | `shared/db.py`: pool psycopg3 + helpers `healthz`/`readyz` (`SELECT 1`, 503 si falla) | ES | 1 | `readyz` responde 503 con la BD apagada y 200 con ella arriba |
| 7 | `shared/auth.py`: emitir/verificar JWT HS256 (`sub`, `email`, `role`, `exp`) + dependencia FastAPI que responde **401** | ES | 1 | Token manipulado y token expirado → 401 |
| 8 | `shared/consul.py`: `register()`/`deregister()` en el lifespan + `discover(name)` de instancias *passing* que **trata la lista vacía como fallo, no como `IndexError`** | ES | 1 | `discover("inexistente")` levanta el error esperado, no un 500 |
| 9 | `shared/resilience.py`: httpx timeout 2s + tenacity (3 intentos, 0.5/1/2s + jitter) + pybreaker (3 fallos → 30s) + propagación del correlation-id saliente | ES | 5, 8 | Contra un endpoint muerto: 3 reintentos y el breaker abre |

## Fase 3 — users-svc (:8003)

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 10 | `init.sql` (tabla `users`) + `init.sh` con el rol `users_app` de menor privilegio | AM | 1 | `users_app` hace DML pero `DROP TABLE` le es denegado |
| 11 | `POST /register`, `POST /login` (devuelve JWT), `GET /users/{id}` | ES | 7, 10 | Registro → login → token decodificable con el `user_id` correcto |
| 12 | `/healthz`, `/readyz`, registro en Consul y `Dockerfile` | AM | 6, 8 | El contenedor levanta y aparece verde en Consul |
| 13 | `users-svc` + `users-db` en el compose con sus variables de entorno | ES | 4, 12 | `docker compose up users-svc` deja el healthz en 200 |

## Fase 4 — booking-svc (:8001)

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 14 | `init.sql`/`init.sh`: `services`, `barbers`, `slots`, `appointments`, `outbox` + seed (5 servicios de barbería, 3 barberos, slots de 7 días) | AM | 1 | `GET /slots` devuelve datos reales sin insertar nada a mano |
| 15 | `GET /services` y `GET /slots?date=&service_id=&barber_id=` | AM | 14 | Los filtros funcionan y los slots ya reservados no aparecen |
| 16 | `POST /appointments` con JWT **+ validación del usuario llamando a `GET /users/{id}` de users-svc** (nunca leyendo `users_db`) | ES | 7, 11, 14 | Sin token → 401; con token válido → 201 y fila en `appointments` |
| 17 | `GET /appointments/{id}` y `DELETE /appointments/{id}` (cancelar libera el slot) | AM | 16 | Tras cancelar, el slot vuelve a estar disponible |
| 18 | `/healthz`, `/readyz`, Consul, `Dockerfile` y entrada en compose con `booking-db` | AM | 6, 8, 12 | Verde en Consul junto a users-svc |
| 19 | Llamada booking → notif **descubriendo por Consul** y envuelta en `shared/resilience` | AM | 9, 16 | Con notif-svc arriba la cita genera notificación; la URL no está hardcodeada en ningún lado |

## Fase 5 — notif-svc (:8002)

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 20 | `init.sql`/`init.sh` + tabla `notifications` (incluye `correlation_id`) | AM | 1 | Rol de menor privilegio verificado igual que en la tarea 10 |
| 21 | `POST /notifications` (log + persistencia) y `GET /notifications?user_id=` | ES | 20 | El historial por usuario devuelve lo enviado |
| 22 | `/healthz`, `/readyz`, Consul, `Dockerfile` y compose con `notif-db` | AM | 6, 8 | Los **3 servicios** en verde en `localhost:8500` (captura de la rúbrica) |

## Fase 6 — Resiliencia y observabilidad end-to-end

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 23 | Consul en compose + **verificar el TTL real** que aplica a `deregister_critical_service_after` (`GET /v1/agent/checks`) y ajustar la demo a ese número | ES | 4 | El valor real queda documentado en el README y usado en `demo.sh` |
| 24 | Outbox: al abrirse el breaker o agotarse los reintentos, la notificación se guarda `pending` y **la cita se crea igual**; task en background reintenta cada 15s | ES | 19 | Con notif-svc caído: 201 + fila `pending`; al volver, pasa a `sent` sola |
| 25 | `GET /admin/circuit` con estado del breaker y conteo del outbox | AM | 24 | Devuelve `open`/`closed` y el pendiente real |
| 26 | Probar el **caso de lista vacía** (Consul ya desregistró notif-svc): debe caer al outbox, no a un 500 | ES | 23, 24 | Tras esperar el TTL real, `POST /appointments` → 201 y el breaker cuenta el fallo |
| 27 | Trazabilidad: un mismo `correlation_id` visible en users-svc → booking-svc → notif-svc | AM | 5, 19 | `docker compose logs \| jq 'select(.correlation_id=="…")'` muestra el viaje completo |

## Fase 7 — MCP Server (:8000)

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 28 | FastMCP con transporte streamable-http + `Dockerfile` + compose + registro en Consul | ES | 3, 4 | El contenedor expone el endpoint MCP en `:8000` |
| 29 | Identidad del MCP: login con `DEMO_USER_EMAIL`/`DEMO_USER_PASSWORD` **desde `.env`**, cache del JWT y re-login ante 401 | ES | 11, 28 | Ninguna credencial en el código; `grep -r` no encuentra passwords |
| 30 | Tools `get_available_slots`, `create_booking`, `cancel_booking` (destino resuelto por Consul) | AM | 15, 16, 17, 29 | Las 3 tools crean/cancelan filas reales en `booking_db` |
| 31 | Tools `send_notification`, `get_notifications` (las usa el Notification Agent) | ES | 21, 29 | Una notificación creada desde MCP aparece en el historial |
| 32 | Config de Claude Desktop (`docker exec -i … --stdio` y alternativa `mcp-remote`) documentada y probada | ES | 30, 31 | Desde Claude Desktop, *"¿qué horarios hay el viernes?"* devuelve datos reales |

## Fase 8 — Agent-to-Agent (:9000–9002)

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 33 | `booking-agent` :9001 con `a2a-sdk`, Agent Card en `/.well-known/agent.json` **y** `/.well-known/agent-card.json`, skills ejecutadas vía MCP | AM | 3, 30 | La card valida y `create_booking` por A2A crea la cita |
| 34 | `notification-agent` :9002, mismas dos rutas de card, skills `send_notification` / `get_history` vía MCP | AM | 3, 31 | Notificación enviada por delegación A2A |
| 35 | `orchestrator` :9000: lee `AGENT_URLS`, **descarga las cards** y elige por `skills`; interpreta con la API de Claude y **cae a keywords** si no hay key o falla | AM | 33, 34 | *"Resérvame corte y barba el viernes y avísame"* → reserva + notificación, y también funciona sin `ANTHROPIC_API_KEY` |
| 36 | Los 3 agentes en el compose + logs de la conversación A2A en JSON con `correlation_id` | AM | 35 | Los logs muestran la delegación agente → agente paso a paso |

## Fase 9 — Documentación y demo

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 37 | README: diagrama ASCII, tabla de servicios/puertos, `clone → cp .env.example .env → docker compose up --build`, tabla de mapeo PDF → barbería | ES | 22 | Alguien que clona el repo levanta el sistema sin preguntar nada |
| 38 | README: gestión de secretos + **rotación de credenciales sin downtime** (pasos concretos, probados) | ES | 10, 20 | La rotación se ejecuta de verdad sin que caiga ningún servicio |
| 39 | README: sección **Agent-to-Agent** explicando la diferencia entre MCP y A2A (checkpoint de Task 5) | AM | 36 | La explicación usa el diagrama del flujo real del proyecto |
| 40 | `demo.sh` con los 7 checkpoints del PDF en orden + guion de video escena por escena en `docs/` | ES | 26, 32, 36 | `./demo.sh` corre de punta a punta y sirve para grabar sin editar |

## Fase 10 — Cloud (+15) y cierre

| # | Tarea | Asig. | Dep. | Done cuando |
|---|---|---|---|---|
| 41 | Despliegue en Railway: definición de servicios, **secretos como Variables del proveedor (no `.env`)**, URLs públicas, captura de la UI de Consul en la nube y sección de despliegue paso a paso en el README | AM | 37 | Los servicios responden por URL pública y el compose local sigue funcionando |
| 42 | `ENTREGA.md` con checklist de la rúbrica (110 + 15) y evidencias + auditoría final de secretos (`git log` sin `.env`, sin passwords en el historial) | AM | 40, 41 | Cada criterio del PDF tiene su fila, su estado y su evidencia enlazada |

---

## Notas de ejecución

- **El video lo graba el equipo.** La tarea 40 entrega el script y el guion; la grabación de pantalla es manual.
- **La tarea 41 necesita cuenta de Railway** del equipo antes de poder ejecutarse.
- **La tarea 35 funciona sin `ANTHROPIC_API_KEY`**: el orquestador cae a un parser por keywords, para que la
  demo no dependa de la red ni de una API key.
- Puertos internos = los del PDF (8001/8002/8003, 8000, 8500, 9000–9002). En el host son overridables porque
  `8001` y `5432` ya están ocupados en la máquina de desarrollo.
