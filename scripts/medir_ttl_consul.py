#!/usr/bin/env python3
"""Cronometra el TTL real que Consul aplica a `deregister_critical_service_after`.

El PDF del curso afirma que un servicio caído sale del registro a los 30s. Consul 1.17
impone un mínimo de 1m y eleva el valor en silencio, y además barre los checks muertos
de forma periódica, así que el número que ve la demo no es ninguno de los dos. Este
script lo mide: levanta un Consul efímero, registra un servicio real con
`shared.consul.register`, mata su `/healthz` y cronometra con polling de 1s.

Uso:  python scripts/medir_ttl_consul.py

Imprime tres tiempos y sale con 0 si midió; con 1 si venció el tope de espera.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.consul import CHECK_INTERVAL, CHECK_TIMEOUT, DEREGISTER_AFTER, register  # noqa: E402

CONTAINER = "barberflow-check-ttl"
IMAGE = "hashicorp/consul:1.17"
CONSUL_PORT = 58502
# Consul corre en Docker: para alcanzar el /healthz del host necesita este nombre.
HOST_FROM_CONTAINER = "host.docker.internal"
SERVICE_NAME = "barberflow-ttl-probe"
POLL_SECONDS = 1.0
MAX_WAIT_SECONDS = 180.0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


async def poll_until(condition, what: str, timeout: float = MAX_WAIT_SECONDS) -> float:
    """Espera a que `condition()` sea verdadera y devuelve el instante monotónico.

    Imprime un latido por intento: la espera larga es el 90% del script y sin señal de
    avance parece colgado (y algún supervisor lo mata por inactividad).
    """
    inicio = deadline = time.monotonic()
    deadline += timeout
    intento = 0
    while time.monotonic() < deadline:
        intento += 1
        try:
            if await condition():
                return time.monotonic()
        except Exception:
            pass
        print(f"    [{time.monotonic() - inicio:5.0f}s] esperando {what}... (intento {intento})",
              flush=True)
        await asyncio.sleep(POLL_SECONDS)
    raise TimeoutError(f"se agotaron {timeout:.0f}s esperando {what}")


async def run_measurement(client: httpx.AsyncClient, consul_url: str) -> dict[str, float]:
    """Un ciclo completo: registrar, matar el /healthz y cronometrar."""
    import uvicorn
    from fastapi import FastAPI

    app_port = free_port()
    health_app = FastAPI()
    health_app.get("/healthz")(lambda: {"status": "ok"})
    server = uvicorn.Server(
        uvicorn.Config(health_app, host="0.0.0.0", port=app_port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()

    async def health_responde() -> bool:
        return (await client.get(f"http://127.0.0.1:{app_port}/healthz")).status_code == 200

    await poll_until(health_responde, "que la app de prueba sirva /healthz", timeout=30)
    print(f"  app de prueba sirviendo /healthz en :{app_port}")

    # El código real del proyecto, no un payload a mano.
    service_id = await register(SERVICE_NAME, app_port)
    print(f"  registrado '{service_id}' (deregister_critical_service_after={DEREGISTER_AFTER})")

    async def check_status() -> str:
        checks = (await client.get(f"{consul_url}/v1/agent/checks")).json()
        return checks.get(f"service:{service_id}", {}).get("Status", "")

    await poll_until(lambda: _is(check_status, "passing"), "que el check pase a passing", timeout=60)
    print("  check en passing")

    # t0 = el instante en que el endpoint deja de responder de verdad, no en el que
    # pedimos el apagado: uvicorn tarda un tick en cerrar el socket.
    server.should_exit = True

    async def health_muerto() -> bool:
        try:
            await client.get(f"http://127.0.0.1:{app_port}/healthz")
            return False
        except httpx.HTTPError:
            return True

    t0 = await poll_until(health_muerto, "que el /healthz deje de responder", timeout=30)
    print("  /healthz caído — arranca el cronómetro")

    t_critical = await poll_until(lambda: _is(check_status, "critical"), "que el check pase a critical")
    print(f"  check en critical a los {t_critical - t0:.1f}s")

    async def fuera_del_catalogo() -> bool:
        sanos = (await client.get(f"{consul_url}/v1/health/service/{SERVICE_NAME}",
                                  params={"passing": "true"})).json()
        todos = (await client.get(f"{consul_url}/v1/health/service/{SERVICE_NAME}")).json()
        en_agente = service_id in (await client.get(f"{consul_url}/v1/agent/services")).json()
        return not sanos and not todos and not en_agente

    t_gone = await poll_until(fuera_del_catalogo, "que el servicio salga del catálogo")
    print(f"  desregistrado a los {t_gone - t0:.1f}s")

    return {
        "critical": t_critical - t0,
        "desregistro": t_gone - t0,
        "ttl_efectivo": t_gone - t_critical,
    }


async def _is(getter, expected: str) -> bool:
    return await getter() == expected


async def main() -> int:
    consul_url = f"http://localhost:{CONSUL_PORT}"
    os.environ["CONSUL_HTTP_ADDR"] = consul_url
    os.environ["SERVICE_ADDRESS"] = HOST_FROM_CONTAINER

    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", CONTAINER, "-p", f"{CONSUL_PORT}:8500",
         IMAGE, "agent", "-dev", "-client=0.0.0.0"],
        check=True, capture_output=True,
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:

            async def hay_lider() -> bool:
                return bool((await client.get(f"{consul_url}/v1/status/leader")).json())

            await poll_until(hay_lider, "el líder de Consul", timeout=60)
            print(f"Consul efímero en {consul_url}")
            print(f"Check: Interval={CHECK_INTERVAL} Timeout={CHECK_TIMEOUT} "
                  f"DeregisterCriticalServiceAfter={DEREGISTER_AFTER}\n")

            # Dos muestras: el barrido de checks muertos es periódico, así que una sola
            # medición no distingue el TTL del retraso del barrido.
            muestras = []
            for n in (1, 2):
                print(f"--- muestra {n} ---")
                muestras.append(await run_measurement(client, consul_url))
                print()

            logs = subprocess.run(["docker", "logs", CONTAINER], capture_output=True, text=True)
            warnings = sorted({
                line.strip() for line in (logs.stdout + logs.stderr).splitlines()
                if "deregister interval" in line
            })

        print("=" * 72)
        print(f"{'':>10} {'critical':>12} {'desregistro':>14} {'TTL efectivo':>15}")
        for n, m in enumerate(muestras, 1):
            print(f"muestra {n}: {m['critical']:>10.1f}s {m['desregistro']:>13.1f}s "
                  f"{m['ttl_efectivo']:>14.1f}s")
        print("=" * 72)
        print("critical      = desde que muere /healthz hasta que el check pasa a critical")
        print("desregistro   = desde que muere /healthz hasta que sale del catálogo (reloj de pared)")
        print("TTL efectivo  = desde critical hasta el desregistro (lo que Consul aplica de verdad)")
        print()
        if warnings:
            for line in warnings:
                print(f"log del agente -> {line}")
        else:
            print("log del agente -> no se observó ningún WARN de 'deregister interval'")
        return 0
    except TimeoutError as exc:
        print(f"NO MEDIDO: {exc}", file=sys.stderr)
        return 1
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        print(f"({CONTAINER} eliminado)")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
