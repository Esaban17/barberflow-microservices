"""Llamadas HTTP entre servicios con timeout, reintentos y circuit breaker.

Lo que pide el PDF: no esperar más de 2s a un destino, reintentar hasta 3 veces con
backoff exponencial + jitter y, tras 3 fallos seguidos, abrir el circuito 30s.
"""

from __future__ import annotations

import httpx
import pybreaker
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from shared import consul
from shared.logging import correlation_headers, get_logger

log = get_logger()

TIMEOUT = 2.0  # segundos: pasado esto se asume que el destino falló
MAX_ATTEMPTS = 3
FAIL_MAX = 3
RESET_TIMEOUT = 30.0

_breakers: dict[str, pybreaker.CircuitBreaker] = {}


class ServiceCallFailed(Exception):
    """Único error que sale de `call_service`, venga de donde venga el fallo."""


# Los dos modos de caída de un destino tienen que converger aquí: mientras Consul
# todavía lo lista da connection refused o timeout (httpx.HTTPError), y en cuanto lo
# desregistra la lista viene vacía (ServiceUnavailable). Si el segundo se escapara sin
# contarse, el breaker aparecería cerrado justo con el servicio caído y el llamador
# tendría que manejar dos errores distintos en vez de uno.
_RETRYABLE = (httpx.HTTPError, consul.ServiceUnavailable)


def get_breaker(service_name: str) -> pybreaker.CircuitBreaker:
    """Breaker propio de cada servicio destino: 3 fallos seguidos -> abierto 30s."""
    if service_name not in _breakers:
        _breakers[service_name] = pybreaker.CircuitBreaker(
            fail_max=FAIL_MAX,
            reset_timeout=RESET_TIMEOUT,
            name=service_name,
            # Un 4xx no es culpa del destino y no debe abrir nada. pybreaker trata lo
            # excluido como éxito y resetea el contador, que es justo lo correcto: si
            # contestó 400, está vivo.
            exclude=[ServiceCallFailed],
        )
    return _breakers[service_name]


