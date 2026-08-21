# web-ui — la app web de BarberFlow

Next.js (App Router, TypeScript, Tailwind). El navegador **solo** habla con Next:
sus route handlers hacen de BFF, descubren cada microservicio en Consul y reenvían
la llamada. Por eso no hay CORS ni URLs de servicios en el cliente.

| Ruta del BFF        | Reenvía a     |
| ------------------- | ------------- |
| `/api/users/*`      | `users-svc`   |
| `/api/booking/*`    | `booking-svc` |
| `/api/notif/*`      | `notif-svc`   |

- Descubrimiento: `GET $CONSUL_HTTP_ADDR/v1/health/service/<nombre>?passing`.
  Sin instancias sanas el BFF responde **503** `{"detail":"<servicio> no disponible"}`.
- Propaga `Authorization` y `x-correlation-id` (lo genera si el navegador no lo manda).
- `CONSUL_HTTP_ADDR` es de servidor: sin `NEXT_PUBLIC_`, nunca llega al bundle.

## Correr en local

```bash
npm install
CONSUL_HTTP_ADDR=http://localhost:8500 npm run dev   # http://localhost:3000
```

Dentro de `docker compose` la variable ya viene puesta a `http://consul:8500`
y el contenedor escucha en el puerto 3000 (publicado en `${WEB_PORT:-3080}`).

## Imagen

```bash
docker build -t barberflow-web ./web-ui
```
