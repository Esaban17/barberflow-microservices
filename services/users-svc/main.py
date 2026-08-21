"""users-svc: registro, login y consulta de usuarios de BarberFlow.

Contrato en docs/API.md. Todo lo transversal (hash, JWT, pool, salud, logs,
Consul) sale de shared/; aquí solo quedan las cuatro rutas y su SQL.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from shared.auth import (
    create_access_token,
    hash_password,
    user_id_from_request,
    verify_password,
)
from shared.consul import registered
from shared.db import Database, add_health_routes
from shared.logging import CorrelationIdMiddleware, configure_logging

BCRYPT_MAX_BYTES = 72

db = Database()  # lee DATABASE_URL; falla al arrancar si no está


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.open()
    try:
        async with registered(
            os.environ.get("SERVICE_NAME", "users-svc"),
            int(os.environ.get("SERVICE_PORT", "8003")),
            address=os.environ.get("SERVICE_ADDRESS"),
        ):
            yield
    finally:
        await db.close()


configure_logging("users-svc")
app = FastAPI(title="users-svc", lifespan=lifespan)
# extract_user_id es lo que hace que el user_id del token salga en cada línea de log.
app.add_middleware(CorrelationIdMiddleware, extract_user_id=user_id_from_request)
add_health_routes(app, db)


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    role: Literal["client", "barber"] = "client"

    @field_validator("password")
    @classmethod
    def _cabe_en_bcrypt(cls, value: str) -> str:
        # Sin esto hash_password lanzaría ValueError y el registro sería un 500 (PR #8).
        if len(value.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(f"la contraseña no puede pasar de {BCRYPT_MAX_BYTES} bytes")
        return value


class LoginIn(BaseModel):
    # Sin restricciones a propósito: una contraseña corta es un 401, no un 422.
    email: str
    password: str


def _user(row: tuple) -> dict:
    """Objeto público del contrato. Nunca incluye password_hash."""
    keys = ("id", "email", "full_name", "phone", "role", "created_at")
    return dict(zip(keys, row))


@app.post("/register", status_code=201)
async def register(body: RegisterIn) -> dict:
    try:
        async with db.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO users (email, password_hash, full_name, phone, role)"
                " VALUES (%s, %s, %s, %s, %s)"
                " RETURNING id, email, full_name, phone, role, created_at",
                (
                    body.email,
                    hash_password(body.password),
                    body.full_name,
                    body.phone,
                    body.role,
                ),
            )
            row = await cur.fetchone()
    except psycopg.errors.UniqueViolation:
        # Decide la restricción UNIQUE: un SELECT previo tendría carrera.
        raise HTTPException(409, "El email ya está registrado")
    return _user(row)


@app.post("/login")
async def login(body: LoginIn) -> dict:
    async with db.connection() as conn:
        cur = await conn.execute(
            "SELECT id, email, full_name, role, password_hash FROM users WHERE email = %s",
            (body.email,),
        )
        row = await cur.fetchone()
    # Mismo mensaje para email inexistente y contraseña equivocada: no se revela cuál falló.
    if row is None or not verify_password(body.password, row[4]):
        raise HTTPException(401, "Credenciales inválidas")
    user = {"id": row[0], "email": row[1], "full_name": row[2], "role": row[3]}
    return {
        "access_token": create_access_token(user["id"], user["email"], user["role"]),
        "token_type": "bearer",
        "expires_in": int(os.environ.get("JWT_EXPIRE_MINUTES", "60")) * 60,
        "user": user,
    }


@app.get("/users/{user_id}")
async def get_user(user_id: int) -> dict:
    async with db.connection() as conn:
        cur = await conn.execute(
            "SELECT id, email, full_name, phone, role, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, "Usuario no encontrado")
    return _user(row)
