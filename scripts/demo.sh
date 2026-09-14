#!/usr/bin/env bash
# Recorre los 7 checkpoints del enunciado contra el sistema ya levantado (tarea 40).
#
#   docker compose up --build -d
#   ./scripts/demo.sh
#
# No pide nada interactivo y deja el sistema como lo encontró: levanta notif-svc
# si lo derribó y cancela las citas que creó. El único rastro que queda es el
# usuario de prueba (users-svc no expone borrado), con email único por corrida.
#
# Los checkpoints 6 y 7 del enunciado se hacen desde Claude Desktop; aquí se
# ejercita el mismo camino por el protocolo MCP (initialize -> tools/list ->
# tools/call sobre http://localhost:8000/mcp), que es exactamente lo que Claude
# envía por debajo. La grabación con Claude está en video_DEMO_mcp.mp4.
set -euo pipefail

cd "$(dirname "$0")/.."

# ── utilidades ───────────────────────────────────────────────────────────────

RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
CHECKPOINT=0

step()  { CHECKPOINT=$1; shift; printf '\n%s[%s/7] %s%s\n' "$BOLD" "$CHECKPOINT" "$*" "$OFF"; }
ok()    { printf '  %s✔%s %s\n' "$GREEN" "$OFF" "$*"; }
info()  { printf '  %s%s%s\n' "$DIM" "$*" "$OFF"; }
fail()  { printf '\n%s✘ checkpoint %s falló: %s%s\n' "$RED" "$CHECKPOINT" "$*" "$OFF" >&2; exit 1; }

need() { command -v "$1" >/dev/null || { echo "hace falta '$1' en el PATH" >&2; exit 1; }; }
need curl; need jq; need docker

# curl sin proxy (las VPN corporativas interceptan localhost) y sin body en stderr.
req() { curl -sS --noproxy '*' "$@"; }

# Espera activa: poll <segundos> <qué> <comando...>
poll() {
	local deadline=$((SECONDS + $1)) what="$2"; shift 2
	until "$@" >/dev/null 2>&1; do
		(( SECONDS < deadline )) || fail "timeout esperando $what"
		sleep 1
	done
}

# Puerto publicado en el host: lo que diga el .env, o el default del compose.
port() {
	local value=""
	[[ -f .env ]] && value=$(grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d "\"' " || true)
	echo "${value:-$2}"
}

USERS=http://localhost:$(port USERS_PORT 8003)
BOOKING=http://localhost:$(port BOOKING_PORT 8001)
NOTIF=http://localhost:$(port NOTIF_PORT 8002)
MCP=http://localhost:$(port MCP_PORT 8000)/mcp
CONSUL=http://localhost:$(port CONSUL_PORT 8500)

TMP=$(mktemp -d)
CREATED=""          # ids de las citas creadas por esta corrida (separados por espacios)
NOTIF_DOWN=false

cleanup() {
	local code=$?
	if [[ $NOTIF_DOWN == true ]]; then
		printf '\n%slimpieza: levantando notif-svc%s\n' "$DIM" "$OFF"
		docker compose start notif-svc >/dev/null 2>&1 || true
	fi
	if [[ -n $CREATED && -n "${TOKEN:-}" ]]; then
		printf '%slimpieza: cancelando las citas de la demo (%s)%s\n' "$DIM" "$CREATED" "$OFF"
		for id in $CREATED; do
			req -X DELETE "$BOOKING/appointments/$id" -H "Authorization: Bearer $TOKEN" >/dev/null 2>&1 || true
		done
	fi
	rm -rf "$TMP"
	exit $code
}
trap cleanup EXIT

# ── 1. Consul con los servicios en verde ─────────────────────────────────────

step 1 'docker compose up -> los servicios registrados y en verde en Consul'

for svc in users-svc booking-svc notif-svc barberflow-mcp; do
	count=$(req "$CONSUL/v1/health/service/$svc?passing=true" | jq 'length') || fail "Consul no respondió"
	[[ $count -ge 1 ]] || fail "'$svc' no está en verde en Consul (¿ya levantaste el compose?)"
	ok "$svc: $count instancia(s) en verde"
done
info "UI de Consul: $CONSUL"

for url in "$USERS" "$BOOKING" "$NOTIF"; do
	[[ $(req "$url/healthz" | jq -r .status) == ok ]] || fail "$url/healthz no devolvió ok"
done
ok '/healthz responde {"status":"ok"} en los tres servicios'

# ── 2. Registro, login y JWT ─────────────────────────────────────────────────

step 2 'Registrar un usuario -> login -> JWT'

