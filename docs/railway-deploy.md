# Despliegue en Railway (tarea 41)

**Estado de esta tarea:** la configuración de abajo (Dockerfiles, variables,
networking) está lista y usa exactamente las mismas imágenes/roles/init-scripts
que `docker-compose.yml` local — no hay nada inventado ni "a ver si funciona".
Lo que **no** se pudo hacer desde aquí es ejecutar el `railway up` real: tanto
este entorno en la nube como la VM aislada donde corre el resto de este backlog
tienen bloqueado por política de red el dominio de Railway (`railway.app`,
`railway.com`, `backboard.railway.app` — probado con `curl`, error `403` del
proxy de salida). El despliegue real necesita tu cuenta de Railway y correr
desde tu navegador/CLI normal, no desde aquí. Esta guía es el paso a paso para
que lo hagas en ~20-30 minutos; lo único que falta después es pegar aquí (o en
`ENTREGA.md`, tarea 42) las URLs públicas reales que te dé Railway.

## 0. Qué NO cambia

El `docker compose up --build` local sigue funcionando exactamente igual — no
se tocó `docker-compose.yml` ni ningún `Dockerfile` existente. Lo único nuevo
son tres `Dockerfile` chiquitos (`services/{users,booking,notif}-svc/db/Dockerfile`)
que Railway necesita y que el compose local ignora por completo.

## 1. Por qué las bases de datos necesitan un Dockerfile propio

Localmente, `x-db-common` usa la imagen oficial `postgres:16-alpine` sin
modificar y monta `./services/<svc>/db` como `/docker-entrypoint-initdb.d:ro`
(bind-mount de archivos del repo hacia el contenedor en runtime). Railway no
tiene equivalente a "bind-mount un directorio del repo dentro de una imagen
pública en runtime": para que el rol de aplicación (`APP_DB_USER`/
`APP_DB_PASSWORD`) se cree igual que en local, esos mismos `01-init.sql` y
`02-init.sh` tienen que estar copiados **dentro** de la imagen que Railway
construye. Por eso existen ahora `services/users-svc/db/Dockerfile`,
`services/booking-svc/db/Dockerfile` y `services/notif-svc/db/Dockerfile`:

```dockerfile
FROM postgres:16-alpine
COPY . /docker-entrypoint-initdb.d/
```

El entrypoint oficial de Postgres sigue ejecutando esos archivos en el mismo
orden alfabético de siempre (`01-init.sql` crea el esquema, `02-init.sh` crea
el rol de aplicación) — el comportamiento es idéntico al de local, solo cambia
CUÁNDO se copian los archivos (build time en vez de bind-mount en runtime).

> Alternativa más rápida (no recomendada para este proyecto): usar el plugin
> nativo "PostgreSQL" de Railway y correr el SQL de `02-init.sh` a mano una vez,
> vía `railway connect <db>` + `psql`. Funciona, pero hay que repetirlo a mano
> si el volumen se recrea, y no queda versionado en el repo — por eso la guía
> usa el Dockerfile propio como camino principal.

## 2. Servicios a crear en el proyecto de Railway

Un solo proyecto de Railway, un "environment" (`production`), 15 servicios:

| Servicio Railway | Fuente | Root directory | Dockerfile path | Puerto interno | Dominio público |
|---|---|---|---|---|---|
| `consul` | Imagen pública `hashicorp/consul:1.17` | — | — | 8500 | sí (para inspeccionar la UI: tarea 41 pide "captura de Consul en la nube") |
| `users-db` | Este repo | `.` | `services/users-svc/db/Dockerfile` | 5432 | no |
| `booking-db` | Este repo | `.` | `services/booking-svc/db/Dockerfile` | 5432 | no |
| `notif-db` | Este repo | `.` | `services/notif-svc/db/Dockerfile` | 5432 | no |
| `users-svc` | Este repo | `.` | `services/users-svc/Dockerfile` | 8003 | sí |
| `booking-svc` | Este repo | `.` | `services/booking-svc/Dockerfile` | 8001 | sí |
| `notif-svc` | Este repo | `.` | `services/notif-svc/Dockerfile` | 8002 | sí |
| `barberflow-mcp` | Este repo | `.` | `services/mcp-server/Dockerfile` | 8000 | sí |
| `booking-agent` | Este repo | `.` | `services/booking-agent/Dockerfile` | 9001 | sí |
| `notification-agent` | Este repo | `.` | `services/notification-agent/Dockerfile` | 9002 | sí |
| `orchestrator` | Este repo | `.` | `services/orchestrator/Dockerfile` | 9000 | sí |
| `web-ui` | Este repo | `web-ui` | `Dockerfile` (Railway lo detecta solo) | 3000 | **sí, este es el que usan las personas** |

