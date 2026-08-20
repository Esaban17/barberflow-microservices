# BarberFlow — Plataforma de reservas para barbería/peluquería

Sistema de reservas de citas de barbería construido con arquitectura de microservicios:
tres servicios independientes con base de datos propia, service registry con Consul,
un MCP Server para operar el sistema con agentes de IA, y una red de agentes A2A.

> Proyecto del curso **Arquitectura de Componentes y Microservicios** — Universidad Galileo, FISICC.
> El backlog de implementación está en [`docs/BACKLOG.md`](docs/BACKLOG.md).

## Componentes

| Servicio | Puerto | Qué hace |
|---|---|---|
| `users-svc` | 8003 | Registro y autenticación de usuarios (JWT) |
| `booking-svc` | 8001 | Gestión de citas, servicios de barbería y horarios |
| `notif-svc` | 8002 | Envío e historial de notificaciones |
| `barberflow-mcp` | 8000 | Expone BarberFlow a agentes de IA vía MCP |
| `consul` | 8500 | Registro y descubrimiento de servicios |
| `orchestrator` / `booking-agent` / `notification-agent` | 9000–9002 | Red de agentes A2A |

## Cómo correr

```bash
cp .env.example .env    # completar los valores
docker compose up --build
```

_Este README se completa en la tarea 37 del backlog (arquitectura, rotación de credenciales, A2A vs MCP)._
