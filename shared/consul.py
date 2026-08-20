"""Registro y descubrimiento de servicios en Consul contra su HTTP API.

Son cuatro llamadas HTTP: no hace falta un cliente de terceros.
"""

from __future__ import annotations

import logging
import os
import random
from contextlib import asynccontextmanager

import httpx

log = logging.getLogger(__name__)

CHECK_INTERVAL = "10s"
CHECK_TIMEOUT = "2s"
# El PDF pide 30s. Consul impone un mínimo de 1m y eleva este valor en silencio (ver tarea 23).
DEREGISTER_AFTER = "30s"

_TIMEOUT = httpx.Timeout(2.0)


class ServiceUnavailable(Exception):
    """No hay ninguna instancia sana del servicio buscado."""


def _addr() -> str:
    # Se lee en cada llamada: los contenedores la inyectan por entorno.
    return os.getenv("CONSUL_HTTP_ADDR", "http://consul:8500").rstrip("/")


async def register(
    name: str,
    port: int,
    *,
    address: str | None = None,
    health_path: str = "/healthz",
) -> str:
    """Registra el servicio con su health check HTTP y devuelve el service_id."""
    # Dentro de la red de compose el nombre del servicio ya resuelve por DNS.
    address = address or os.getenv("SERVICE_ADDRESS") or name
    service_id = f"{name}-{address}-{port}"
    payload = {
        "ID": service_id,
        "Name": name,
        "Address": address,
        "Port": port,
        "Check": {
            "HTTP": f"http://{address}:{port}{health_path}",
            "Interval": CHECK_INTERVAL,
            "Timeout": CHECK_TIMEOUT,
            "DeregisterCriticalServiceAfter": DEREGISTER_AFTER,
        },
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.put(f"{_addr()}/v1/agent/service/register", json=payload)
        response.raise_for_status()
    log.info("registrado en Consul: %s", service_id)
    return service_id


async def deregister(service_id: str) -> None:
    """Saca el servicio del registro. Un fallo aquí nunca debe tumbar el shutdown."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.put(
                f"{_addr()}/v1/agent/service/deregister/{service_id}"
            )
            response.raise_for_status()
        log.info("desregistrado de Consul: %s", service_id)
    except Exception as exc:
        log.warning("no se pudo desregistrar %s: %s", service_id, exc)


async def discover(name: str) -> str:
    """Base URL ("http://host:puerto") de una instancia sana del servicio.

    Cuando Consul desregistra un servicio caído la respuesta es una lista vacía, no un
    error HTTP: un `instances[0]` ciego daría IndexError -> 500. Aquí es ServiceUnavailable.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{_addr()}/v1/health/service/{name}", params={"passing": "true"}
            )
            response.raise_for_status()
            instances = response.json()
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(f"Consul no respondió por '{name}': {exc}") from exc

    if not instances:
        raise ServiceUnavailable(f"no hay instancias sanas de '{name}'")

    entry = random.choice(instances)  # reparto simple entre las instancias sanas
    service = entry["Service"]
    host = service.get("Address") or entry["Node"]["Address"]
    return f"http://{host}:{service['Port']}"


@asynccontextmanager
async def registered(name: str, port: int, **kwargs):
    """Lifespan de FastAPI: registra al entrar, desregistra al salir.

    Si Consul aún no está listo el servicio arranca igual: los contenedores suben en
    paralelo y el agente puede tardar un par de segundos.
    """
    service_id = None
    try:
        service_id = await register(name, port, **kwargs)
    except Exception as exc:
        log.warning("no se pudo registrar '%s' en Consul: %s", name, exc)
    try:
        yield service_id
    finally:
        if service_id:
            await deregister(service_id)