El "Root directory" en `.` para los servicios Python es a propósito: sus
`Dockerfile` hacen `COPY shared/ ./shared/` con contexto en la raíz del repo
(igual que `context: .` en `docker-compose.yml`), así que Railway tiene que
construir con ese mismo contexto — solo cambia el `Dockerfile Path` para
apuntar al de cada servicio. `web-ui` es la excepción: su Dockerfile ya asume
contexto propio (`context: ./web-ui` en compose), así que ahí sí el root
directory es `web-ui`.

Para cada servicio "Este repo": en el dashboard de Railway, **New → GitHub
Repo → `Esaban17/barberflow-microservices`**, y en Settings → Build configurar
Root Directory y Dockerfile Path según la tabla. (Los nombres exactos de estos
campos en el dashboard pueden variar según la versión de Railway — si no
aparecen tal cual, buscar la sección "Build" de Settings del servicio.)

## 3. Volúmenes (persistencia de las 3 bases)

`users-db`, `booking-db` y `notif-db` necesitan un Volume de Railway montado en
`/var/lib/postgresql/data` cada uno (equivalente a `users-db-data`,
`booking-db-data`, `notif-db-data` en el compose local). Sin esto, cada
redeploy borra los datos.

## 4. Networking privado (equivalente a la red `barberflow` de docker compose)

Railway resuelve servicios del mismo proyecto/environment entre sí por
`<nombre-del-servicio>.railway.internal` cuando el "Private Networking" del
environment está activo (viene activo por defecto en proyectos nuevos). Eso
reemplaza uno a uno los nombres de contenedor que usa el compose local:

| Nombre en compose local | Nombre en Railway (privado) |
|---|---|
| `consul` | `consul.railway.internal` |
| `users-db`, `booking-db`, `notif-db` | `users-db.railway.internal`, etc. |
| `users-svc`, `booking-svc`, `notif-svc` | `users-svc.railway.internal`, etc. |
| `barberflow-mcp` | `barberflow-mcp.railway.internal` |

El health check HTTP que Consul le hace a cada servicio (`shared/consul.py`
registra `Address=<SERVICE_ADDRESS>`) también viaja por esta red privada, así
que `SERVICE_ADDRESS` de cada servicio tiene que ser su propio nombre
`*.railway.internal` (ver tabla de variables abajo) para que Consul pueda
alcanzarlo.

## 5. Variables por servicio

Variables compartidas por todos los servicios Python (crear como "Shared
Variables" del environment y referenciarlas con `${{shared.NOMBRE}}` en cada
servicio, para no repetirlas 8 veces):

```
JWT_SECRET=<el mismo valor que en tu .env>
CONSUL_HTTP_ADDR=http://consul.railway.internal:8500
```

Variables propias de cada servicio (usar el nombre real del servicio en
`SERVICE_ADDRESS`, no "localhost" ni el nombre del contenedor local):

