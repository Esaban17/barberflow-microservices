# Trazabilidad del `correlation_id` (tarea 27)

**Método.** Se levantaron los tres microservicios contra Postgres real (sin
Docker: Postgres local + un shim mínimo de la HTTP API de Consul, solo para
esta verificación) y se hizo una reserva de punta a punta a través del MCP
server (`create_booking`), que es el mismo camino que recorre una reserva real
desde la web o desde un agente. Se revisaron los logs JSON de los tres
servicios buscando el mismo `correlation_id`.

**Comando equivalente sobre el sistema real** (con `docker compose up`):

```bash
docker compose logs -f | jq 'select(.correlation_id=="<id>")'
```

## Evidencia (un `create_booking` real, tres servicios)

`correlation_id = 12742c96-7afa-42c6-a04c-dcb2095ae7c4` en los tres:

**users-svc** (el MCP server se loguea como el usuario demo, y booking-svc
valida ese usuario por la API — nunca por su BD):

```json
{"method": "POST", "path": "/login", "status_code": 200, "duration_ms": 277.33, "event": "http_request", "correlation_id": "12742c96-7afa-42c6-a04c-dcb2095ae7c4", "service": "users-svc", ...}
{"method": "GET", "path": "/users/1", "status_code": 200, "duration_ms": 2.5, "event": "http_request", "correlation_id": "12742c96-7afa-42c6-a04c-dcb2095ae7c4", "service": "users-svc", ...}
```

**booking-svc** (crea la cita; el mismo id que trajo el login):

```json
{"method": "POST", "path": "/appointments", "status_code": 201, "duration_ms": 242.71, "event": "http_request", "user_id": "1", "correlation_id": "12742c96-7afa-42c6-a04c-dcb2095ae7c4", "service": "booking-svc", ...}
```

**notif-svc** (booking-svc le propaga el mismo header al notificar):

```json
{"notification_id": 1, "user_id": 1, "channel": "log", "subject": "Cita confirmada", "event": "notification_sent", "correlation_id": "12742c96-7afa-42c6-a04c-dcb2095ae7c4", "service": "notif-svc", ...}
{"method": "POST", "path": "/notifications", "status_code": 201, "duration_ms": 8.9, "event": "http_request", "correlation_id": "12742c96-7afa-42c6-a04c-dcb2095ae7c4", "service": "notif-svc", ...}
```

## Cómo viaja

1. El cliente (web, MCP, o un agente) manda `x-correlation-id` o lo deja en
   blanco — `shared/logging.CorrelationIdMiddleware` genera uno con `uuid4()`
   si falta y lo bindea al contexto de `structlog` para el resto del request.
2. Cada llamada saliente entre servicios (`shared/resilience.call_service`)
   agrega el header con `correlation_headers()`, leído del mismo contexto.
3. El servicio destino recibe el header, su propio middleware lo respeta en
   vez de generar uno nuevo, y lo vuelve a bindear — así la cadena completa
   comparte un único id aunque cruce tres procesos y dos saltos HTTP.
4. `notif-svc` además lo persiste en la columna `correlation_id` de
   `notifications`, así que el historial de una notificación queda enlazado
   al request que la originó incluso después de que el log rote.

**Resultado: verificado.** Un mismo `correlation_id` es visible en
`users-svc → booking-svc → notif-svc` para un mismo flujo de reserva.
