# ENTREGA — BarberFlow (tarea 42)

Checklist de la rúbrica del curso (`proyecto-FitFlow_Proyecto_Mejorado.pdf`, dominio
adaptado a barbería) con su estado real y su evidencia. Fecha de este corte: **7 de
septiembre de 2026**.

> **Nota sobre el estado de las ramas de Andre (AM) al momento de escribir esto:**
> las tareas 3, 27, 33–36, 38, 39, 41 y 47 están implementadas, probadas contra
> servicios reales (Postgres real, no mocks) y committeadas — pero en ramas locales
> que todavía no se subieron a GitHub ni tienen PR abierto (ver la tabla de la
> sección 2). Esta tabla se debe releer y actualizar (números de PR reales) en
> cuanto esas ramas estén subidas y con PR.

---

## 1. Rúbrica del PDF (110 + 15 pts)

| Criterio | Pts | Estado | Evidencia |
|---|---|---|---|
| Los 3 servicios corren con `docker compose up` y tienen DB propia | 20 | ✅ | `docker-compose.yml`; `docs/evidencias/01-web-inicio.png`; database-per-service en `services/{users,booking,notif}-svc/db/01-init.sql` (sin FKs cruzadas entre bases) |
| Los servicios se registran en Consul y se descubren dinámicamente | 20 | ✅ | `docs/evidencias/02-consul-3-servicios.png`; `shared/consul.py`; `docs/consul-ttl.md` (TTL real medido: 82.7s/86.7s, no los 30s que dice el PDF) |
| MCP Server funciona: Claude puede crear una reserva | 20 | ✅ (probado sin Docker, contra Postgres real) | `services/mcp-server/main.py` (rama `feat/mcp-server`, tareas 28–31 — bloqueaban las tareas 33-36 de Andre y se implementaron para no frenar el resto); config de Claude Desktop documentada en `docs/a2a-mcp-api-notes.md` (tarea 32, misma rama) |
| Circuit breaker demostrado: notif-svc cae, el sistema sigue | 20 | ✅ | `GET /admin/circuit` en `services/booking-svc/main.py` (tarea 25, ya en `main`); panel visual en vivo `/status` de la web-ui (rama `feat/web-status-panel`, tarea 47) — probado end-to-end: 3 reservas con notif-svc caído → 201 igual, breaker abre (`state: open, fail_counter: 3, outbox_pending: 3`), y cierra solo al volver el servicio (`outbox_pending: 0`) |
| JWT implementado + secretos fuera del código | 10 | ✅ | `shared/auth.py` (ya en `main`); gestión de secretos y rotación de credenciales sin downtime, con dos procedimientos medidos de verdad (rama `docs/rotacion-credenciales`, tarea 38 — ver sección 3); auditoría de secretos en el historial de git en la sección 4 de este documento |
| Agent-to-Agent | 20 | ✅ (probado sin Docker, contra Postgres real) | `services/{booking,notification}-agent/main.py` + `services/orchestrator/main.py` (rama `feat/a2a-agents`, tareas 33–36); sección "Agent-to-Agent: MCP vs. A2A" del README con diagrama Mermaid del flujo real (rama `docs/a2a-vs-mcp`, tarea 39) |
| **Extra** — despliegue cloud | +15 | ⚠️ Config y guía completas; despliegue real pendiente | `docs/railway-deploy.md` (rama `docs/railway-deploy`, tarea 41) — ver sección 5, "Lo que falta ejecutar de verdad" |
| _Fuera del PDF, pedido por el equipo_ — app web | — | ✅ | `web-ui/` (tareas 43–46, ya en `main`) + panel de estado (tarea 47) |

**Total con lo verificado hasta hoy: 110/110 + config lista de los +15 extra (ejecución
real pendiente, ver sección 5).**

## 2. Estado de las ramas (evidencia de PR, tarea 42 lo pide explícitamente)

| Rama | Tarea(s) | Commit | PR |
|---|---|---|---|
| `feat/booking-svc`, `feat/notif-svc`, `feat/users-svc`, `feat/web-svc`, `feat/task-04-compose-base`, `feat/task-05-logging`, `feat/task-06-db`, `feat/task-07-auth`, `feat/task-08-consul`, `feat/task-09-resilience`, `feat/task-23-consul-ttl` | 1, 2, 4–26, 43–46 (ES) | — | Ver tabla de PRs en `docs/BACKLOG.md` (#1–#12), todas mergeadas a `main` |
| `docs/a2a-mcp-api-notes` | 3 | `71db404` | pendiente de subir + abrir PR |
| `feat/mcp-server` | 28–31 (bloqueaban 33-36 de AM) | `55ecafb` | pendiente de subir + abrir PR |
| `feat/a2a-agents` | 33–36 | `fa5a464` | pendiente de subir + abrir PR |
| `docs/rotacion-credenciales` | 38 | `9091871` | pendiente de subir + abrir PR |
| `docs/a2a-vs-mcp` (sobre `docs/rotacion-credenciales`) | 39 | `28f56aa` | pendiente de subir + abrir PR |
| `docs/railway-deploy` | 41 | `9ac3826` | pendiente de subir + abrir PR |
| `feat/web-status-panel` | 47 | `5030b88` | pendiente de subir + abrir PR |

Estas 7 ramas existen y están committeadas en el checkout local del repo, pero el
`git push` no se pudo hacer desde el entorno donde se generó este trabajo (sandbox
en la nube sin credenciales de GitHub configuradas) — hace falta correr
`git push -u origin <rama>` desde una terminal con acceso normal a GitHub y abrir
el PR de cada una, igual que las de Estuardo.

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

1. **Subir las 7 ramas de la tabla de la sección 2** y abrir su PR (mismo flujo que
   ya usó Estuardo — un PR por tarea/grupo de tareas).
2. **Railway (tarea 41, los +15 extra):** la guía y toda la configuración están
   listas en `docs/railway-deploy.md`, pero el despliegue real no se ejecutó — ni
   este entorno ni la VM del dispositivo donde se hizo el resto del trabajo tienen
   salida de red hacia `railway.app`/`railway.com` (bloqueado por política de red,
   confirmado con `curl`). Hace falta correrlo desde una cuenta de Railway real,
   siguiendo la guía, y pegar aquí las URLs públicas resultantes + una captura de
   la UI de Consul en la nube (eso es lo que pide el "Done cuando" de la tarea 41).
3. **Captura de pantalla del panel `/status`** (tarea 47) en los dos estados (todo
   verde, y con el breaker abierto) para `docs/evidencias/` — se verificó por API
   (`curl /api/status`) pero no se tomó captura de la UI todavía.