```
# users-svc
SERVICE_NAME=users-svc
SERVICE_ADDRESS=users-svc.railway.internal
SERVICE_PORT=8003
DATABASE_URL=postgresql://${USERS_APP_USER}:${USERS_APP_PASSWORD}@users-db.railway.internal:5432/${USERS_DB_NAME}

# booking-svc — igual, cambiando el prefijo BOOKING_ y el puerto 8001
# notif-svc   — igual, cambiando el prefijo NOTIF_ y el puerto 8002

# barberflow-mcp
SERVICE_NAME=barberflow-mcp
SERVICE_ADDRESS=barberflow-mcp.railway.internal
SERVICE_PORT=8000
DEMO_USER_EMAIL=demo@barberflow.local
DEMO_USER_PASSWORD=<el mismo valor que en tu .env>

# orchestrator
SERVICE_NAME=orchestrator
SERVICE_ADDRESS=orchestrator.railway.internal
SERVICE_PORT=9000
AGENT_URLS=http://booking-agent.railway.internal:9001,http://notification-agent.railway.internal:9002
ANTHROPIC_API_KEY=<opcional — sin ella el orquestador cae a keywords>

# booking-agent / notification-agent — SERVICE_NAME/SERVICE_ADDRESS/SERVICE_PORT
# análogos (9001 / 9002), sin variables extra

# web-ui
CONSUL_HTTP_ADDR=http://consul.railway.internal:8500
```

Y para cada base (`users-db`/`booking-db`/`notif-db`), las mismas 5 variables
que ya tienes en `.env` (`*_DB_SUPERUSER`, `*_DB_SUPERPASSWORD`, `*_DB_NAME`,
más `APP_DB_USER`/`APP_DB_PASSWORD` — ojo que el Dockerfile del paso 1 espera
estos dos últimos nombres genéricos, tal como los lee `02-init.sh`, no el
prefijo `BOOKING_`/`USERS_`/`NOTIF_`):

```
POSTGRES_USER=${BOOKING_DB_SUPERUSER}
POSTGRES_PASSWORD=${BOOKING_DB_SUPERPASSWORD}
POSTGRES_DB=${BOOKING_DB_NAME}
APP_DB_USER=${BOOKING_APP_USER}
APP_DB_PASSWORD=${BOOKING_APP_PASSWORD}
```

**Los valores reales de secretos van directo en las Variables de Railway, no
en ningún archivo de este repo** — es exactamente el punto de la tarea 41
("secretos como Variables del proveedor") y sigue el mismo principio que la
tarea 38 (nunca commitear `.env`).

## 6. Orden de despliegue recomendado

1. `consul` primero (nada depende de él para construir, todo depende de él en
   runtime).
2. Las 3 bases (`users-db`, `booking-db`, `notif-db`) con sus volúmenes.
3. `users-svc`, `booking-svc`, `notif-svc`.
4. `barberflow-mcp` (depende de `users-svc` para el login demo).
5. `booking-agent`, `notification-agent` (dependen de `barberflow-mcp`).
6. `orchestrator` (depende de los dos agentes).
7. `web-ui` al final.

Railway no tiene un `depends_on: condition: service_healthy` como compose —
si un servicio arranca antes de que su dependencia esté lista, sus reintentos
con backoff (`shared/resilience.py`, ya construido en la tarea 9) lo cubren:
tolera que un destino no responda todavía y no hace falta orquestar el orden
al segundo. Aun así, desplegar en el orden de arriba evita ruido innecesario
en los logs del primer arranque.

## 7. Verificación (esto es lo que falta ejecutar de verdad)

Una vez desplegado, con las URLs públicas que Railway asigna a cada servicio
(Settings → Networking → Generate Domain):

```bash
curl https://<url-publica-de-users-svc>/healthz
curl https://<url-publica-de-booking-svc>/healthz
curl https://<url-publica-de-notif-svc>/healthz
curl https://<url-publica-de-consul>/v1/status/leader   # o abrir la UI en el navegador
curl -X POST https://<url-publica-de-orchestrator>/instruct \
  -H 'Content-Type: application/json' \
  -d '{"text": "Resérvame un corte clásico el viernes y avísame"}'
```

Y confirmar en la UI de Consul (URL pública del servicio `consul`, puerto 8500)
que los 3 microservicios de negocio (`users-svc`, `booking-svc`, `notif-svc`)
aparecen registrados y en verde — esa captura es la evidencia que pide el
"Done cuando" de la tarea 41, y va en `ENTREGA.md` (tarea 42).

**Siguiente paso real:** correr esto desde tu cuenta de Railway (dashboard o
`npx @railway/cli`, que si tiene salida de red desde tu máquina) y pegar las
URLs públicas resultantes aquí o en `ENTREGA.md`.
