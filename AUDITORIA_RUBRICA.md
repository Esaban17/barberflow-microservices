# Auditoría final contra la rúbrica del PDF

Revisión de código real (no solo lo que dice `ENTREGA.md`) contra los 110 + 15 pts de
`proyecto-FitFlow_Proyecto_Mejorado.pdf`. `main` local y `origin/main` están al mismo commit
(`657c713...`) — todo lo revisado ya está pusheado.

## Rúbrica principal (110 pts)

| # | Criterio | Pts | Estado | Verificado en |
|---|---|---|---|---|
| 1 | Los 3 servicios corren con `docker compose up` y tienen DB propia | 20 | ✅ | `docker-compose.yml`: `users-db`/`booking-db`/`notif-db` son 3 Postgres separados, cada uno con rol superusuario + rol de aplicación de mínimo privilegio, sin FKs cruzadas |
| 2 | Los servicios se registran en Consul y se descubren dinámicamente | 20 | ✅ | `shared/consul.py` (`register`/`discover` con `?passing=true` + health check HTTP); `registered()` confirmado en el `lifespan` de `users-svc`, `booking-svc`, `notif-svc`, `barberflow-mcp` y `orchestrator` |
| 3 | MCP Server funciona: Claude puede crear una reserva | 20 | ✅ | `services/mcp-server/main.py`: 5 tools reales (`get_available_slots`, `create_booking`, `cancel_booking`, `send_notification`, `get_notifications`) sobre `MCPServer` real; demostrado en vivo en el video final y en `video_DEMO_mcp.mp4` |
| 4 | Circuit breaker demostrado: notif-svc cae, el sistema sigue | 20 | ✅ | `shared/resilience.py` (timeout + retries con backoff/jitter + `pybreaker`) y outbox en `booking-svc`; demostrado en vivo esta sesión con valores reales (`fail_counter: 3`, `outbox_pending: 3` → `closed`, `0`) |
| 5 | JWT implementado + secretos fuera del código | 10 | ✅ | `shared/auth.py` (HS256, expiración, 401 en firma inválida/expirado/sin header — con self-check de 9 casos); `.env` en `.gitignore`, `.env.example` sin secretos reales, auditoría real con `gitleaks` (0 leaks en 43 commits, todas las ramas) |
| 6 | Agent-to-Agent | 20 | ✅ | `orchestrator` (descubre por Agent Card, arma el plan, delega), `booking-agent` y `notification-agent` (SDK `a2a` real, `AgentCard`/`AgentSkill`, ejecutan vía `shared/mcp_client.call_tool`, nunca hablan directo con los microservicios de negocio) |

**Total: 110/110 verificado en código.**

## Puntos extra — despliegue en la nube (+15)

| Criterio | Pts | Estado |
|---|---|---|
| Guía completa de despliegue | +3 | ✅ `docs/railway-deploy.md` — paso a paso real, tabla de los 12 servicios con root directory/Dockerfile/puerto, explica por qué las DBs necesitan Dockerfile propio en Railway |
| URL pública de cada servicio | +8 | ❌ Pendiente — no ejecutado (bloqueo de red hacia `railway.app` desde este entorno, documentado en la propia guía) |
| Secretos en el servicio del proveedor (no `.env`) | +4 | ❌ Pendiente — depende de lo anterior |

**Total extra: +3 de 15.** Es el único hueco real de todo el proyecto, y ya estaba
identificado en `ENTREGA.md`. Requiere tu cuenta de Railway real; no se puede hacer desde acá.

## Un hallazgo menor (no resta puntos, pero vale la pena saberlo)

`.gitignore` tiene esta línea comentada:

```
# Video demo (muy pesado para git)
#video_DEMO_mcp.mp4
```

Es intencional — el README dice explícitamente "el repositorio incluye
`video_DEMO_mcp.mp4` (~65 MB)" — pero dejá esto en mente: GitHub empieza a advertir sobre
archivos binarios grandes a partir de ~50 MB (el límite duro es 100 MB, así que no bloquea,
pero un `git push` de ese archivo puede tardar más o el hosting puede marcarlo). Si en algún
momento GitHub se queja, la solución es sacar ese archivo del repo y dejarlo solo enlazado
(como ya hiciste con el video final vía Drive).

## Lo único que falta confirmar en vivo

Todo lo de arriba está verificado por código y por lo que ya grabamos en el video. Lo único
que no vimos completar en esta conversación fue el resultado final del paso 8 del guion (la
instrucción A2A al `orchestrator`) después de corregir el problema de acentos. Para cerrar la
auditoría del todo, corré esto una vez más y confirmame la salida:

```powershell
docker compose ps --format "table {{.Name}}\t{{.Status}}"

$instructBody = @{ text = "Reservame un corte para manana y avisame por notificacion" } | ConvertTo-Json
$resp2 = Invoke-WebRequest -Uri http://localhost:9000/instruct -Method Post -Body $instructBody -ContentType "application/json"
$result = $resp2.Content | ConvertFrom-Json
$result | ConvertTo-Json -Depth 5
```

Debería devolver `plan_source: "keywords"`, `plan: ["create_booking", "send_notification"]`
y dos `steps` sin error. Si sale así, los 110/110 quedan verificados en vivo de punta a punta
y lo único pendiente para la entrega es la decisión sobre Railway (+12 pts extra).