EMAIL="demo-$(date +%s)@barberflow.local"
req -X POST "$USERS/register" -H 'Content-Type: application/json' \
	-d "{\"email\":\"$EMAIL\",\"password\":\"demo1234\",\"full_name\":\"Demo Script\",\"phone\":\"+502 5555-9999\"}" \
	-o "$TMP/register.json" -w '%{http_code}' | grep -q 201 || fail "POST /register no devolvió 201: $(cat "$TMP/register.json")"
USER_ID=$(jq -r .id "$TMP/register.json")
ok "usuario $EMAIL creado con id $USER_ID"

TOKEN=$(req -X POST "$USERS/login" -H 'Content-Type: application/json' \
	-d "{\"email\":\"$EMAIL\",\"password\":\"demo1234\"}" | jq -r .access_token)
[[ -n $TOKEN && $TOKEN != null ]] || fail "/login no devolvió access_token"
ok "JWT recibido (${#TOKEN} caracteres)"
info "payload: $(cut -d. -f2 <<<"$TOKEN" | tr '_-' '/+' \
	| jq -Rr '@base64d | fromjson | {sub, email, role} | tojson' 2>/dev/null || echo '(no decodificado)')"

[[ $(req -o /dev/null -w '%{http_code}' "$BOOKING/appointments" -H 'Authorization: Bearer noesuntoken') == 401 ]] \
	|| fail "un token inválido debería dar 401"
ok 'un token inválido responde 401'

# ── 3. Reserva con JWT y correlation-id rastreable ───────────────────────────

step 3 'Crear una reserva con el JWT -> log JSON con el mismo correlation_id'

slot() { req "$BOOKING/slots" | jq -r ".[$1].id"; }
SLOT=$(slot 0); [[ -n $SLOT && $SLOT != null ]] || fail "no hay horarios libres en GET /slots"

CID="demo-$(date +%s)"
req -X POST "$BOOKING/appointments" -H 'Content-Type: application/json' \
	-H "Authorization: Bearer $TOKEN" -H "x-correlation-id: $CID" \
	-d "{\"slot_id\":$SLOT}" -o "$TMP/appt.json" -w '%{http_code}' | grep -q 201 \
	|| fail "POST /appointments no devolvió 201: $(cat "$TMP/appt.json")"
APPT=$(jq -r .id "$TMP/appt.json"); CREATED="$CREATED $APPT"
ok "cita $APPT creada en el horario $SLOT, notificación: $(jq -r .notification "$TMP/appt.json")"

for svc in booking-svc notif-svc; do
	docker compose logs "$svc" --since 2m 2>/dev/null | grep -q "$CID" \
		|| fail "el correlation_id $CID no aparece en los logs de $svc"
	ok "$svc registró el correlation_id $CID"
done
info "rastrearlo completo: docker compose logs | grep $CID | jq ."
if [[ $(docker compose logs booking-svc --since 2m 2>/dev/null | grep "$CID" | grep -c '"user_id"') -ge 1 ]]; then
	ok "los logs llevan el user_id junto al correlation_id"
fi

# ── 4. notif-svc caído: el sistema sigue y el breaker abre ───────────────────

step 4 'Derribar notif-svc -> 3 reservas responden 201 -> circuit breaker abierto'

docker compose stop notif-svc >/dev/null 2>&1 || fail 'no se pudo parar notif-svc'
NOTIF_DOWN=true
ok 'notif-svc detenido'

for i in 1 2 3; do
	s=$(slot "$i"); [[ -n $s && $s != null ]] || fail "no hay suficientes horarios libres"
	req -X POST "$BOOKING/appointments" -H 'Content-Type: application/json' \
		-H "Authorization: Bearer $TOKEN" -d "{\"slot_id\":$s}" \
		-o "$TMP/down-$i.json" -w '%{http_code}' | grep -q 201 \
		|| fail "con notif-svc caído la reserva $i no devolvió 201: $(cat "$TMP/down-$i.json")"
	CREATED="$CREATED $(jq -r .id "$TMP/down-$i.json")"
	ok "reserva $i: 201 con notificación '$(jq -r .notification "$TMP/down-$i.json")' (sin 500)"
done

CIRCUIT=$(req "$BOOKING/admin/circuit")
[[ $(jq -r .state <<<"$CIRCUIT") == open ]] || fail "el breaker debería estar abierto: $CIRCUIT"
ok "breaker: $(jq -c '{state, fail_counter, outbox_pending}' <<<"$CIRCUIT")"
info "el panel en vivo de esto es http://localhost:$(port WEB_PORT 3080)/status"

# ── 5. notif-svc vuelve: el breaker cierra y el outbox se vacía ──────────────

step 5 'Levantar notif-svc -> el breaker cierra y el outbox se vacía solo'

