"""Logging estructurado en JSON y propagación del `x-correlation-id`.

Cada servicio llama a `configure_logging(<nombre>)` al arrancar y monta
`CorrelationIdMiddleware`. A partir de ahí toda línea de log sale en JSON con
`timestamp`, `level`, `service`, `event` y, dentro de un request, también
`correlation_id` y `user_id`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

CORRELATION_ID_HEADER = "x-correlation-id"


def configure_logging(service: str) -> None:
    """Configura structlog para emitir JSON a stdout etiquetado con `service`."""

    def add_service(_logger, _method, event_dict: dict) -> dict:
        event_dict.setdefault("service", service)
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_service,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        # Sin caché: el logger se reconstruye en cada llamada y así respeta un
        # sys.stdout redirigido (lo usa el self-check de abajo).
        cache_logger_on_first_use=False,
    )


def get_logger(**initial_values) -> structlog.BoundLogger:
    """Devuelve un logger; el contexto del request se añade solo."""
    return structlog.get_logger(**initial_values)


def get_correlation_id() -> str | None:
    """Correlation id del request en curso, o `None` fuera de un request."""
    return structlog.contextvars.get_contextvars().get("correlation_id")


def correlation_headers() -> dict[str, str]:
    """Headers para propagar el correlation id en llamadas HTTP salientes."""
    correlation_id = get_correlation_id()
    return {CORRELATION_ID_HEADER: correlation_id} if correlation_id else {}


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Genera o propaga el `x-correlation-id` y registra una línea por request."""

    def __init__(
        self,
        app,
        *,
        extract_user_id: Callable[[Request], str | None] | None = None,
    ) -> None:
        super().__init__(app)
        self._extract_user_id = extract_user_id

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        # El user_id se bindea antes de procesar el request para que la propia
        # línea del request lo lleve; en una dependencia de ruta llegaría tarde.
        if self._extract_user_id is not None:
            try:
                user_id = self._extract_user_id(request)
            except Exception:
                # Un token inválido debe terminar en el 401 de la ruta, no en un
                # 500 disparado desde el middleware de logging.
                # ponytail: se traga cualquier excepción (también un callback mal
                # cableado); si en la demo falta user_id, loguear aquí un warning.
                user_id = None
            if user_id is not None:
                structlog.contextvars.bind_contextvars(user_id=user_id)

        log = get_logger().bind(method=request.method, path=request.url.path)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Un request que revienta sin dejar rastro es peor que uno lento: se
            # deja la línea y se re-lanza. El middleware observa, no traga; el
            # manejo de la excepción sigue siendo de Starlette.
            log.error(
                "http_request",
                status_code=500,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                exception=type(exc).__name__,
            )
            raise
        else:
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            log.info(
                "http_request",
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return response
        finally:
            # Corre en los dos caminos: el contexto nunca se filtra al siguiente request.
            structlog.contextvars.clear_contextvars()


if __name__ == "__main__":
    import asyncio
    import contextlib
    import io
    import json

    import httpx
    from fastapi import FastAPI

    configure_logging("test-svc")

    app = FastAPI()
    app.add_middleware(
        CorrelationIdMiddleware,
        extract_user_id=lambda request: request.headers.get("x-test-user"),
    )

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return correlation_headers()

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    async def drive_requests() -> tuple[httpx.Response, httpx.Response, str]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get(
                "/ping",
                headers={CORRELATION_ID_HEADER: "abc-123", "x-test-user": "u-42"},
            )
            try:
                await client.get(
                    "/boom",
                    headers={CORRELATION_ID_HEADER: "boom-1", "x-test-user": "u-99"},
                )
                raised = ""
            except RuntimeError as exc:
                raised = str(exc)
            # El request sano va después del que revienta: si el camino de error no
            # limpiara el contexto, este heredaría el user_id "u-99".
            second = await client.get("/ping")
            return first, second, raised

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        # Los requests corren en la misma tarea a propósito: TestClient lanza cada
        # uno en su propia tarea y ahí una fuga de contexto sería indetectable.
        first, second, raised = asyncio.run(drive_requests())

    raw_lines = buffer.getvalue().splitlines()
    assert len(raw_lines) == 3, raw_lines
    first_line, error_line, second_line = (json.loads(line) for line in raw_lines)

    # Un correlation id entrante se respeta y vuelve en la respuesta.
    assert first.headers[CORRELATION_ID_HEADER] == "abc-123"
    assert first_line["correlation_id"] == "abc-123"
    assert first.json() == {CORRELATION_ID_HEADER: "abc-123"}

    # Sin header entrante se genera un uuid4 y también vuelve en la respuesta.
    generated = second.headers[CORRELATION_ID_HEADER]
    assert uuid.UUID(generated).version == 4, generated
    assert second_line["correlation_id"] == generated

    # JSON estructurado con las claves que exige el PDF.
    assert {"timestamp", "level", "service", "event", "correlation_id"} <= first_line.keys()
    assert first_line["service"] == "test-svc"
    assert first_line["level"] == "info"
    assert first_line["event"] == "http_request"
    assert first_line["method"] == "GET"
    assert first_line["path"] == "/ping"
    assert first_line["status_code"] == 200
    assert isinstance(first_line["duration_ms"], float)

    # El user_id del token (aquí simulado) viaja junto al correlation_id.
    assert first_line["user_id"] == "u-42"

    # Un request que revienta deja línea de error con el mismo contexto y se re-lanza.
    assert error_line["level"] == "error"
    assert error_line["event"] == "http_request"
    assert error_line["correlation_id"] == "boom-1"
    assert error_line["user_id"] == "u-99"
    assert error_line["path"] == "/boom"
    assert error_line["status_code"] == 500
    assert error_line["exception"] == "RuntimeError"
    assert raised == "kaboom", "el middleware observa, no traga: la excepción se re-lanza"

    # El contexto no se filtra: ni al siguiente request ni fuera de los requests.
    assert "user_id" not in second_line, second_line
    assert structlog.contextvars.get_contextvars() == {}
    assert correlation_headers() == {}

    print(buffer.getvalue(), end="")
    print(
        "self-check OK: JSON válido, correlation_id propagado y generado, user_id presente,"
        " request fallido logueado con level=error y re-lanzado, sin fugas de contexto"
    )
