# TTL real de desregistro en Consul

**Tarea 23.** Número medido, no estimado. Reproducible con `scripts/medir_ttl_consul.py`.

## Resumen

| | |
|---|---|
| Lo que dice el PDF | Consul elimina el servicio del registro **a los 30s** |
| Lo que hace Consul 1.17 | Ignora los 30s (mínimo de 1m) y además barre los checks muertos de forma periódica |
| **Reloj de pared medido** | **82.7s y 86.7s** desde que muere `/healthz` hasta que el servicio sale del catálogo |
| **Número a usar en la demo** | **esperar 90s** (techo con margen sobre lo medido) |

El 30s del PDF es falso. La demo que espera 30s y muestra el catálogo verá el servicio
**todavía registrado**, y el checkpoint "derribar notif-svc" no demuestra nada.

## Qué dice el PDF

> *"Si un servicio falla durante 30 segundos, Consul lo elimina del registro automáticamente"*

`shared/consul.py` envía exactamente eso: `DEREGISTER_AFTER = "30s"`.

## Qué hace Consul en realidad

Dos cosas, encadenadas:

1. **Eleva el valor en silencio.** Consul 1.17 impone un mínimo de `1m0s` a
   `DeregisterCriticalServiceAfter`. La petición de registro devuelve **200 OK** — no hay
   error, no hay aviso en la respuesta. El único rastro está en el log del agente.
2. **El barrido es periódico, no un temporizador por servicio.** El agente no desregistra
   en el instante exacto en que se cumple el minuto: pasa una escoba cada cierto tiempo.
   Por eso el valor efectivo queda **por encima** de 1m y **varía entre corridas**.

Resultado: el ciclo completo no dura 30s (PDF) ni 60s (el mínimo de Consul), sino
**más de 80s**.

## Tiempos medidos

Dos muestras, misma corrida, `hashicorp/consul:1.17 agent -dev`, check
`Interval=10s Timeout=2s DeregisterCriticalServiceAfter=30s`, polling cada 1s:

```
========================================================================
               critical    desregistro    TTL efectivo
muestra 1:        9.0s          82.7s           73.6s
muestra 2:        9.0s          86.7s           77.6s
========================================================================
critical      = desde que muere /healthz hasta que el check pasa a critical
desregistro   = desde que muere /healthz hasta que sale del catálogo (reloj de pared)
TTL efectivo  = desde critical hasta el desregistro (lo que Consul aplica de verdad)

log del agente -> 2026-08-20T17:06:49.759Z [WARN]  agent: check has deregister interval below minimum: check=service:barberflow-ttl-probe-host.docker.internal-51712 minimum_interval=1m0s
log del agente -> 2026-08-20T17:08:18.489Z [WARN]  agent: check has deregister interval below minimum: check=service:barberflow-ttl-probe-host.docker.internal-51923 minimum_interval=1m0s
```

Los tres tiempos son distintos y conviene no confundirlos:

- **9.0s hasta `critical`** — es la latencia de detección, la manda `Interval=10s`. Estable
  en ambas muestras.
- **73.6s / 77.6s de TTL efectivo** — es lo que Consul aplica de verdad contando desde que
  el check entra en `critical`. Este es el número que desmiente al PDF: ni 30s ni 60s.
- **82.7s / 86.7s de reloj de pared** — es lo que espera una persona parada frente a la
  demo. Este es el número que hay que planificar.

**Solo hay dos muestras y difieren en 4s.** Ambas caen por encima del mínimo de 1m, lo que
confirma que el barrido es periódico y que el valor **tiene jitter**: trátese como un piso
con variación, no como una constante. Si alguien necesita más precisión, que corra el
script varias veces.

## Por qué `GET /v1/agent/checks` no sirve para leer este valor

El backlog proponía leer el valor efectivo por la API. **No se puede.** El endpoint
devuelve `Interval` y `Timeout`, pero `Definition` viene vacío y
`DeregisterCriticalServiceAfter` no aparece por ningún lado:

```json
{
  "service:barberflow-ttl-probe-host.docker.internal-51712": {
    "CheckID": "service:barberflow-ttl-probe-host.docker.internal-51712",
    "Status": "critical",
    "Output": "Get \"http://host.docker.internal:51712/healthz\": dial tcp 192.168.65.254:51712: connect: connection refused",
    "Type": "http",
    "Interval": "10s",
    "Timeout": "2s",
    "Definition": {},
    "CreateIndex": 0,
    "ModifyIndex": 0
  }
}
```

`GET /v1/agent/service/{id}` tampoco: la respuesta no trae bloque `Check`.

```json
{
  "ID": "barberflow-ttl-probe-host.docker.internal-51712",
  "Service": "barberflow-ttl-probe",
  "Port": 51712,
  "Address": "host.docker.internal",
  "Weights": {"Passing": 1, "Warning": 1},
  "ContentHash": "f5a8a24af1654bda",
  "Datacenter": "dc1"
}
```

Quedan dos formas de saberlo, y ambas están cubiertas arriba: el `[WARN]` del log del
agente (dice el mínimo, `1m0s`, pero no el efectivo) y **cronometrarlo**, que es lo que
hace el script.

## Qué implica para la demo

**El checkpoint "derribar notif-svc" debe planificarse contra ~90s, no contra 30s.**

- **Tarea 26** (caso de lista vacía tras el desregistro): esperar **90s** después de tumbar
  notif-svc antes de hacer el `POST /appointments`. A los 30s el servicio sigue en el
  catálogo y la prueba no estaría probando lo que dice probar — estaría midiendo el
  breaker, no el desregistro.
- **Tarea 24** (outbox): entre los ~9s y los ~85s el servicio está **registrado pero
  `critical`**. Una llamada a `discover()` hecha después de los ~9s ya devuelve
  `ServiceUnavailable`, por el filtro `?passing` que está en `shared/consul.py`. *Ese
  último punto se lee del código y lo cubre el self-check de la tarea 8; **no se cronometró
  en esta corrida**.* El outbox no debe esperar al desregistro para actuar: su disparador
  es el breaker o los reintentos agotados, que ocurre mucho antes.
- **Tarea 40** (`demo.sh` y guion de video): el checkpoint necesita **90s de espera real**.
  Es minuto y medio de silencio en el video: conviene rellenarlos mostrando el estado
  `critical` en la UI de Consul en vez de dejar la pantalla quieta, o hacer la espera
  explícita con una cuenta regresiva en pantalla. No poner `sleep 30`.

## Nota sobre `shared/consul.py`

La constante sigue en `DEREGISTER_AFTER = "30s"`. **Es engañosa pero inofensiva**: Consul la
eleva sola, y bajarla o subirla no cambia el comportamiento observado mientras esté por
debajo del mínimo. Se deja intacta a propósito en esta tarea (alcance: medir y documentar).
Cambiarla a `"1m"` para que el código diga la verdad es un follow-up que alguien debería
levantar; cosmético, no funcional.

## Reproducir

```bash
python scripts/medir_ttl_consul.py
```

Levanta su propio Consul efímero (`barberflow-check-ttl`, puerto 58502), registra un
servicio real con `shared.consul.register`, mata su `/healthz` y cronometra. Toma dos
muestras, imprime la tabla y borra el contenedor pase lo que pase. Sale con 0 si midió,
1 si venció el tope de 180s.