docker compose start notif-svc >/dev/null 2>&1 || fail 'no se pudo levantar notif-svc'
NOTIF_DOWN=false
poll 60 'que notif-svc vuelva a estar en verde en Consul' \
	bash -c "[[ \$(curl -sS --noproxy '*' '$CONSUL/v1/health/service/notif-svc?passing=true' | jq 'length') -ge 1 ]]"
ok 'notif-svc de vuelta en verde en Consul'

info 'esperando el reset del breaker (30s) y el barrido del outbox (cada 15s)…'
poll 120 'que el breaker cierre y el outbox quede vacío' \
	bash -c "[[ \$(curl -sS --noproxy '*' '$BOOKING/admin/circuit' | jq -r '.state + \":\" + (.outbox_pending|tostring)') == closed:0 ]]"
ok "breaker: $(req "$BOOKING/admin/circuit" | jq -c '{state, fail_counter, outbox_pending}')"

pend=$(req "$NOTIF/notifications?user_id=$USER_ID" | jq 'length')
[[ $pend -ge 3 ]] || fail "notif-svc debería tener las notificaciones del outbox: solo $pend"
ok "notif-svc entregó $pend notificaciones del usuario $USER_ID (las del outbox incluidas)"

# ── 6 y 7. MCP: listar horarios y reservar ───────────────────────────────────

# initialize + notifications/initialized; deja el session id en $SESSION.
mcp_open() {
	SESSION=$(req -D "$TMP/mcp.h" -o /dev/null -X POST "$MCP" \
		-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
		-d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo.sh","version":"1.0"}}}' \
		&& tr -d '\r' < "$TMP/mcp.h" | awk 'tolower($1)=="mcp-session-id:"{print $2}')
	[[ -n ${SESSION:-} ]] || fail 'el MCP Server no devolvió mcp-session-id'
	mcp_raw '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null
}

mcp_raw() {
	req -X POST "$MCP" -H 'Content-Type: application/json' \
		-H 'Accept: application/json, text/event-stream' -H "mcp-session-id: $SESSION" -d "$1"
}

# tools/call que devuelve el resultado ya des-empaquetado, o falla con el error del server.
mcp_call() {
	local out; out=$(mcp_raw "{\"jsonrpc\":\"2.0\",\"id\":9,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}" \
		| sed -n 's/^data: //p' | tail -1)
	[[ $(jq -r '.result.isError' <<<"$out") != true ]] || fail "tool $1: $(jq -r '.result.content[0].text' <<<"$out")"
	jq -r '.result.structuredContent.result // (.result.content[0].text | fromjson)' <<<"$out"
}

step 6 'Claude lista los horarios disponibles vía MCP (get_available_slots)'

mcp_open
ok "sesión MCP abierta contra $MCP"
TOOLS=$(mcp_raw '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | sed -n 's/^data: //p' | tail -1 | jq -r '[.result.tools[].name] | join(", ")')
ok "tools publicadas: $TOOLS"
SLOTS=$(mcp_call get_available_slots '{}')
[[ $(jq 'length' <<<"$SLOTS") -ge 1 ]] || fail 'get_available_slots no devolvió horarios'
ok "get_available_slots -> $(jq 'length' <<<"$SLOTS") horarios libres"
info "primero: $(jq -c '.[0] | {id, starts_at, service_name, barber_name}' <<<"$SLOTS")"

step 7 'Claude crea la reserva vía MCP (create_booking) y se ve en la base'

MCP_SLOT=$(jq -r '.[0].id' <<<"$SLOTS")
BOOKED=$(mcp_call create_booking "{\"slot_id\":$MCP_SLOT}")
MCP_APPT=$(jq -r .id <<<"$BOOKED")
ok "create_booking -> cita $MCP_APPT, notificación '$(jq -r .notification <<<"$BOOKED")'"

# La cita del MCP es del usuario demo del .env, no del usuario de este script:
# se cancela por la misma tool para no dejar basura.
row=$(docker compose exec -T booking-db psql -U "$(port BOOKING_DB_SUPERUSER booking_admin)" \
	-d "$(port BOOKING_DB_NAME booking_db)" -tAc \
	"SELECT status FROM appointments WHERE id = $MCP_APPT" 2>/dev/null | tr -d ' ')
[[ $row == confirmed ]] || fail "la cita $MCP_APPT no quedó confirmada en booking-db (status='$row')"
ok "booking-db confirma la cita $MCP_APPT (SELECT status -> $row)"

mcp_call cancel_booking "{\"appointment_id\":$MCP_APPT}" >/dev/null
ok "cancel_booking -> cita $MCP_APPT cancelada y horario liberado"

printf '\n%s✔ los 7 checkpoints pasaron%s\n' "$GREEN$BOLD" "$OFF"
