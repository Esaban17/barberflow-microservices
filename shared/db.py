"""Pool de PostgreSQL (psycopg3) y endpoints de salud compartidos por los servicios."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool

POOL_TIMEOUT = 1.5  # espera máxima por una conexión del pool
READY_TIMEOUT = 2.0  # tope duro para is_ready(): /readyz nunca se cuelga


class Database:
    """Envuelve un AsyncConnectionPool y expone el chequeo de conectividad."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or os.environ["DATABASE_URL"]
        self._pool: AsyncConnectionPool | None = None

    async def open(self) -> None:
        # open=False en el constructor (abrirlo ahí está deprecado) y wait=False al
        # abrir: el pool conecta en segundo plano, así el servicio arranca aunque
        # Postgres todavía no acepte conexiones (los contenedores suben en paralelo).
        self._pool = AsyncConnectionPool(self.dsn, min_size=1, max_size=10, open=False)
        await self._pool.open(wait=False)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def is_ready(self) -> bool:
        try:
            await asyncio.wait_for(self._select_one(), READY_TIMEOUT)
            return True
        except Exception:  # cualquier fallo es "no listo"; nunca propaga
            return False

    async def _select_one(self) -> None:
        assert self._pool is not None
        async with self._pool.connection(timeout=POOL_TIMEOUT) as conn:
            await conn.execute("SELECT 1")

    def connection(self):
        """Uso: `async with db.connection() as conn: ...`."""
        if self._pool is None:
            raise RuntimeError("Database.open() no fue llamado")
        return self._pool.connection()


def add_health_routes(app: FastAPI, db: Database | None = None) -> None:
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        # A propósito no toca la BD: Consul sondea aquí cada 10s y un hipo de
        # Postgres no debe desregistrar al servicio.
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        if db is None:
            return {"status": "ok"}
        if await db.is_ready():
            return {"status": "ok", "database": "up"}
        return JSONResponse(
            status_code=503, content={"status": "error", "database": "down"}
        )


if __name__ == "__main__":
    import logging
    import subprocess
    import time
    from contextlib import asynccontextmanager

    import psycopg
    from fastapi.testclient import TestClient

    CONTAINER = "barberflow-check-db"
    DSN = "postgresql://postgres:check@127.0.0.1:55432/postgres"

    logging.getLogger("psycopg.pool").setLevel(logging.CRITICAL)

    def docker(*args: str, check: bool = True) -> None:
        subprocess.run(["docker", *args], check=check, capture_output=True)

    def wait_for_postgres(deadline_s: float = 60.0) -> None:
        deadline = time.monotonic() + deadline_s
        while time.monotonic() < deadline:
            try:
                psycopg.connect(DSN, connect_timeout=3).close()
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("Postgres no aceptó conexiones dentro del plazo")

    async def check_pool() -> None:
        db = Database(DSN)
        await db.open()
        assert await db.is_ready() is True
        async with db.connection() as conn:
            cur = await conn.execute("SELECT 1")
            assert await cur.fetchone() == (1,)
        await db.close()

    docker("rm", "-f", CONTAINER, check=False)
    try:
        docker(
            "run", "-d", "--rm", "--name", CONTAINER,
            "-e", "POSTGRES_PASSWORD=check", "-p", "55432:5432", "postgres:16-alpine",
        )
        wait_for_postgres()
        print("BD efímera arriba en :55432")

        asyncio.run(check_pool())
        print("is_ready() -> True y SELECT 1 devuelve (1,)")

        db = Database(DSN)

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await db.open()
            yield
            await db.close()

        app = FastAPI(lifespan=lifespan)
        add_health_routes(app, db)

        with TestClient(app) as client:
            r = client.get("/healthz")
            assert r.status_code == 200 and r.json() == {"status": "ok"}, r.text
            r = client.get("/readyz")
            assert r.status_code == 200, r.text
            assert r.json() == {"status": "ok", "database": "up"}, r.text
            print("BD arriba   -> /healthz 200, /readyz 200 {'database': 'up'}")

            docker("rm", "-f", CONTAINER, check=False)

            # Dos llamadas: la 1ª falla sobre la conexión ya rota, la 2ª obliga al
            # pool a reconectar contra una BD ausente (el camino que sí puede colgarse).
            for intento in (1, 2):
                started = time.monotonic()
                r = client.get("/readyz")
                elapsed = time.monotonic() - started
                assert r.status_code == 503, r.text
                assert r.json() == {"status": "error", "database": "down"}, r.text
                assert elapsed < 5, f"/readyz tardó {elapsed:.1f}s"
                print(f"BD caída    -> /readyz 503 en {elapsed:.2f}s (llamada {intento})")

            r = client.get("/healthz")
            assert r.status_code == 200 and r.json() == {"status": "ok"}, r.text
            print("BD caída    -> /healthz sigue 200")

        async def check_cold_start() -> None:
            # Con la BD ya caída: abrir el pool desde cero no debe bloquear ni explotar
            # (es lo que pasa cuando el contenedor del servicio arranca antes que el de la BD).
            started = time.monotonic()
            cold = Database(DSN)
            await cold.open()
            assert await cold.is_ready() is False
            await cold.close()
            elapsed = time.monotonic() - started
            assert elapsed < 5, f"arranque sin BD tardó {elapsed:.1f}s"
            print(f"sin BD      -> open() + is_ready() False en {elapsed:.2f}s")

        asyncio.run(check_cold_start())

        # Servicios sin BD propia (MCP server, agentes A2A) llaman sin `db`.
        bare = FastAPI()
        add_health_routes(bare)
        with TestClient(bare) as client:
            r = client.get("/readyz")
            assert r.status_code == 200 and r.json() == {"status": "ok"}, r.text
            r = client.get("/healthz")
            assert r.status_code == 200 and r.json() == {"status": "ok"}, r.text
            print("sin db      -> /healthz 200, /readyz 200 {'status': 'ok'}")

        print("self-check OK")
    finally:
        docker("rm", "-f", CONTAINER, check=False)