@retry(
    stop=stop_after_attempt(MAX_ATTEMPTS),
    # 0.5 / 1 / 2s + jitter. Con 3 intentos solo se llegan a usar las dos primeras esperas.
    wait=wait_exponential_jitter(initial=0.5, max=2.0, exp_base=2, jitter=0.1),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
async def _attempt(
    service_name: str,
    method: str,
    path: str,
    json,
    params,
    headers,
) -> httpx.Response:
    """Un intento suelto: descubrir instancia, llamar con timeout y clasificar."""
    base_url = await consul.discover(service_name)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.request(
            method,
            f"{base_url}{path}",
            json=json,
            params=params,
            # El correlation-id del request en curso viaja al destino; un header
            # explícito del llamador manda sobre él.
            headers={**correlation_headers(), **(headers or {})},
        )
    if response.is_server_error:
        response.raise_for_status()  # 5xx: transitorio, se reintenta
    if response.is_client_error:
        # Reintentar un 4xx es inútil: la petición está mal, no el destino.
        raise ServiceCallFailed(f"{service_name} {method} {path} -> {response.status_code}")
    return response


async def call_service(
    service_name: str,
    method: str,
    path: str,
    *,
    json=None,
    params=None,
    headers=None,
) -> httpx.Response:
    """Llama a otro servicio de BarberFlow. Cualquier fallo sale como ServiceCallFailed."""
    breaker = get_breaker(service_name)
    try:
        # El breaker envuelve al conjunto de reintentos: sus "3 fallos" son 3 ciclos
        # completos agotados, no 3 intentos sueltos. Al revés un único bache abriría el
        # circuito y dejaría al destino fuera 30s sin motivo.
        # pybreaker 1.4.1 esconde call_async detrás de tornado, que no está instalado
        # (NameError: name 'gen' is not defined); calling() es su API síncrona y envuelve
        # el await sin problema porque entra y sale alrededor de él.
        # ponytail: calling() captura BaseException, así que una cancelación también
        # cuenta como fallo del destino; aceptable aquí.
        with breaker.calling():
            return await _attempt(service_name, method, path, json, params, headers)
    except ServiceCallFailed:
        raise  # 4xx ya clasificado: el breaker lo dejó pasar sin contarlo
    except Exception as exc:
        # Con el tipo delante: un ReadTimeout tiene str() vacío y sin él la línea de log
        # y el mensaje del error quedan mudos justo en el caso más común.
        detail = f"{type(exc).__name__}: {exc}"
        log.warning(
            "service_call_failed",
            target=service_name,
            path=path,
            circuit=breaker.current_state,
            error=detail,
        )
        raise ServiceCallFailed(
            f"llamada a '{service_name}' {method} {path} fallida: {detail}"
        ) from exc


def circuit_state(service_name: str) -> dict:
    """Estado del breaker, tal como lo publica GET /admin/circuit (tarea 25)."""
    breaker = get_breaker(service_name)
    return {
        # pybreaker escribe "half-open"; la API expone "half_open".
        "state": breaker.current_state.replace("-", "_"),
        "fail_counter": breaker.fail_counter,
    }


if __name__ == "__main__":
    # Self-check contra un Consul real y un destino FastAPI real. Ver el PR de la tarea 9.
    import asyncio
    import os
    import socket
    import subprocess
    import threading
    import time
    from collections import Counter

    import structlog
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    from shared.logging import configure_logging

    CONTAINER = "barberflow-check-resilience"
    IMAGE = "hashicorp/consul:1.17"
    CONSUL_PORT = 58501
    TARGET = "barberflow-check-target"
    DEAD = "barberflow-check-dead"

    configure_logging("resilience-check")

    hits: Counter = Counter()  # peticiones que llegan de verdad al destino
    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}  # no cuenta: solo sirve para esperar a uvicorn

    @app.get("/ok")
    async def ok(request: Request) -> dict:
        hits["ok"] += 1
        # Devuelve lo recibido para poder comprobar la propagación de verdad.
        return {"seen": request.headers.get("x-correlation-id"), "a": request.query_params.get("a")}

    @app.get("/slow")
    async def slow() -> dict:
        hits["slow"] += 1
        await asyncio.sleep(5)
        return {}

    @app.get("/boom")
    async def boom() -> JSONResponse:
        hits["boom"] += 1
        return JSONResponse({"error": "kaboom"}, status_code=500)

    @app.get("/bad")
    async def bad() -> JSONResponse:
        hits["bad"] += 1
        return JSONResponse({"error": "petición inválida"}, status_code=400)

    def free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("", 0))
            return sock.getsockname()[1]

    async def apoll(fn, what: str, timeout: float = 30.0):
        """Espera activa a que `fn` devuelva algo truthy."""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                got = await fn()
                if got:
                    return got
            except Exception as exc:
                last = exc
            await asyncio.sleep(0.3)
        raise AssertionError(f"timeout esperando {what} (último error: {last})")

    async def failing(name: str, path: str) -> tuple[ServiceCallFailed, float]:
        """Corre un ciclo que debe fallar. Si escapa otra excepción, revienta el check."""
        started = time.monotonic()
        try:
            await call_service(name, "GET", path)
        except ServiceCallFailed as exc:
            return exc, time.monotonic() - started
        raise AssertionError(f"{name}{path} no falló")

    async def main() -> None:
        consul_url = f"http://localhost:{CONSUL_PORT}"
        os.environ["CONSUL_HTTP_ADDR"] = consul_url
        port, dead_port = free_port(), free_port()  # en dead_port no escucha nadie

        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        subprocess.run(
            ["docker", "run", "-d", "--rm", "--name", CONTAINER,
             "-p", f"{CONSUL_PORT}:8500", IMAGE,
             "agent", "-dev", "-client=0.0.0.0"],
            check=True, capture_output=True,
        )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:

                async def register(name: str, service_port: int) -> None:
                    # Sin health check: el check tendría que alcanzar al host desde el
                    # contenedor y aquí solo importa que discover() devuelva 127.0.0.1.
                    # Los checks ya los cubre el self-check de la tarea 8.
                    response = await client.put(
                        f"{consul_url}/v1/agent/service/register",
                        json={"ID": f"{name}-1", "Name": name,
                              "Address": "127.0.0.1", "Port": service_port},
                    )
                    response.raise_for_status()

                async def listed(name: str, service_port: int):
                    return await consul.discover(name) == f"http://127.0.0.1:{service_port}"

                async def leader():
                    return (await client.get(f"{consul_url}/v1/status/leader")).json()

                print(f"[1] Consul efímero en {consul_url}, líder = {await apoll(leader, 'el líder')}")

                server = uvicorn.Server(uvicorn.Config(
                    app, host="127.0.0.1", port=port, log_level="warning"))
                threading.Thread(target=server.run, daemon=True).start()

                async def serving():
                    return (await client.get(f"http://127.0.0.1:{port}/healthz")).status_code == 200

                await apoll(serving, "el destino de prueba", timeout=15)
                await register(TARGET, port)
                await apoll(lambda: listed(TARGET, port), f"que Consul liste '{TARGET}'")
                print(f"[2] destino FastAPI en :{port} registrado como '{TARGET}'")

                # --- camino feliz: 200 y correlation-id propagado -------------------
                structlog.contextvars.bind_contextvars(correlation_id="cid-check-1")
                response = await call_service(TARGET, "GET", "/ok", params={"a": "1"})
                structlog.contextvars.clear_contextvars()
                assert response.status_code == 200, response
                assert response.json() == {"seen": "cid-check-1", "a": "1"}, response.json()
                assert circuit_state(TARGET) == {"state": "closed", "fail_counter": 0}, circuit_state(TARGET)
                print(f"[3] camino feliz: 200 y el destino recibió {response.json()}")

                # --- timeout de 2s por intento --------------------------------------
                exc, elapsed = await failing(TARGET, "/slow")
                assert hits["slow"] == 3, hits
                # 3 intentos cortados a 2s + las dos esperas del backoff (~1.6s).
                assert 6.0 < elapsed < 10.0, elapsed
                assert circuit_state(TARGET)["fail_counter"] == 1, circuit_state(TARGET)
                print(f"[4] /slow (tarda 5s): 3 intentos cortados a ~2s, {elapsed:.1f}s en total")
                print(f"    -> {exc}")

                # --- reintentos y backoff con 5xx -----------------------------------
                exc, elapsed = await failing(TARGET, "/boom")
                assert hits["boom"] == 3, hits
                # Dos esperas: 0.5s y 1s, más jitter. La tercera (2s) está configurada
                # pero stop_after_attempt(3) corta antes de usarla.
                assert 1.4 < elapsed < 3.0, elapsed
                assert circuit_state(TARGET)["fail_counter"] == 2, circuit_state(TARGET)
                print(f"[5] /boom (500): exactamente {hits['boom']} peticiones en {elapsed:.2f}s")

                # --- modo B: Consul ya lo desregistró, la lista viene vacía ----------
                await client.put(f"{consul_url}/v1/agent/service/deregister/{TARGET}-1")

                async def gone():
                    try:
                        await consul.discover(TARGET)
                        return False
                    except consul.ServiceUnavailable:
                        return True

                await apoll(gone, f"que Consul olvide '{TARGET}'")
                before = dict(hits)
                # failing() solo atrapa ServiceCallFailed: si escapara ServiceUnavailable
                # o un IndexError, el self-check moriría aquí.
                exc, elapsed = await failing(TARGET, "/ok")
                assert dict(hits) == before, hits
                assert circuit_state(TARGET) == {"state": "open", "fail_counter": 3}, circuit_state(TARGET)
                print(f"[6] lista vacía -> ServiceCallFailed y el breaker lo cuenta: abre a los 3")
                print(f"    -> {exc}")

                # --- breaker abierto: ni una petición sale ---------------------------
                await register(TARGET, port)
                await apoll(lambda: listed(TARGET, port), f"que Consul vuelva a listar '{TARGET}'")
                before = dict(hits)
                exc, elapsed = await failing(TARGET, "/ok")
                assert dict(hits) == before, hits  # el destino está sano y aun así no se toca
                assert elapsed < 0.2, elapsed  # ni un intento: corta el breaker, no el retry
                assert circuit_state(TARGET)["state"] == "open", circuit_state(TARGET)
                print(f"[7] breaker abierto: {circuit_state(TARGET)}, la llamada corta en "
                      f"{elapsed * 1000:.0f}ms sin llegar al destino")

                # --- modo A: sigue en el catálogo pero nadie escucha -----------------
                await register(DEAD, dead_port)
                await apoll(lambda: listed(DEAD, dead_port), f"que Consul liste '{DEAD}'")
                exc, elapsed = await failing(DEAD, "/ok")
                assert circuit_state(DEAD) == {"state": "closed", "fail_counter": 1}, circuit_state(DEAD)
                assert elapsed < 3.0, elapsed
                print(f"[8] registrado pero muerto (connection refused): mismo ServiceCallFailed "
                      f"y el breaker también lo cuenta -> {circuit_state(DEAD)}")

                # --- un 4xx no se reintenta ni abre nada -----------------------------
                get_breaker(TARGET).close()  # se reinicia a mano el breaker de [6]
                before = hits["bad"]
                exc, elapsed = await failing(TARGET, "/bad")
                assert hits["bad"] == before + 1, hits  # un solo intento
                assert circuit_state(TARGET) == {"state": "closed", "fail_counter": 0}, circuit_state(TARGET)
                assert "400" in str(exc), exc
                print(f"[9] 4xx: 1 sola petición, breaker intacto {circuit_state(TARGET)} -> {exc}")

                # --- abierto -> medio abierto -> cerrado ------------------------------
                # reset_timeout corto solo para el check; el default sigue siendo 30s.
                _breakers[TARGET] = pybreaker.CircuitBreaker(
                    fail_max=FAIL_MAX, reset_timeout=1.0, name=TARGET,
                    exclude=[ServiceCallFailed])
                for _ in range(FAIL_MAX):
                    await failing(TARGET, "/boom")
                assert circuit_state(TARGET) == {"state": "open", "fail_counter": 3}, circuit_state(TARGET)
                await asyncio.sleep(1.2)
                assert circuit_state(TARGET)["state"] == "open", "no se cierra solo"
                response = await call_service(TARGET, "GET", "/ok")  # llamada de prueba
                assert response.status_code == 200, response
                assert circuit_state(TARGET) == {"state": "closed", "fail_counter": 0}, circuit_state(TARGET)
                print(f"[10] tras {FAIL_MAX} ciclos abre; pasado el reset_timeout la llamada de "
                      f"prueba funciona y cierra -> {circuit_state(TARGET)}")

                get_breaker("barberflow-check-mapping").half_open()
                assert circuit_state("barberflow-check-mapping") == {
                    "state": "half_open", "fail_counter": 0}
                print("     circuit_state() traduce el 'half-open' de pybreaker a 'half_open'")

            print("\nOK — self-check completo, sin excepciones")
        finally:
            subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
            print(f"({CONTAINER} eliminado)")

    asyncio.run(main())