if __name__ == "__main__":
    # Self-check contra un Consul real y un /healthz real. Ver el PR de la tarea 8.
    import asyncio
    import json
    import socket
    import subprocess
    import threading
    import time

    CONTAINER = "barberflow-check-consul"
    IMAGE = "hashicorp/consul:1.17"
    CONSUL_PORT = 58500
    # Consul corre en Docker: para alcanzar el /healthz del host necesita este nombre.
    HOST_FROM_CONTAINER = "host.docker.internal"

    logging.basicConfig(level=logging.INFO, format="    log> %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    def free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("", 0))
            return sock.getsockname()[1]

    async def apoll(fn, what: str, timeout: float = 45.0):
        """Espera activa a que `fn` devuelva algo truthy. Nada de sleeps fijos."""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                got = await fn()
                if got:
                    return got
            except Exception as exc:
                last = exc
            await asyncio.sleep(0.5)
        raise AssertionError(f"timeout esperando {what} (último error: {last})")

    async def main() -> None:
        consul_url = f"http://localhost:{CONSUL_PORT}"
        ok_name = "barberflow-selfcheck"
        dead_name = "barberflow-selfcheck-dead"
        app_port = free_port()
        dead_port = free_port()  # nadie escucha aquí: el check quedará critical

        os.environ["CONSUL_HTTP_ADDR"] = consul_url
        os.environ["SERVICE_ADDRESS"] = HOST_FROM_CONTAINER

        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        subprocess.run(
            ["docker", "run", "-d", "--rm", "--name", CONTAINER,
             "-p", f"{CONSUL_PORT}:8500", IMAGE,
             "agent", "-dev", "-client=0.0.0.0"],
            check=True, capture_output=True,
        )
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:

                async def leader():
                    return (await client.get(f"{consul_url}/v1/status/leader")).json()

                print(f"[1] Consul efímero en {consul_url}, líder = {await apoll(leader, 'el líder')}")

                # /healthz real, para que el check pase a passing de verdad.
                import uvicorn
                from fastapi import FastAPI

                health_app = FastAPI()
                health_app.get("/healthz")(lambda: {"status": "ok"})
                server = uvicorn.Server(
                    uvicorn.Config(health_app, host="0.0.0.0", port=app_port, log_level="warning")
                )
                threading.Thread(target=server.run, daemon=True).start()

                async def local_health():
                    r = await client.get(f"http://127.0.0.1:{app_port}/healthz")
                    return r.status_code == 200

                await apoll(local_health, "la app de prueba", timeout=15)
                print(f"[2] app de prueba sirviendo /healthz en :{app_port}")

                service_id = await register(ok_name, app_port)
                dead_id = await register(dead_name, dead_port)
                print(f"[3] registrados '{service_id}' y '{dead_id}'")

                async def found():
                    try:
                        return await discover(ok_name)
                    except ServiceUnavailable:
                        return None

                url = await apoll(found, f"que el check de '{ok_name}' pase a passing")
                assert url == f"http://{HOST_FROM_CONTAINER}:{app_port}", url
                print(f"[4] discover('{ok_name}') -> {url}")

                # Registrado pero critical: prueba que el filtro ?passing está de verdad puesto.
                async def check_failed():
                    checks = (await client.get(f"{consul_url}/v1/agent/checks")).json()
                    chk = checks.get(f"service:{dead_id}", {})
                    return chk if chk.get("Status") == "critical" and chk.get("Output") else None

                dead_check = await apoll(check_failed, f"que el check de '{dead_name}' falle")
                try:
                    await discover(dead_name)
                    raise AssertionError("discover devolvió una instancia critical")
                except ServiceUnavailable as exc:
                    print(f"[5] '{dead_name}' registrado pero critical -> ServiceUnavailable: {exc}")
                    print(f"    check output: {dead_check['Output'].strip()[:90]}")

                try:
                    await discover("servicio-inexistente")
                    raise AssertionError("discover('servicio-inexistente') no lanzó ServiceUnavailable")
                except ServiceUnavailable as exc:
                    print(f"[6] discover('servicio-inexistente') -> ServiceUnavailable: {exc}")

                # TTL real de desregistro (dato que necesita la tarea 23). Se lee con el
                # contenedor todavía vivo: el log del agente es donde Consul lo confirma.
                agent_check = (await client.get(f"{consul_url}/v1/agent/checks")).json()[f"service:{service_id}"]
                service_def = (await client.get(f"{consul_url}/v1/agent/service/{service_id}")).json()
                logs = subprocess.run(["docker", "logs", CONTAINER], capture_output=True, text=True)
                warnings = [
                    line.strip()
                    for line in (logs.stdout + logs.stderr).splitlines()
                    if "deregister interval" in line
                ]
                print("[7] deregister_critical_service_after: enviado 30s por register()")
                print(f"    GET /v1/agent/checks -> Interval={agent_check['Interval']} "
                      f"Timeout={agent_check['Timeout']} Definition={agent_check['Definition']}")
                print(f"    GET /v1/agent/service/{{id}} -> {json.dumps(service_def)}")
                for line in warnings:
                    print(f"    log del agente -> {line}")

                await deregister(service_id)

                async def gone():
                    try:
                        await discover(ok_name)
                        return None
                    except ServiceUnavailable:
                        return True

                await apoll(gone, "que Consul olvide el servicio", timeout=10)
                print(f"[8] tras deregister, discover('{ok_name}') -> ServiceUnavailable")

                # Consul caído no debe impedir que el servicio arranque.
                os.environ["CONSUL_HTTP_ADDR"] = "http://localhost:1"
                async with registered("barberflow-sin-consul", 1234) as sid:
                    assert sid is None, sid
                os.environ["CONSUL_HTTP_ADDR"] = consul_url
                print("[9] registered() con Consul inalcanzable: el lifespan entra y sale igual")

            print("\nOK — self-check completo, sin excepciones")
        finally:
            subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
            print(f"({CONTAINER} eliminado)")

    asyncio.run(main())
