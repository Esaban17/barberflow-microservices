# Contrato de APIs de BarberFlow

Este documento es **la fuente de verdad** para implementar y consumir los servicios. Se escribió
antes que el código para que los tres microservicios y la web se pudieran construir en paralelo
sin verse entre sí. Si algo aquí no cuadra con el código, gana este documento: se corrige el código.

Reglas transversales:

- Todo es JSON. Las peticiones con cuerpo llevan `Content-Type: application/json`.
- Fechas en **ISO-8601 UTC** (`2026-08-22T15:00:00Z`).
- Errores con el formato de FastAPI: `{"detail": "mensaje"}`.
- Los endpoints marcados 🔒 exigen `Authorization: Bearer <jwt>`; sin token o con token inválido
  o expirado responden **401**.
- Todos los servicios aceptan y propagan el header `x-correlation-id` (lo maneja
  `shared/logging.py`; ver `shared/resilience.py` para las llamadas salientes).
- Todos exponen `GET /healthz` → `200 {"status":"ok"}` (no toca la BD) y `GET /readyz` →
  `200 {"status":"ok","database":"up"}` o `503 {"status":"error","database":"down"}`.
- Ningún servicio lee la base de datos de otro. Si booking-svc necesita un usuario, llama a la
  API de users-svc.

---

## users-svc — puerto interno 8003

### `POST /register` → 201
```json
{"email":"ana@example.com","password":"secreta123","full_name":"Ana López","phone":"+502 5555-1234"}
```
`phone` es opcional. `role` opcional, `"client"` (default) o `"barber"`.

Respuesta: `{"id":1,"email":"…","full_name":"…","phone":"…","role":"client","created_at":"…"}`
(**nunca** el hash de la contraseña).

Errores: **409** email ya registrado · **422** datos inválidos, incluida contraseña de más de
72 bytes (bcrypt no admite más; ver `shared/auth.py`).

### `POST /login` → 200
```json
{"email":"ana@example.com","password":"secreta123"}
```
Respuesta:
```json
{"access_token":"eyJ…","token_type":"bearer","expires_in":3600,
 "user":{"id":1,"email":"…","full_name":"…","role":"client"}}
```
Errores: **401** credenciales inválidas (mismo mensaje para email inexistente y contraseña
equivocada: no se revela cuál de los dos falló).

### `GET /users/{id}` → 200
El mismo objeto de `/register`. **404** si no existe. Lo usa booking-svc para validar al usuario
de una cita.

---

## booking-svc — puerto interno 8001

### `GET /services` → 200
```json
[{"id":1,"name":"Corte clásico","duration_min":30,"price":75.00}]
```

### `GET /barbers` → 200
```json
[{"id":1,"name":"Marco Ruiz","chair":1}]
```

### `GET /slots` → 200
Query opcional: `date=YYYY-MM-DD`, `service_id`, `barber_id`. Devuelve **solo horarios libres y
futuros**, ordenados por `starts_at`.
```json
[{"id":12,"barber_id":1,"barber_name":"Marco Ruiz","service_id":1,
  "service_name":"Corte clásico","starts_at":"2026-08-22T15:00:00Z",
  "duration_min":30,"price":75.00}]
```

### `POST /appointments` 🔒 → 201
```json
{"slot_id":12}
```
El `user_id` sale del token, **no** del cuerpo. Flujo: valida el slot → confirma que el usuario
existe llamando a `GET /users/{id}` de users-svc → marca el slot como reservado → crea la cita →
intenta notificar a notif-svc.
```json
{"id":5,"user_id":1,"status":"confirmed","created_at":"…",
 "slot":{"id":12,"starts_at":"…","service_name":"Corte clásico","barber_name":"Marco Ruiz"},
 "notification":"sent"}
```
`notification` es `"sent"` o `"pending"`. **Si notif-svc está caído la cita se crea igual**, la
notificación queda en el outbox y este campo dice `"pending"`: nunca un 500 (tarea 24).

Errores: **401** sin token · **404** slot inexistente · **409** slot ya reservado ·
**502** el usuario del token ya no existe en users-svc.

### `GET /appointments` 🔒 → 200
Las citas del usuario del token, más recientes primero. Mismo objeto que `POST`, sin
`notification`. Acepta `status=confirmed|cancelled`.

### `GET /appointments/{id}` 🔒 → 200
**404** si no existe · **403** si la cita es de otro usuario.

### `DELETE /appointments/{id}` 🔒 → 200
Cancela y **libera el slot**. `{"id":5,"status":"cancelled"}`.
**404** si no existe · **403** si es de otro usuario · **409** si ya estaba cancelada.

### `GET /admin/circuit` → 200
Estado del circuit breaker hacia notif-svc y del outbox. Alimenta la demo y el panel de la web.
```json
{"target":"notif-svc","state":"closed","fail_counter":0,"outbox_pending":0}
```

---

## notif-svc — puerto interno 8002

### `POST /notifications` → 201
```json
{"user_id":1,"subject":"Cita confirmada","body":"Tu corte es el sábado a las 15:00","channel":"log"}
```
`channel` opcional (`"log"` por defecto). El envío real se simula con un log estructurado.
Respuesta: `{"id":9,"user_id":1,"subject":"…","body":"…","channel":"log","status":"sent","created_at":"…"}`.
Guarda el `correlation_id` del request para poder rastrear el viaje completo.

### `GET /notifications?user_id=1` → 200
Historial del usuario, más recientes primero. `user_id` es obligatorio.

---

## web-ui — puerto interno 3000 (Next.js)

El navegador **solo** habla con Next. Sus route handlers actúan de BFF: descubren cada servicio
en Consul y reenvían la llamada, propagando el `Authorization` y el `x-correlation-id`. Así no
hay CORS ni URLs de servicios en el cliente.

| Ruta del BFF | Reenvía a |
|---|---|
| `/api/users/*` | users-svc |
| `/api/booking/*` | booking-svc |
| `/api/notif/*` | notif-svc |
| `/api/status` | Consul (`/v1/health/state/any`) + `booking-svc /admin/circuit` |
