# BarberFlow — Backlog de implementación

**Proyecto:** plataforma de reservas para barbería/peluquería con arquitectura de microservicios
**Curso:** Arquitectura de Componentes y Microservicios — Universidad Galileo, FISICC
**Base:** `proyecto-FitFlow_Proyecto_Mejorado.pdf` (dominio adaptado: de clases de fitness a servicios de barbería)
**Equipo:** `AM` = Andre Morales · `ES` = Estuardo Sabán

---

## Cómo está repartido el trabajo

Reasignado el 21 de agosto de 2026. La regla es simple: **Andre solo tiene tareas que no bloquean a
nadie**. Todo lo que está en la ruta crítica —los tres microservicios, el MCP y el núcleo de la web—
lo lleva Estuardo, para que el sistema se pueda levantar en local sin esperar a nadie.

| | Tareas |
|---|---|
| **ES — ruta crítica** | 2, 4–26, 28–32, 37, 40, 43–46 |
| **AM — nada de esto bloquea** | 3, 27, 33–36, 38, 39, 41, 42, 47 |

Cada tarea (o grupo de tareas de un mismo servicio) va en su propio PR; el historial de PRs es parte
de la evidencia de la entrega.

## Estado de avance

| # | Tarea | Asig. | Estado | PR |
|---|---|---|---|---|
| 1 | Scaffold, `.gitignore`, `.env.example` | ES | ✅ Hecho | commit inicial |
| 2 | Repo público en GitHub | ES | ✅ Hecho | commit inicial |
| 4 | `docker-compose.yml` base + red + Consul | ES | ✅ Hecho | [#1](https://github.com/Esaban17/barberflow-microservices/pull/1) |
| 7 | `shared/auth.py` — JWT HS256 + 401 | ES | ✅ Hecho | [#2](https://github.com/Esaban17/barberflow-microservices/pull/2) |
| 6 | `shared/db.py` — pool + healthz/readyz | ES | ✅ Hecho | [#3](https://github.com/Esaban17/barberflow-microservices/pull/3) |
| 5 | `shared/logging.py` — JSON + correlation-id | ES | ✅ Hecho | [#4](https://github.com/Esaban17/barberflow-microservices/pull/4) |
| 8 | `shared/consul.py` — registro y descubrimiento | ES | ✅ Hecho | [#5](https://github.com/Esaban17/barberflow-microservices/pull/5) |
| 23 | TTL real de desregistro de Consul | ES | ✅ Hecho | [#6](https://github.com/Esaban17/barberflow-microservices/pull/6) |
| 9 | `shared/resilience.py` — timeout, reintentos, breaker | ES | ✅ Hecho | [#7](https://github.com/Esaban17/barberflow-microservices/pull/7) |
| — | Fix: truncamiento silencioso de contraseñas en bcrypt | ES | ✅ Hecho | [#8](https://github.com/Esaban17/barberflow-microservices/pull/8) |
| — | Contrato de APIs (`docs/API.md`) + compose completo | ES | ✅ Hecho | commit directo |
| 10–13 | **users-svc** completo | ES | ✅ Hecho | [#9](https://github.com/Esaban17/barberflow-microservices/pull/9) |
| 20–22 | **notif-svc** completo | ES | ✅ Hecho | [#10](https://github.com/Esaban17/barberflow-microservices/pull/10) |
| 14–19, 24, 25 | **booking-svc** completo + outbox + `/admin/circuit` | ES | ✅ Hecho | [#11](https://github.com/Esaban17/barberflow-microservices/pull/11) |
| 43–46 | **web-ui** (Next.js): BFF, auth, reservar, mis citas | ES | ✅ Hecho | [#12](https://github.com/Esaban17/barberflow-microservices/pull/12) |
| — | Fix: build tras proxy que intercepta TLS (`PIP_TRUSTED_HOST`, `NPM_STRICT_SSL`) | ES | ✅ Hecho | commit directo |
| 26 | Caso de lista vacía en Consul: 201 y no 500 | ES | ✅ Hecho | verificado en el sistema real |

> La tarea 1 la hizo Estuardo dentro del commit inicial: toda tarea de ES dependía de ella y sin el
> scaffold no había dónde abrir un PR. **No hay que rehacerla.**

## Objetivo inmediato — ✅ cumplido el 21 de agosto de 2026

El sistema levanta en local con `docker compose up --build`: los **tres microservicios registrados y
en verde en Consul** (`localhost:8500`) y la **app web** consumiéndolos por su BFF.

Verificado de punta a punta sobre el sistema real:

| Comprobación | Resultado |
|---|---|
| 8 contenedores arriba (3 svc + 3 BD + Consul + web) | ✅ |
| `users-svc`, `booking-svc` y `notif-svc` en verde en Consul | ✅ `docs/evidencias/02-consul-3-servicios.png` |
| Registro → login con JWT → reservar → notificación | ✅ |
| booking-svc valida el usuario **por la API** de users-svc, nunca por su BD | ✅ |
| Un mismo `correlation_id` visible en los tres servicios | ✅ |
| `notif-svc` caído: 3 reservas → **201** con `notification: pending`, ningún 500 | ✅ |
| Circuit breaker `open` → `closed` y outbox vaciado solo al volver el servicio | ✅ |
| La web consume todo por su BFF, que descubre los servicios en Consul | ✅ `docs/evidencias/01-web-inicio.png` |

**Cómo levantarlo**

```bash
cp .env.example .env          # completar los valores
docker compose up --build     # http://localhost:3080  ·  Consul en :8500
```

En esta máquina el puerto 8001 está ocupado por otro contenedor y el 3000 por otro frontend: por eso
el `.env` local usa `BOOKING_PORT=8011` y la web sale en `3080`. Si tu red intercepta TLS (Zscaler y
similares), descomenta `PIP_TRUSTED_HOST` y `NPM_STRICT_SSL` en el `.env` o el build de las imágenes
falla con `CERTIFICATE_VERIFY_FAILED`.

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
| _Fuera del PDF, pedido por el equipo_ | — | 43–47 (app web) |

### Convenciones de dominio (PDF → BarberFlow)

| PDF (FitFlow) | BarberFlow |
|---|---|
| clase de fitness | servicio de barbería (corte clásico, corte + barba, afeitado, tinte, cejas) |
| horario de clase | *slot*: barbero + servicio + fecha/hora |
| instructor | barbero |
| `get_available_classes` | `get_available_slots` |
| `create_booking` / `cancel_booking` | iguales (cita) |

---

## Tareas de Andre (AM)

Ninguna de estas bloquea a nadie: se pueden hacer en cualquier orden, en paralelo con la ruta crítica.

| # | Tarea | Dep. | Done cuando |
|---|---|---|---|
| 3 | Leer los paquetes instalados `a2a-sdk==1.1.2` y `mcp==2.0.0` y anotar en `docs/` su API real (clases, ruta de la Agent Card, método `message/send`) | — | Existe la nota con las firmas reales, no escritas de memoria |
| 27 | Trazabilidad: comprobar que un mismo `correlation_id` se ve en users-svc → booking-svc → notif-svc | 10–22 | `docker compose logs \| jq 'select(.correlation_id=="…")'` muestra el viaje completo |
| 33 | `booking-agent` :9001 con `a2a-sdk`, Agent Card en `/.well-known/agent.json` **y** `/.well-known/agent-card.json`, skills vía MCP | 3, 30 | La card valida y `create_booking` por A2A crea la cita |
| 34 | `notification-agent` :9002, mismas dos rutas de card, skills vía MCP | 3, 31 | Notificación enviada por delegación A2A |
| 35 | `orchestrator` :9000: lee `AGENT_URLS`, descarga las cards y elige por `skills`; interpreta con la API de Claude y cae a keywords si no hay key | 33, 34 | *"Resérvame corte y barba el viernes y avísame"* reserva y notifica, y funciona sin `ANTHROPIC_API_KEY` |
| 36 | Los 3 agentes en el compose + logs A2A en JSON con `correlation_id` | 35 | Los logs muestran la delegación agente → agente paso a paso |
| 38 | README: gestión de secretos + **rotación de credenciales sin downtime** (pasos probados) | 10, 20 | La rotación se ejecuta de verdad sin que caiga ningún servicio |
| 39 | README: sección **Agent-to-Agent** explicando la diferencia entre MCP y A2A | 36 | Explica la diferencia con el diagrama del flujo real del proyecto |
| 41 | Despliegue en Railway: servicios, secretos como Variables del proveedor, URLs públicas, captura de Consul en la nube y guía paso a paso | 37 | Los servicios responden por URL pública y el compose local sigue funcionando |
| 42 | `ENTREGA.md` con checklist de la rúbrica (110 + 15) y evidencias + auditoría final de secretos en el historial de git | 40, 41 | Cada criterio del PDF tiene su fila, su estado y su evidencia enlazada |
| 47 | Panel de estado en la web: servicios registrados en Consul + estado del circuit breaker (`/admin/circuit`) | 25, 43 | La página muestra los 3 servicios en verde y el breaker abriéndose al caer notif-svc |

**Nota para Andre sobre la tarea 38:** el rol de aplicación de cada base lo crea el `init.sh` de su
servicio a partir de `APP_DB_USER`/`APP_DB_PASSWORD`. La rotación consiste en crear un rol nuevo con
los mismos grants, cambiar el `DATABASE_URL` del servicio, reiniciarlo con
`docker compose up -d --no-deps <svc>` y recién entonces borrar el rol viejo.

---

## Tareas de Estuardo (ES)

### Terminadas
Ver la tabla de estado arriba: 1, 2, 4, 5, 6, 7, 8, 9, 23 y el fix de bcrypt.

### En curso — los tres servicios y la web
| # | Tarea | Done cuando |
|---|---|---|
| 10–13 | **users-svc**: esquema + rol de menor privilegio, `/register`, `/login` (JWT), `/users/{id}`, salud, Consul, Dockerfile | Registro → login → token válido, y el servicio en verde en Consul |
| 14–19 | **booking-svc**: esquema y semilla de barbería, catálogo, horarios, crear/consultar/cancelar cita, validación del usuario **por API** de users-svc, llamada a notif-svc con `shared/resilience.py` | Una cita se crea con JWT y notifica; cancelar libera el horario |
| 20–22 | **notif-svc**: esquema, envío simulado con log estructurado, historial, salud, Consul, Dockerfile | El historial devuelve lo enviado y guarda el `correlation_id` |
| 24, 25 | **Outbox + `/admin/circuit`**: con notif-svc caído la cita se crea igual y la notificación queda `pending`; un task reintenta cada 15s | 201 en vez de 500 con el servicio caído, y el outbox se vacía solo al volver |
| 43–46 | **web-ui** (Next.js + TypeScript): BFF que descubre por Consul, registro/login, reservar, mis citas | El flujo completo funciona desde el navegador sin CORS ni URLs hardcodeadas |

### Pendientes
| # | Tarea | Dep. |
|---|---|---|
| 26 | Probar el caso de lista vacía (Consul ya desregistró notif-svc): 201 y no 500 | 24 |
| 28 | MCP Server: FastMCP streamable-http + Dockerfile + compose + Consul | 3 |
| 29 | Identidad del MCP: login con `DEMO_USER_*` desde `.env`, cache del JWT, re-login en 401 | 28 |
| 30 | Tools `get_available_slots`, `create_booking`, `cancel_booking` | 29 |
| 31 | Tools `send_notification`, `get_notifications` | 29 |
| 32 | Config de Claude Desktop (`docker exec --stdio` y `mcp-remote`) probada | 30, 31 |
| 37 | README: arquitectura, tabla de servicios, cómo correr, mapeo PDF → barbería | 22 |
| 40 | `demo.sh` con los 7 checkpoints del PDF + guion de video | 26, 32, 36 |

---

## Hallazgos que corrigen el enunciado

1. **El desregistro de Consul no tarda 30s.** Medido: **82.7s y 86.7s** desde que muere el `/healthz`.
   Consul eleva los 30s a un mínimo de 1m sin avisar (solo un `[WARN]` en su log) y además barre los
   checks muertos de forma periódica, así que el valor tiene *jitter*. La demo debe esperar ~90s.
   Método y evidencia: `docs/consul-ttl.md`, reproducible con `scripts/medir_ttl_consul.py`.
2. **Truncamiento silencioso de contraseñas** (corregido en el PR #8): recortar a 72 bytes antes de
   bcrypt hacía que dos contraseñas con el mismo prefijo sirvieran indistintamente para entrar.
   `POST /register` debe responder 422 ante una contraseña más larga.
3. **`pybreaker.call_async` es inservible** en 1.4.1: está detrás de `tornado`, que no se instala.
   La composición usa `breaker.calling()`.
4. **Follow-up menor:** `shared/consul.py` sigue enviando `DEREGISTER_AFTER = "30s"`. Es inofensivo
   —Consul lo eleva solo— pero engañoso al leer el código; cambiarlo a `"1m"` cabe en la tarea 26.

## Notas de ejecución

- **El video lo graba el equipo.** La tarea 40 entrega el script y el guion; la grabación es manual.
- **La tarea 41 necesita cuenta de Railway** antes de poder ejecutarse.
- **La tarea 35 funciona sin `ANTHROPIC_API_KEY`**: el orquestador cae a un parser por keywords, para
  que la demo no dependa de la red ni de una API key.
- Puertos internos = los del PDF. En el host son overridables (`.env`) porque en la máquina de
  desarrollo `8001`, `5432` y `3000` ya están ocupados; por eso la web sale por defecto en `3080`.
