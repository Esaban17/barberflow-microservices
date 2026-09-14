# ENTREGA — BarberFlow (tarea 42)

Checklist de la rúbrica del curso (`proyecto-FitFlow_Proyecto_Mejorado.pdf`, dominio
adaptado a barbería) con su estado real y su evidencia. Última actualización: **14 de
septiembre de 2026**, tras verificar el stack completo con Docker real en la laptop
del equipo.

---

## 1. Rúbrica del PDF (110 + 15 pts)

| Criterio | Pts | Estado | Evidencia |
|---|---|---|---|
| Los 3 servicios corren con `docker compose up` y tienen DB propia | 20 | ✅ | Stack completo (12 servicios) verificado arriba con `docker compose up --build` real — `docker compose ps` muestra las 3 BD `(healthy)` y los 3 servicios `Up`; database-per-service en `services/{users,booking,notif}-svc/db/01-init.sql` (sin FKs cruzadas entre bases) |
| Los servicios se registran en Consul y se descubren dinámicamente | 20 | ✅ | `docs/evidencias/02-consul-3-servicios.png`; `shared/consul.py`; `docs/consul-ttl.md` (TTL real medido: 82.7s/86.7s, no los 30s que dice el PDF) |
| MCP Server funciona: Claude puede crear una reserva | 20 | ✅ **verificado desde Claude Desktop real** | `services/mcp-server/main.py` (PR [#14](https://github.com/Esaban17/barberflow-microservices/pull/14), tareas 28–31); config real en `claude_desktop_config.json` (`mcp-remote` + Node vía ruta absoluta `npx.cmd`, necesario porque la app empaqueta su propio `PATH`); probado end-to-end contra el stack en Docker: `get_available_slots` devolvió horarios reales, `create_booking` creó la cita `id:3` con `notification:"sent"`, `get_notifications` la mostró en el historial. Video corto grabado (`docs/evidencias/videoDEMOmcp.mp4` — excede el límite de GitHub, descrito en el commit `a17b244`) |
| Circuit breaker demostrado: notif-svc cae, el sistema sigue | 20 | ✅ | `GET /admin/circuit` en `services/booking-svc/main.py` (tarea 25, ya en `main`); panel visual en vivo `/status` de la web-ui (PR [#19](https://github.com/Esaban17/barberflow-microservices/pull/19), tarea 47) — probado end-to-end: 3 reservas con notif-svc caído → 201 igual, breaker abre (`state: open, fail_counter: 3, outbox_pending: 3`), y cierra solo al volver el servicio (`outbox_pending: 0`) |
| JWT implementado + secretos fuera del código | 10 | ✅ | `shared/auth.py` (ya en `main`); gestión de secretos y rotación de credenciales sin downtime, con dos procedimientos medidos de verdad (PR [#16](https://github.com/Esaban17/barberflow-microservices/pull/16), tarea 38 — ver sección 3); auditoría de secretos en el historial de git en la sección 4 de este documento |
| Agent-to-Agent | 20 | ✅ | `services/{booking,notification}-agent/main.py` + `services/orchestrator/main.py` (PR [#15](https://github.com/Esaban17/barberflow-microservices/pull/15), tareas 33–36) — corriendo como contenedores reales (`barberflow-booking-agent`, `barberflow-notification-agent`, `barberflow-orchestrator` en `docker compose ps`); sección "Agent-to-Agent: MCP vs. A2A" del README con diagrama Mermaid del flujo real (PR [#17](https://github.com/Esaban17/barberflow-microservices/pull/17), tarea 39) |
| **Extra** — despliegue cloud | +15 | ⚠️ Config y guía completas; despliegue real pendiente | `docs/railway-deploy.md` (PR [#18](https://github.com/Esaban17/barberflow-microservices/pull/18), tarea 41) — ver sección 5 |
| _Fuera del PDF, pedido por el equipo_ — app web | — | ✅ | `web-ui/` (tareas 43–46, ya en `main`) + panel de estado (tarea 47), corriendo en `http://localhost:3080` |

**Total con lo verificado hasta hoy: 110/110 + config lista de los +15 extra (ejecución
real en Railway pendiente, ver sección 5).**

**Entregable final del PDF** ("Repositorio GitHub + README + video demo de 5–8 min"):
repo y README completos; el video de 5–8 min cubriendo TODO el checklist (no solo el
demo de MCP que ya existe) todavía no está grabado — ver sección 5.

## 2. Estado de las ramas y PRs

Todas las ramas de Andre (AM) están subidas, con PR abierto y **mergeadas a `main`**:

| Rama | Tarea(s) | PR |
|---|---|---|
| `feat/booking-svc`, `feat/notif-svc`, `feat/users-svc`, `feat/web-svc`, `feat/task-04-compose-base`, `feat/task-05-logging`, `feat/task-06-db`, `feat/task-07-auth`, `feat/task-08-consul`, `feat/task-09-resilience`, `feat/task-23-consul-ttl` | 1, 2, 4–26, 43–46 (ES) | [#1–#12](https://github.com/Esaban17/barberflow-microservices/pulls?q=is%3Apr+is%3Amerged) |
| `docs/a2a-mcp-api-notes` | 3 | [#13](https://github.com/Esaban17/barberflow-microservices/pull/13) ✅ mergeado |
| `feat/mcp-server` | 28–31 (bloqueaban 33-36 de AM) | [#14](https://github.com/Esaban17/barberflow-microservices/pull/14) ✅ mergeado |
| `feat/a2a-agents` | 33–36 | [#15](https://github.com/Esaban17/barberflow-microservices/pull/15) ✅ mergeado |
| `docs/rotacion-credenciales` | 38 | [#16](https://github.com/Esaban17/barberflow-microservices/pull/16) ✅ mergeado |
| `docs/a2a-vs-mcp` | 39 | [#17](https://github.com/Esaban17/barberflow-microservices/pull/17) ✅ mergeado |
| `docs/railway-deploy` | 41 | [#18](https://github.com/Esaban17/barberflow-microservices/pull/18) ✅ mergeado |
| `feat/web-status-panel` | 47 | [#19](https://github.com/Esaban17/barberflow-microservices/pull/19) ✅ mergeado |
| `docs/entrega` | 42 | [#20](https://github.com/Esaban17/barberflow-microservices/pull/20) ✅ mergeado |

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

Ejecutada contra el repo real, las 43 commits de **todas** las ramas locales
(`git log --all`), no solo `main`:

```
$ gitleaks detect --source . --log-opts="--all" --report-format json \
    --report-path gitleaks_report.json --exit-code 0 -v

9:25PM INF 43 commits scanned.
9:25PM INF scan completed in 946ms
9:25PM INF no leaks found
```

`gitleaks_report.json` resultante: `[]` (lista vacía).

Como segunda pasada, manual y específica a las variables de este proyecto (por si
el ruleset genérico de gitleaks no cubriera algún patrón propio):

```
$ git log -p --all -- '*.env' '*.env.*' \
    | grep -E "^\+.*(PASSWORD|SECRET|API_KEY)=" \
    | grep -viE "=cambiar\s*$|=\s*$"

+JWT_SECRET=cambiar-por-un-secreto-largo-y-aleatorio
```

La única línea que aparece es el placeholder de `.env.example` (`cambiar-...`),
nunca un valor real. Y `.env` (el archivo con los secretos reales) nunca se
agregó al repo:

```
$ git log --all --diff-filter=A --name-only | grep -E "^\.env$|/\.env$"
(sin resultados)
```

**Conclusión: ningún secreto real llegó al historial de git, en ninguna rama.**

## 5. Lo que falta ejecutar de verdad (para quien retome esto)

1. **Video demo de 5–8 min** (entregable final del PDF): ya existe un clip corto
   mostrando el MCP desde Claude Desktop (agenda una cita), pero falta el video
   completo cubriendo el "Video Checkpoint" de la tarea 4 y el checkpoint de la
   tarea 5:
   - `docker compose up` → Consul en `localhost:8500` con los servicios en verde
   - Registrar un usuario → login → mostrar el JWT recibido
   - Crear una reserva usando el JWT → ver el log JSON con `correlation_id`
   - Derribar `notif-svc` → hacer reservas → mostrar que el sistema sigue
     respondiendo → mostrar el circuit breaker abierto (panel `/status` o
     `GET /admin/circuit`)
   - Levantar `notif-svc` → circuit breaker se cierra
   - El clip de MCP que ya existe (Claude Desktop listando y reservando)
   - Demo de A2A: instrucción en lenguaje natural al `orchestrator` → delega a
     `booking-agent` + `notification-agent` → logs de la delegación
2. **Railway (tarea 41, los +15 extra):** la guía y toda la configuración están
   listas en `docs/railway-deploy.md`, pero el despliegue real no se ejecutó — ni
   el entorno de nube ni la VM del dispositivo usados para el resto del trabajo
   tienen salida de red hacia `railway.app`/`railway.com` (bloqueado por política
   de red, confirmado con `curl`). Hace falta correrlo desde una cuenta de Railway
   real, siguiendo la guía, y pegar aquí las URLs públicas resultantes + una
   captura de la UI de Consul en la nube (eso es lo que pide el "Done cuando" de
   la tarea 41).
3. **Captura de pantalla del panel `/status`** (tarea 47) en los dos estados (todo
   verde, y con el breaker abierto) para `docs/evidencias/` — se verificó por API
   pero no se tomó captura de la UI todavía.
