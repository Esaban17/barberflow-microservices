# ENTREGA — BarberFlow (tarea 42)

Checklist de la rúbrica del curso (`proyecto-FitFlow_Proyecto_Mejorado.pdf`, dominio
adaptado a barbería) con su estado real y su evidencia. Fecha de este corte:
**11 de septiembre de 2026**.

Todo el trabajo está mergeado a `main` (PRs #1–#21) y el sistema completo —12 contenedores—
se levantó y se verificó en local en esta fecha. Lo único que no está ejecutado es el
despliegue en la nube de los puntos extra: ver la sección 5.

---

## 1. Rúbrica del PDF (110 + 15 pts)

| Criterio | Pts | Estado | Evidencia |
|---|---|---|---|
| Los 3 servicios corren con `docker compose up` y tienen DB propia | 20 | ✅ | `docker-compose.yml`; `docs/evidencias/01-web-inicio.png`; database-per-service en `services/{users,booking,notif}-svc/db/01-init.sql` (sin FKs cruzadas entre bases) |
| Los servicios se registran en Consul y se descubren dinámicamente | 20 | ✅ | `docs/evidencias/02-consul-3-servicios.png`; `shared/consul.py`; `docs/consul-ttl.md` (TTL real medido: 82.7s/86.7s, no los 30s que dice el PDF); paso 1 de `scripts/demo.sh` |
| MCP Server funciona: Claude puede crear una reserva | 20 | ✅ | `services/mcp-server/main.py` (tareas 28–31); `video_DEMO_mcp.mp4` (llamada real desde Claude); config de Claude Desktop probada con `mcp-remote` (tarea 32, `docs/a2a-mcp-api-notes.md`); pasos 6 y 7 de `scripts/demo.sh`, que ejercitan `initialize → tools/list → tools/call` contra el contenedor y comprueban la cita en `booking-db` |
| Circuit breaker demostrado: notif-svc cae, el sistema sigue | 20 | ✅ | `GET /admin/circuit` en `services/booking-svc/main.py` (tareas 24, 25); panel `/status` de la web (tarea 47) con sus dos capturas: `docs/evidencias/03-status-breaker-abierto.png` y `04-status-todo-verde.png`; pasos 4 y 5 de `scripts/demo.sh`: 3 reservas con notif-svc caído → 201 con `notification: pending`, breaker `open` con `fail_counter: 3` y `outbox_pending: 3`, y cierre solo al volver el servicio (`closed`, `outbox_pending: 0`) |
| JWT implementado + secretos fuera del código | 10 | ✅ | `shared/auth.py`; JWT con `sub`/`email`/`role` y 401 verificado en el paso 2 de `scripts/demo.sh`; `user_id` junto al `correlation_id` en los logs (paso 3); gestión de secretos y rotación sin downtime con dos procedimientos medidos (README, tarea 38 — ver sección 3); auditoría de secretos del historial en la sección 4 |
| Agent-to-Agent | 20 | ✅ | `services/{booking,notification}-agent/main.py` + `services/orchestrator/main.py` (tareas 33–36); Agent Card en `/.well-known/agent.json` **y** `/.well-known/agent-card.json` (ambas responden 200); sección "Agent-to-Agent: MCP vs. A2A" del README con el diagrama del flujo real (tarea 39) |
| **Extra** — despliegue cloud | +15 | ⚠️ Guía completa (+3); URL pública y secretos del proveedor (+12) **pendientes** | `docs/railway-deploy.md` (tarea 41) — ver sección 5 |
| _Fuera del PDF, pedido por el equipo_ — app web | — | ✅ | `web-ui/` (tareas 43–46) + panel de estado (tarea 47) |

**Total verificado: 110/110, más los +3 de la guía de despliegue. Los +12 restantes dependen
de ejecutar el despliegue (sección 5).**

### Verificación del 11 de septiembre de 2026

Sobre el sistema levantado con `docker compose up --build` (12 contenedores):

| Comprobación | Resultado |
|---|---|
| `./scripts/demo.sh` — los 7 checkpoints del PDF de corrido | ✅ pasa y deja el sistema como lo encontró |
| `users-svc`, `booking-svc`, `notif-svc` y `barberflow-mcp` en verde en Consul | ✅ |
| Registro → login → JWT → reserva con el mismo `correlation_id` en booking-svc y notif-svc | ✅ |
| 3 reservas con `notif-svc` detenido → 201 y `notification: pending` | ✅ breaker `open`, `fail_counter: 3`, `outbox_pending: 3` |
| `notif-svc` de vuelta → breaker `closed` y outbox vaciado sin intervención | ✅ las notificaciones encoladas llegaron a notif-svc |
| MCP por protocolo: `tools/list` (5 tools) → `get_available_slots` → `create_booking` → cita confirmada en `booking-db` → `cancel_booking` | ✅ |
| A2A en Docker: `POST /instruct` "Resérvame un corte… y avísame" | ✅ `plan_source: keywords` (sin `ANTHROPIC_API_KEY`), delegó en booking-agent (cita creada) y notification-agent (notificación enviada) |
| Claude Desktop conectado al MCP con `mcp-remote` | ✅ handshake y `tools/list` verificados por el puente |

## 2. Estado de las ramas y PRs (tarea 42 lo pide explícitamente)

Todo mergeado a `main`. Un PR por tarea o grupo de tareas:

| PR | Tarea(s) | Qué entrega |
|---|---|---|
| [#1](https://github.com/Esaban17/barberflow-microservices/pull/1)–[#7](https://github.com/Esaban17/barberflow-microservices/pull/7) | 4–9, 23 | Compose base, Consul, y los módulos de `shared/`: auth, db, logging, consul, resilience |
| [#8](https://github.com/Esaban17/barberflow-microservices/pull/8) | — | Fix: truncamiento silencioso de contraseñas en bcrypt |
| [#9](https://github.com/Esaban17/barberflow-microservices/pull/9) | 10–13 | `users-svc` completo |
| [#10](https://github.com/Esaban17/barberflow-microservices/pull/10) | 20–22 | `notif-svc` completo |
| [#11](https://github.com/Esaban17/barberflow-microservices/pull/11) | 14–19, 24, 25 | `booking-svc` + outbox + `/admin/circuit` |
| [#12](https://github.com/Esaban17/barberflow-microservices/pull/12) | 43–46 | `web-ui` (Next.js) con BFF que descubre por Consul |
| [#13](https://github.com/Esaban17/barberflow-microservices/pull/13) | 3 | API real de `a2a-sdk==1.1.2` y `mcp==2.0.0` |
| [#14](https://github.com/Esaban17/barberflow-microservices/pull/14) | 28–31 | `barberflow-mcp` con `MCPServer` streamable-http y sus 5 tools |
| [#15](https://github.com/Esaban17/barberflow-microservices/pull/15) | 33–36 | Red de agentes A2A |
| [#16](https://github.com/Esaban17/barberflow-microservices/pull/16) | 38 | Rotación de credenciales sin downtime |
| [#17](https://github.com/Esaban17/barberflow-microservices/pull/17) | 39 | Sección Agent-to-Agent: MCP vs. A2A |
| [#18](https://github.com/Esaban17/barberflow-microservices/pull/18) | 41 | Guía de despliegue en Railway |
| [#19](https://github.com/Esaban17/barberflow-microservices/pull/19) | 47 | Panel de estado `/status` |
| [#20](https://github.com/Esaban17/barberflow-microservices/pull/20) | 42 | Este documento (primera versión) |
| [#21](https://github.com/Esaban17/barberflow-microservices/pull/21) | 32, 37, 40 | Entrega final: README con arquitectura, `scripts/demo.sh`, capturas del panel y este corte |

## 3. Rotación de credenciales — resultado medido (tarea 38, detalle)

Ver la sección "Gestión de secretos y rotación de credenciales" del `README.md`
para el procedimiento completo. Resumen de los dos números que importan, medidos
contra Postgres real (no simulados):

- Restart de una sola instancia (`docker compose up -d --no-deps <svc>` tal cual):
  **≈0.99s de corte real** (poller externo, 15 peticiones fallidas seguidas).
- Rotación con dos instancias solapadas (blue/green vía Consul, aprovechando que
  `shared/resilience.call_service` redescubre en cada intento): **400 llamadas
  reales, 0 fallos**, mientras se mataba la instancia vieja y se borraba su rol a
  mitad del test.

## 4. Auditoría de secretos en el historial de git

Ejecutada contra el repo real, sobre **todas** las ramas (`git log --all`), no solo `main`.
El barrido con gitleaks es el del 7 de septiembre de 2026, sobre las 43 commits de esa fecha:

```
$ gitleaks detect --source . --log-opts="--all" --report-format json \
    --report-path gitleaks_report.json --exit-code 0 -v

9:25PM INF 43 commits scanned.
9:25PM INF scan completed in 946ms
9:25PM INF no leaks found
```

`gitleaks_report.json` resultante: `[]` (lista vacía, guardado en
`docs/evidencias/gitleaks-report.json`).

La segunda pasada —manual y específica a las variables de este proyecto— se volvió a correr
hoy, ya sobre las 57 commits del historial completo:

```
$ git log -p --all -- '*.env' '*.env.*' \
    | grep -E "^\+.*(PASSWORD|SECRET|API_KEY)=" \
    | grep -viE "=cambiar\s*$|=\s*$"

+DEMO_USER_PASSWORD=demo1234
+JWT_SECRET=cambiar-por-un-secreto-largo-y-aleatorio
```

Las dos líneas son de `.env.example` y ninguna es un secreto:

- `JWT_SECRET=cambiar-...` es el placeholder que el `.env.example` pide reemplazar.
- `DEMO_USER_PASSWORD=demo1234` es la contraseña del usuario de demostración, cuyo hash
  bcrypt ya está versionado —a propósito y desde el primer día— en la semilla
  `services/users-svc/db/01-init.sql`. No protege nada: existe para que `barberflow-mcp`
  pueda autenticarse contra `users-svc` en una demo local. Dejarla explícita en
  `.env.example` evita el `401` que aparecía al seguir el README al pie de la letra.

Y `.env` (el archivo con los secretos reales) nunca se agregó al repo:

```
$ git log --all --diff-filter=A --name-only | grep -E "^\.env$|/\.env$"
(sin resultados)
```

**Conclusión: ningún secreto real llegó al historial de git, en ninguna rama.**

## 5. Lo único que falta ejecutar

**Despliegue en Railway (tarea 41, los +12 restantes de los puntos extra).** La guía y la
configuración están completas en `docs/railway-deploy.md`, pero el despliegue real no se
ejecutó: ni el entorno donde se escribió la guía ni la máquina de desarrollo tienen salida
de red hacia `railway.app`/`railway.com` (bloqueado por política de red, confirmado con
`curl`). Para cerrarlo hace falta, desde una cuenta de Railway real:

1. Seguir la guía y desplegar los servicios.
2. Pegar en este documento las URLs públicas resultantes.
3. Adjuntar la captura de la UI de Consul en la nube a `docs/evidencias/`.
4. Mover los secretos a las Variables del proveedor (eso es lo que vale los +4).

El `docker-compose.yml` local sigue siendo válido para desarrollo, como pide el PDF.
